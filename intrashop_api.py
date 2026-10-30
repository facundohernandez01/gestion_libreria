"""API LAN para IntraShop. Comparte la SQLite y el flujo de ventas del POS."""
from __future__ import annotations

import base64
import json
import logging
import mimetypes
import os
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Depends
from pos_auth import require_config
import intrashop_checkout_store as checkout_store
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from core.settings import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tienda", tags=["IntraShop"])
DB_PATH = settings.db_path
API_KEY = settings.api_key
MEDIA_DIR = Path(DB_PATH).resolve().parent / "intrashop_media"
_jobs: dict[str, dict] = {}
_jobs_lock = threading.RLock()
_checkout_lock = threading.Lock()
_cancel_events: dict[str, threading.Event] = {}


def _auth(x_api_key: str | None) -> None:
    if not API_KEY or x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="API key inválida")


@contextmanager
def _connect():
    conn = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    try:
        yield conn
    finally:
        conn.close()


def _ensure_schema() -> None:
    """Migración aditiva; conserva datos y funciona con bases ya instaladas."""
    with _connect() as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(productos)")}
        if "disponible_tienda" not in cols:
            conn.execute("ALTER TABLE productos ADD COLUMN disponible_tienda INTEGER NOT NULL DEFAULT 0")
        if "imagen_tienda" not in cols:
            conn.execute("ALTER TABLE productos ADD COLUMN imagen_tienda TEXT NOT NULL DEFAULT ''")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_productos_tienda ON productos(disponible_tienda, stock_actual)")
        checkout_store.ensure_schema(conn)
        conn.commit()


def _product(row: sqlite3.Row) -> dict:
    p = dict(row)
    p["disponible_tienda"] = bool(p.get("disponible_tienda", 0))
    p["imagen_url"] = f"/tienda/productos/{p['id']}/imagen" if p.get("imagen_tienda") else ""
    if p.get("imagen_tienda", "").startswith("https://"):
        p["imagen_url"] = p["imagen_tienda"]
    p.pop("imagen_tienda", None)
    return p


class ProductStoreUpdate(BaseModel):
    disponible: bool
    imagen_base64: str | None = None
    imagen_nombre: str = "producto.jpg"
    imagen_url: str | None = None


class CartItem(BaseModel):
    producto_id: int
    cantidad: int = Field(gt=0, le=50)


class CheckoutIn(BaseModel):
    totem_id: str | None = Field(default=None, max_length=64)
    items: list[CartItem] = Field(min_length=1, max_length=50)


def _load_cart(items: list[CartItem]) -> tuple[list[dict], float]:
    ids = [i.producto_id for i in items]
    if len(set(ids)) != len(ids):
        raise HTTPException(400, "Hay productos duplicados en el carrito")
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT id, codigo, descripcion, precio_lista, stock_actual, disponible_tienda FROM productos WHERE id IN ({','.join('?' for _ in ids)})",
            ids,
        ).fetchall()
    by_id = {int(r["id"]): r for r in rows}
    cart, total = [], 0.0
    for item in items:
        p = by_id.get(item.producto_id)
        if not p or not p["disponible_tienda"]:
            raise HTTPException(400, f"Producto {item.producto_id} no disponible en la tienda")
        if int(p["stock_actual"]) < item.cantidad:
            raise HTTPException(409, f"Stock insuficiente para {p['descripcion']}")
        price = round(float(p["precio_lista"]), 2)
        cart.append({"producto_id": int(p["id"]), "cantidad": item.cantidad,
                     "precio_unitario": price, "descripcion": p["descripcion"]})
        total += price * item.cantidad
    return cart, round(total, 2)


def _finalize_sale(job_id: str, cart: list[dict], total: float) -> None:
    """Registra una única venta después de confirmar el pago; revalida stock."""
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job or job.get("sale_done") or job.get("status") != "paid":
            return
        # El estado definitivo se escribe solo después del commit.
    try:
        with _connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            already = conn.execute("SELECT venta_id FROM intrashop_checkouts WHERE id=? AND venta_id IS NOT NULL", (job_id,)).fetchone()
            if already:
                with _jobs_lock:
                    _jobs[job_id].update(status="completed", venta_id=already["venta_id"], sale_done=True)
                return
            caja = conn.execute("SELECT id FROM cajas WHERE estado='abierta' ORDER BY id DESC LIMIT 1").fetchone()
            if not caja:
                raise RuntimeError("No hay una caja abierta. Abrí la caja en el POS antes de cobrar.")
            for item in cart:
                p = conn.execute(
                    "SELECT stock_actual, disponible_tienda, descripcion FROM productos WHERE id=?",
                    (item["producto_id"],),
                ).fetchone()
                if not p or not p["disponible_tienda"] or int(p["stock_actual"]) < item["cantidad"]:
                    raise RuntimeError(f"Stock cambiado durante el pago: {item['descripcion'] if p else item['producto_id']}")
            cur = conn.execute(
                "INSERT INTO ventas (caja_id, fecha, total, estado, metodo_pago, comprobante) VALUES (?, CURRENT_TIMESTAMP, ?, 'completada', 'mercadopago_qr', ?)",
                (int(caja["id"]), total, f"IntraShop Mercado Pago · {job_id}"),
            )
            venta_id = int(cur.lastrowid)
            for item in cart:
                pid, qty, price = item["producto_id"], item["cantidad"], item["precio_unitario"]
                row = conn.execute("SELECT stock_actual FROM productos WHERE id=?", (pid,)).fetchone()
                anterior = int(row["stock_actual"])
                nuevo = anterior - qty
                conn.execute(
                    "INSERT INTO venta_items (venta_id, producto_id, cantidad, precio_unitario, subtotal) VALUES (?,?,?,?,?)",
                    (venta_id, pid, qty, price, round(qty * price, 2)),
                )
                conn.execute("UPDATE productos SET stock_actual=?, fecha_modificacion=CURRENT_TIMESTAMP WHERE id=?", (nuevo, pid))
                conn.execute(
                    """INSERT INTO movimientos_stock
                       (producto_id, tipo, cantidad, stock_anterior, stock_nuevo, referencia_id, observaciones)
                       VALUES (?, 'venta', ?, ?, ?, ?, ?)""",
                    (pid, qty, anterior, nuevo, venta_id, f"Venta IntraShop #{venta_id}"),
                )
            from intrashop_entregas import ensure_schema, register_paid_sale
            ensure_schema(conn)
            register_paid_sale(conn, venta_id, job_id, job.get("totem_id"), job.get("totem_nombre"))
            checkout_store.set_status(conn, job_id, "completed", venta_id)
            conn.commit()
        _save_internal_receipt(venta_id, cart, total, job_id)
        with _jobs_lock:
            _jobs[job_id].update(status="completed", sale_done=True, venta_id=venta_id, total=total, message="Pago confirmado y venta registrada")
    except Exception as exc:
        logger.exception("No se pudo registrar la venta de IntraShop tras el pago")
        with _connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            checkout_store.set_status(conn, job_id, "uncertain")
            conn.commit()
        with _jobs_lock:
            _jobs[job_id].update(status="paid_sale_error", message=str(exc))


def _save_internal_receipt(venta_id: int, cart: list[dict], total: float, job_id: str) -> None:
    """Guarda comprobante interno cuando la configuración de caja lo solicita."""
    try:
        from core.settings import settings as cfg
        if not (cfg.facturacion_activa and cfg.facturar_auto_qr):
            return
        folder = Path(cfg.comprobantes_path)
        if not folder.is_absolute():
            folder = Path(DB_PATH).resolve().parent / folder
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"intrashop_venta_{venta_id}.txt"
        lines = [f"COMPROBANTE INTERNO · IntraShop", f"Venta POS: {venta_id}", f"Referencia: {job_id}",
                 f"Fecha: {time.strftime('%Y-%m-%d %H:%M:%S')}", ""]
        lines.extend(f"{i['descripcion']} x{i['cantidad']} · ${i['precio_unitario']:.2f}" for i in cart)
        lines.extend(["", f"TOTAL: ${total:.2f}", "Pago: Mercado Pago QR", "No es factura fiscal."])
        path.write_text("\n".join(lines), encoding="utf-8")
        with _connect() as conn:
            conn.execute("UPDATE ventas SET comprobante=? WHERE id=?", (str(path), venta_id))
            conn.commit()
    except Exception:
        logger.exception("No se pudo guardar el comprobante interno de IntraShop")


def _run_checkout(job_id: str, cart: list[dict], total: float) -> None:
    from services.mercadopago_service import mp_service
    try:
        with _jobs_lock:
            _jobs[job_id]["status"] = "creating_order"
        with _connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            checkout_store.set_status(conn, job_id, "creating")
            conn.commit()
        pos_ext = _jobs[job_id]["pos_ext"]
        store_ext = _jobs[job_id]["store_ext"]
        ok = mp_service.crear_orden(total, pos_ext=pos_ext, store_ext=store_ext, reference=job_id)
        if not ok:
            raise RuntimeError("Mercado Pago no pudo crear la orden. Revisá la configuración del QR.")
        with _connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            checkout_store.set_status(conn, job_id, "waiting")
            conn.commit()
        with _jobs_lock:
            _jobs[job_id]["status"] = "waiting_payment"
            _jobs[job_id]["message"] = "Escaneá el QR del local para pagar"
            _jobs[job_id]["qr_url"] = _jobs[job_id]["qr_url"] or ""
        cancel_event = _cancel_events[job_id]
        paid = mp_service.verificar_estado(cancelar=cancel_event.is_set, pos_ext=pos_ext, reference=job_id)
        if cancel_event.is_set():
            # Cancelar la visualización no implica que Mercado Pago haya anulado el cobro.
            # Consultar la referencia del pago después de cerrar la orden evita
            # perder una venta aprobada justo durante la cancelación.
            closed = mp_service.cancelar_orden(pos_ext=pos_ext, store_ext=store_ext)
            confirmed = paid or mp_service.consultar_ultimo_pago(reference=job_id)
            if confirmed:
                with _jobs_lock:
                    _jobs[job_id].update(status="paid", message="Pago confirmado durante la cancelación; registrando venta")
                _finalize_sale(job_id, cart, total)
            elif closed:
                with _jobs_lock:
                    _jobs[job_id].update(status="cancelled", message="Orden QR cerrada. No se registró una venta.")
            else:
                with _jobs_lock:
                    _jobs[job_id].update(status="cancel_error", message="No se pudo confirmar el cierre del QR. Revisá Mercado Pago antes de reintentar.")
            return
        if not paid:
            # El timeout de polling no cierra automáticamente el QR en Mercado Pago.
            closed = mp_service.cancelar_orden(pos_ext=pos_ext, store_ext=store_ext)
            confirmed = mp_service.consultar_ultimo_pago(reference=job_id)
            if confirmed:
                with _jobs_lock:
                    _jobs[job_id].update(status="paid", message="Pago confirmado; registrando venta")
                _finalize_sale(job_id, cart, total)
            else:
                with _jobs_lock:
                    _jobs[job_id].update(status="expired" if closed else "cancel_error",
                        message="Tiempo agotado; orden cerrada." if closed else "No se pudo cerrar el QR. Revisá Mercado Pago antes de volver a intentar.")
            return
        with _jobs_lock:
            _jobs[job_id].update(status="paid", message="Pago confirmado; registrando venta")
        _finalize_sale(job_id, cart, total)
    except Exception as exc:
        logger.exception("Checkout IntraShop fallido")
        with _jobs_lock:
            if _cancel_events.get(job_id) and _cancel_events[job_id].is_set():
                _jobs[job_id].update(status="cancel_error", message="No se pudo verificar la cancelación. Revisá Mercado Pago.")
            else:
                _jobs[job_id].update(status="error", message=str(exc))
    finally:
        # No liberar stock cuando el resultado de MP es incierto.
        with _jobs_lock:
            current = _jobs.get(job_id, {}).get("status")
        if current != "completed":
            persisted = "uncertain"  # El cierre de QR no demuestra ausencia definitiva de pago.
            with _connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                checkout_store.set_status(conn, job_id, persisted)
                conn.commit()


@router.get("/health")
def tienda_health():
    _ensure_schema()
    return {"ok": True, "service": "IntraShop", "database": str(DB_PATH)}


@router.get("/productos")
def listar_productos(termino: str = ""):
    _ensure_schema()
    with _connect() as conn:
        rows = conn.execute(
            """SELECT id, codigo, descripcion, categoria, marca, precio_lista,
                      stock_actual, disponible_tienda, imagen_tienda
               FROM productos
               WHERE disponible_tienda=1 AND stock_actual > 0
                 AND (descripcion LIKE ? OR codigo LIKE ? OR categoria LIKE ?)
               ORDER BY descripcion LIMIT 200""",
            (f"%{termino}%", f"%{termino}%", f"%{termino}%"),
        ).fetchall()
    with _connect() as conn:
        products = []
        for row in rows:
            p = _product(row)
            p["stock_actual"] = checkout_store.available(conn, p["id"])
            if p["stock_actual"] > 0:
                products.append(p)
        return products


@router.get("/productos/{producto_id}/imagen")
def imagen_producto(producto_id: int):
    _ensure_schema()
    with _connect() as conn:
        row = conn.execute("SELECT imagen_tienda FROM productos WHERE id=? AND disponible_tienda=1", (producto_id,)).fetchone()
    if not row or not row["imagen_tienda"]:
        raise HTTPException(404, "El producto no tiene imagen")
    if row["imagen_tienda"].startswith("https://"):
        raise HTTPException(404, "La imagen se sirve desde su URL HTTPS externa")
    path = Path(row["imagen_tienda"]).resolve()
    if not path.is_file() or MEDIA_DIR.resolve() not in path.parents:
        raise HTTPException(404, "Imagen no encontrada")
    return FileResponse(path, media_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream")


@router.put("/admin/productos/{producto_id}")
def actualizar_producto_tienda(producto_id: int, body: ProductStoreUpdate, x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    _ensure_schema()
    image_path = ""
    if body.imagen_url:
        from urllib.parse import urlparse
        parsed = urlparse(body.imagen_url.strip())
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise HTTPException(400, "Usá una URL pública HTTPS válida")
        image_path = body.imagen_url.strip()
    if body.imagen_base64:
        try:
            raw = body.imagen_base64.split(",", 1)[-1]
            data = base64.b64decode(raw, validate=True)
        except Exception as exc:
            raise HTTPException(400, "Imagen base64 inválida") from exc
        if len(data) > 5 * 1024 * 1024:
            raise HTTPException(413, "La imagen supera 5 MB")
        name = Path(body.imagen_nombre).name.lower()
        ext = Path(name).suffix
        if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
            raise HTTPException(400, "Formato permitido: JPG, PNG o WebP")
        MEDIA_DIR.mkdir(parents=True, exist_ok=True)
        image_path = str((MEDIA_DIR / f"{producto_id}-{uuid.uuid4().hex}{ext}").resolve())
        Path(image_path).write_bytes(data)
    with _connect() as conn:
        row = conn.execute("SELECT id, imagen_tienda FROM productos WHERE id=?", (producto_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Producto no encontrado")
        if image_path:
            conn.execute("UPDATE productos SET disponible_tienda=?, imagen_tienda=? WHERE id=?",
                         (int(body.disponible), image_path, producto_id))
        else:
            conn.execute("UPDATE productos SET disponible_tienda=? WHERE id=?",
                         (int(body.disponible), producto_id))
        conn.commit()
    return {"ok": True, "producto_id": producto_id, "disponible": body.disponible,
            "imagen_url": f"/tienda/productos/{producto_id}/imagen" if image_path or row["imagen_tienda"] else ""}


class BindingIn(BaseModel):
    terminal_id: str = Field(min_length=3, max_length=64)
    terminal_type: str
    pos_external_id: str = Field(min_length=1, max_length=100)
    store_external_id: str = Field(min_length=1, max_length=100)
    qr_url: str = ""
    nombre: str = ""


@router.get("/admin/mp-bindings")
def listar_bindings(operador: str = Depends(require_config)):
    with _connect() as conn:
        checkout_store.ensure_schema(conn)
        return [dict(x) for x in conn.execute("SELECT * FROM intrashop_mp_bindings ORDER BY terminal_type,nombre")]


@router.put("/admin/mp-bindings")
def asignar_binding(body: BindingIn, operador: str = Depends(require_config)):
    if body.terminal_type not in ("totem", "caja"):
        raise HTTPException(400, "Tipo de terminal inválido")
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        checkout_store.ensure_schema(conn)
        busy = conn.execute("""SELECT id FROM intrashop_checkouts WHERE
            pos_external_id IN (?,(SELECT pos_external_id FROM intrashop_mp_bindings WHERE terminal_id=?))
            AND estado IN ('reserved','creating','waiting','verifying','uncertain','paid') LIMIT 1""",
            (body.pos_external_id,body.terminal_id)).fetchone()
        if busy:
            raise HTTPException(409, "No se puede reasignar un QR con cobros activos")
        try:
            conn.execute("""INSERT INTO intrashop_mp_bindings
                (terminal_id,terminal_type,pos_external_id,store_external_id,qr_url,nombre)
                VALUES (?,?,?,?,?,?) ON CONFLICT(terminal_id) DO UPDATE SET
                terminal_type=excluded.terminal_type,pos_external_id=excluded.pos_external_id,
                store_external_id=excluded.store_external_id,qr_url=excluded.qr_url,nombre=excluded.nombre""",
                (body.terminal_id,body.terminal_type,body.pos_external_id,
                 body.store_external_id,body.qr_url,body.nombre))
            conn.commit()
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Este POS Mercado Pago ya está asignado a otra terminal")
    return {"ok": True}


@router.get("/admin/checkouts-pending")
def pending_checkouts(operador: str = Depends(require_config)):
    with _connect() as conn:
        checkout_store.ensure_schema(conn)
        return [dict(row) for row in conn.execute("""SELECT id,totem_id,pos_external_id,
            estado,total,created_at,updated_at FROM intrashop_checkouts
            WHERE estado NOT IN ('completed','cancelled','failed')
            ORDER BY created_at DESC LIMIT 100""")]


@router.post("/admin/checkouts/{checkout_id}/reconcile")
def reconcile_checkout(checkout_id: str, operador: str = Depends(require_config)):
    """Reconciliar pagos aprobados tras reinicio, sin liberar reservas por ausencia de respuesta."""
    with _connect() as conn:
        row = conn.execute("SELECT * FROM intrashop_checkouts WHERE id=?", (checkout_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Checkout inexistente")
    if row["estado"] == "completed":
        return {"estado":"completed","venta_id":row["venta_id"]}
    from services.mercadopago_service import mp_service
    if not mp_service.consultar_ultimo_pago(reference=checkout_id):
        return {"estado":"uncertain","message":"No se confirmó pago aprobado. Reserva retenida para conciliación."}
    cart = json.loads(row["items_json"])
    with _jobs_lock:
        _jobs[checkout_id] = {"status":"paid","sale_done":False,"totem_id":row["totem_id"],
            "totem_nombre":None,"items":cart,"total":row["total"]}
    _finalize_sale(checkout_id,cart,row["total"])
    with _jobs_lock:
        result = _jobs[checkout_id]
    return {"estado":result["status"],"venta_id":result.get("venta_id"),
            "message":result.get("message","")}


class ReleaseRequest(BaseModel):
    confirmacion: str


@router.post("/admin/checkouts/{checkout_id}/release")
def release_checkout(checkout_id: str, body: ReleaseRequest, operador: str = Depends(require_config)):
    """Liberación excepcional, auditada; requiere verificar pago manualmente en MP."""
    if body.confirmacion != "VERIFIQUE EN MERCADO PAGO QUE NO EXISTE COBRO":
        raise HTTPException(400, "Confirmación de conciliación requerida")
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT estado FROM intrashop_checkouts WHERE id=?", (checkout_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Checkout inexistente")
        if row["estado"] != "uncertain":
            raise HTTPException(409, "Solo se pueden liberar reservas pendientes de conciliación")
        conn.execute("""CREATE TABLE IF NOT EXISTS intrashop_auditoria (
            id INTEGER PRIMARY KEY AUTOINCREMENT, checkout_id TEXT NOT NULL,
            operador TEXT NOT NULL, accion TEXT NOT NULL,
            fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        conn.execute("INSERT INTO intrashop_auditoria(checkout_id,operador,accion) VALUES (?,?,?)",
                     (checkout_id,operador,"LIBERACION_MANUAL_SIN_PAGO_CONFIRMADO"))
        checkout_store.set_status(conn,checkout_id,"cancelled")
        conn.commit()
    return {"ok":True,"estado":"cancelled"}


class TotemRegisterIn(BaseModel):
    id: str = Field(min_length=8, max_length=64)
    nombre: str = Field(min_length=1, max_length=80)


@router.post("/totems/register")
def registrar_totem(body: TotemRegisterIn, x_api_key: str | None = Header(default=None)):
    # La API key de instalación autoriza el alta, no los cambios de nombre de otros tótems.
    if not settings.api_key or x_api_key != settings.api_key:
        raise HTTPException(401, "Clave de instalación inválida")
    from intrashop_entregas import ensure_schema
    with _connect() as conn:
        ensure_schema(conn)
        conn.execute("""INSERT INTO intrashop_totems(id, nombre)
            VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET
            nombre=excluded.nombre, ultimo_contacto=CURRENT_TIMESTAMP""",
            (body.id, body.nombre.strip()))
        conn.commit()
    return {"id": body.id, "nombre": body.nombre.strip(), "ok": True}


@router.post("/checkout")
def iniciar_checkout(body: CheckoutIn):
    _ensure_schema()
    cart, total = _load_cart(body.items)
    with _connect() as conn:
        caja = conn.execute("SELECT id FROM cajas WHERE estado='abierta' ORDER BY id DESC LIMIT 1").fetchone()
    if not caja:
        raise HTTPException(409, "El POS no tiene una caja abierta. Abrí la caja antes de habilitar compras.")
    if not settings.mp_activo:
        raise HTTPException(503, "Mercado Pago está deshabilitado en la configuración del POS")
    totem_nombre = None
    if body.totem_id:
        from intrashop_entregas import ensure_schema
        with _connect() as conn:
            ensure_schema(conn)
            row = conn.execute("SELECT nombre FROM intrashop_totems WHERE id=?", (body.totem_id,)).fetchone()
            if not row:
                raise HTTPException(400, "Tótem no registrado. Revisá la configuración del dispositivo.")
            totem_nombre = row["nombre"]
    if not body.totem_id:
        raise HTTPException(400, "El checkout requiere un tótem registrado")
    job_id = uuid.uuid4().hex
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            checkout_store.ensure_schema(conn)
            binding = checkout_store.reserve(conn, job_id, body.totem_id, cart, total)
            conn.commit()
        except ValueError as exc:
            raise HTTPException(409, str(exc))
    with _jobs_lock:
        _jobs[job_id] = {"status": "queued", "message": "Stock reservado; preparando cobro",
                         "total": total, "items": cart, "created_at": time.time(),
                         "sale_done": False, "totem_id": body.totem_id,
                         "totem_nombre": totem_nombre,
                         "pos_ext": binding["pos_external_id"],
                         "store_ext": binding["store_external_id"],
                         "qr_url": binding["qr_url"]}
        _cancel_events[job_id] = threading.Event()
    threading.Thread(target=_run_checkout, args=(job_id, cart, total), daemon=True).start()
    return {"checkout_id": job_id, "status": "queued", "total": total, "items": cart}


@router.post("/checkout/{checkout_id}/cancel")
def cancelar_checkout(checkout_id: str):
    with _jobs_lock:
        job = _jobs.get(checkout_id)
        if not job:
            raise HTTPException(404, "Checkout no encontrado o servidor reiniciado")
        if job.get("status") in {"completed", "paid", "paid_sale_error"}:
            raise HTTPException(409, "El pago ya fue confirmado; no se puede cancelar desde la tienda.")
        if job.get("status") in {"cancelled", "expired", "error", "cancel_error"}:
            return {"ok": True, "status": job["status"]}
        _cancel_events.setdefault(checkout_id, threading.Event()).set()
        job.update(status="cancelling", message="Cancelando el pedido y cerrando el QR…")
    return {"ok": True, "status": "cancelling"}


@router.get("/checkout/{checkout_id}")
def estado_checkout(checkout_id: str):
    with _jobs_lock:
        job = _jobs.get(checkout_id)
        if not job:
            with _connect() as conn:
                row = conn.execute("SELECT estado,total,venta_id FROM intrashop_checkouts WHERE id=?", (checkout_id,)).fetchone()
            if not row:
                raise HTTPException(404, "Checkout inexistente")
            return {"status": "completed" if row["estado"]=="completed" else "paid_sale_error",
                    "total":row["total"],"venta_id":row["venta_id"],
                    "message":"El servidor se reinició. El pago requiere conciliación del administrador." if row["estado"]!="completed" else "Venta registrada"}
        return {k: v for k, v in job.items() if k not in {"sale_done", "created_at"}}

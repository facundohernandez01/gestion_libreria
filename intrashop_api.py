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

from fastapi import APIRouter, Header, HTTPException
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
        job["sale_done"] = True
    try:
        with _connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
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
            conn.commit()
        _save_internal_receipt(venta_id, cart, total, job_id)
        with _jobs_lock:
            _jobs[job_id].update(status="completed", venta_id=venta_id, total=total, message="Pago confirmado y venta registrada")
    except Exception as exc:
        logger.exception("No se pudo registrar la venta de IntraShop tras el pago")
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
        with _checkout_lock:
            with _jobs_lock:
                _jobs[job_id]["status"] = "creating_order"
            ok = mp_service.crear_orden(total)
            if not ok:
                raise RuntimeError("Mercado Pago no pudo crear la orden. Revisá la configuración del QR.")
            with _jobs_lock:
                _jobs[job_id]["status"] = "waiting_payment"
                _jobs[job_id]["message"] = "Escaneá el QR del local para pagar"
                _jobs[job_id]["qr_url"] = settings.mp_qr_url or ""
            cancel_event = _cancel_events[job_id]
            paid = mp_service.verificar_estado(cancelar=cancel_event.is_set)
            if cancel_event.is_set():
                try:
                    mp_service.cancelar_orden()
                except Exception:
                    logger.exception("No se pudo cerrar la orden QR cancelada")
                with _jobs_lock:
                    _jobs[job_id].update(status="cancelled", message="Pedido cancelado. No se registró ninguna venta.")
                return
            if not paid:
                with _jobs_lock:
                    _jobs[job_id].update(status="expired", message="No se confirmó el pago. Verificá Mercado Pago antes de volver a intentar.")
                return
            with _jobs_lock:
                _jobs[job_id].update(status="paid", message="Pago confirmado; registrando venta")
            _finalize_sale(job_id, cart, total)
    except Exception as exc:
        logger.exception("Checkout IntraShop fallido")
        with _jobs_lock:
            if _cancel_events.get(job_id) and _cancel_events[job_id].is_set():
                _jobs[job_id].update(status="cancelled", message="Pedido cancelado.")
            else:
                _jobs[job_id].update(status="error", message=str(exc))


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
    return [_product(r) for r in rows]


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
    with _jobs_lock:
        active = any(j.get("status") in {"creating_order", "waiting_payment", "paid", "paid_sale_error"} for j in _jobs.values())
        if active:
            raise HTTPException(409, "Ya hay un cobro en curso. Esperá a que finalice.")
        job_id = uuid.uuid4().hex
        _jobs[job_id] = {"status": "queued", "message": "Preparando el cobro", "total": total,
                         "items": cart, "created_at": time.time(), "sale_done": False}
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
        if job.get("status") in {"cancelled", "expired", "error"}:
            return {"ok": True, "status": job["status"]}
        _cancel_events.setdefault(checkout_id, threading.Event()).set()
        job.update(status="cancelling", message="Cancelando el pedido y cerrando el QR…")
    return {"ok": True, "status": "cancelling"}


@router.get("/checkout/{checkout_id}")
def estado_checkout(checkout_id: str):
    with _jobs_lock:
        job = _jobs.get(checkout_id)
        if not job:
            raise HTTPException(404, "Checkout no encontrado o servidor reiniciado")
        return {k: v for k, v in job.items() if k not in {"sale_done", "created_at"}}

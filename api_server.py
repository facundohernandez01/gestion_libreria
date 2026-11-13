"""Servidor FastAPI para modo multi-usuario (LAN).

Expone la base de datos SQLite a través de HTTP. Usa WAL + lock para evitar
colisiones entre hilos/conexiones concurrentes.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import threading
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Header, Request
from pydantic import BaseModel

DB_PATH = os.getenv("DB_PATH", "libreria.db")
API_KEY = os.getenv("API_KEY", "libreria-lan")

# En modo congelado/servicio el cwd puede ser distinto: resolver rutas y
# credenciales con la misma configuración que usa la app.
try:
    from core.settings import settings as _settings

    DB_PATH = _settings.db_path
    API_KEY = _settings.api_key
except Exception:
    pass

# Activar WAL + busy_timeout para concurrencia
_conn_init = sqlite3.connect(DB_PATH)
_conn_init.execute("PRAGMA journal_mode=WAL")
_conn_init.execute("PRAGMA busy_timeout=5000")
_conn_init.commit()
_conn_init.close()

_write_lock = threading.RLock()

# La UI Flet se monta como sub-app; Starlette no ejecuta el lifespan de las
# sub-apps montadas, así que el ciclo de vida de app_manager se maneja acá.
_flet_web_montado = False


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    app_manager = None
    if _flet_web_montado:
        try:
            from flet_web.fastapi import app_manager

            await app_manager.start()
        except Exception as ex:  # noqa: BLE001
            app_manager = None
            logging.getLogger(__name__).warning(
                "No se pudo iniciar Flet App Manager: %s", ex)
    try:
        # En el arranque no quedan workers de cobro del proceso anterior.
        # Conservar sus reservas hasta verificar el resultado en Mercado Pago.
        try:
            from intrashop_api import recover_interrupted_checkouts
            recover_interrupted_checkouts()
            # La consulta a Mercado Pago es I/O remoto; no bloquear el arranque.
            # Solo registra ventas verificadas, nunca libera stock por timeout.
            from intrashop_api import reconcile_pending_after_startup
            threading.Thread(
                target=reconcile_pending_after_startup,
                name="intrashop-startup-reconciliation",
                daemon=True,
            ).start()
        except (sqlite3.Error, OSError) as exc:
            logging.getLogger(__name__).error(
                "No se pudo recuperar checkouts interrumpidos: %s", exc)
            raise
        yield
    finally:
        if app_manager is not None:
            try:
                await app_manager.shutdown()
            except Exception as ex:  # noqa: BLE001
                logging.getLogger(__name__).warning(
                    "Error cerrando Flet App Manager: %s", ex)


app = FastAPI(title="Librería Kiosko — API", version="1.0", lifespan=_lifespan)

# La interfaz Astro compilada se publica desde el mismo servidor FastAPI.
# Si dist no existe, la API continúa funcionando normalmente.
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

INTRASHOP_DIST = Path(__file__).resolve().parent / "intrashop" / "dist"
if (INTRASHOP_DIST / "index.html").is_file():
    class AstroStaticFiles(StaticFiles):
        async def get_response(self, path, scope):
            # Astro static builds output admin/index.html or admin.html.
            try:
                return await super().get_response(path, scope)
            except StarletteHTTPException as exc:
                if exc.status_code != 404:
                    raise
            clean = path.strip("/")
            if not clean or "." in clean.rsplit("/", 1)[-1]:
                raise StarletteHTTPException(status_code=404)
            for candidate in (clean + "/index.html", clean + ".html"):
                if (INTRASHOP_DIST / candidate).is_file():
                    return await super().get_response(candidate, scope)
            raise StarletteHTTPException(status_code=404)

    app.mount("/intrashop", AstroStaticFiles(directory=str(INTRASHOP_DIST), html=True), name="intrashop")


from fastapi.middleware.cors import CORSMiddleware
from intrashop_api import router as intrashop_router

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PUT", "PATCH", "OPTIONS"],
    allow_headers=["*", "x-api-key", "content-type"],
)
app.include_router(intrashop_router)
from intrashop_entregas import router as intrashop_entregas_router
app.include_router(intrashop_entregas_router)
from pos_auth import router as pos_auth_router
app.include_router(pos_auth_router)
from services.mp_oauth_api import router as mp_oauth_router
app.include_router(mp_oauth_router)


def _connect() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    c.execute("PRAGMA busy_timeout=5000")
    return c


def _auth(x_api_key: str | None) -> None:
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="API key inválida")


@contextmanager
def _tx():
    with _write_lock:
        conn = _connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


@app.get("/health")
def health():
    return {"ok": True, "service": "pos-lan", "capabilities": ["intrashop-entregas-v1", "pos-operator-sessions-v1"]}


@app.get("/config")
def get_config(x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    with _connect() as conn:
        rows = conn.execute("SELECT clave, valor FROM config").fetchall()
    return {r["clave"]: r["valor"] for r in rows}


class ConfigIn(BaseModel):
    clave: str
    valor: str


@app.post("/config")
def set_config(body: ConfigIn, x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    with _tx() as conn:
        conn.execute(
            "INSERT INTO config (clave, valor) VALUES (?,?) "
            "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor",
            (body.clave, body.valor),
        )
    return {"ok": True}


# Administración de roles y usuarios: sesión POS con permiso CONFIGURACION.
# No se utiliza la API key LAN como sustituto de la autorización del operador.
from fastapi import Depends
from pos_auth import require_config


@app.get("/roles")
def api_listar_roles(operador: str = Depends(require_config)):
    from database_manager import DatabaseManager
    return DatabaseManager().listar_roles()


@app.get("/roles/{rol_id}")
def api_obtener_rol(rol_id: int, operador: str = Depends(require_config)):
    from database_manager import DatabaseManager
    result = DatabaseManager().obtener_rol(rol_id)
    if result is None:
        raise HTTPException(404, "Rol inexistente")
    return result


@app.post("/roles")
def api_guardar_rol(datos: dict, operador: str = Depends(require_config)):
    from database_manager import DatabaseManager
    with _write_lock:
        rol_id, error = DatabaseManager().guardar_rol(datos)
    return {"id": rol_id, "error": error}


@app.delete("/roles/{rol_id}")
def api_eliminar_rol(rol_id: int, operador: str = Depends(require_config)):
    from database_manager import DatabaseManager
    with _write_lock:
        ok, error = DatabaseManager().eliminar_rol(rol_id)
    return {"ok": ok, "error": error}


@app.get("/usuarios")
def api_listar_usuarios(operador: str = Depends(require_config)):
    from database_manager import DatabaseManager
    return [{k: v for k, v in user.items() if k != "clave"}
            for user in DatabaseManager().listar_usuarios()]


@app.get("/usuarios/{usuario_id}")
def api_obtener_usuario(usuario_id: int, operador: str = Depends(require_config)):
    from database_manager import DatabaseManager
    result = DatabaseManager().obtener_usuario(usuario_id)
    if result is None:
        raise HTTPException(404, "Usuario inexistente")
    return {k: v for k, v in result.items() if k != "clave"}


@app.post("/usuarios")
def api_guardar_usuario(datos: dict, operador: str = Depends(require_config)):
    from database_manager import DatabaseManager
    with _write_lock:
        usuario_id, error = DatabaseManager().guardar_usuario(datos)
    return {"id": usuario_id, "error": error}


@app.delete("/usuarios/{usuario_id}")
def api_eliminar_usuario(usuario_id: int, operador: str = Depends(require_config)):
    from database_manager import DatabaseManager
    with _write_lock:
        ok, error = DatabaseManager().eliminar_usuario(usuario_id)
    return {"ok": ok, "error": error}


@app.get("/productos")
def list_productos(termino: str = "", campo: str = "descripcion", x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    campo = campo if campo in {"descripcion", "codigo", "categoria"} else "descripcion"
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM productos WHERE {campo} LIKE ? ORDER BY descripcion LIMIT 200",
            (f"%{termino or ''}%",),
        ).fetchall()
    return [dict(r) for r in rows]


@app.post("/productos")
def save_producto(producto: dict, x_api_key: str | None = Header(default=None)):
    """Reutiliza las validaciones y transacciones del gestor de datos."""
    _auth(x_api_key)
    from database_manager import DatabaseManager
    with _write_lock:
        producto_id = DatabaseManager().guardar_producto(producto)
    if not producto_id:
        raise HTTPException(status_code=422, detail="Producto inválido o no se pudo guardar")
    return {"id": producto_id}


@app.get("/cajas/historial")
def historial_cajas(filtro: str = "", desde: str = "", hasta: str = "",
                    x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    with _connect() as conn:
        where = []
        params = []
        if filtro.strip():
            where.append("(CAST(id AS TEXT) LIKE ? OR strftime('%Y-%m-%d', fecha_apertura) LIKE ?)")
            params.extend([f"%{filtro.strip()}%", f"%{filtro.strip()}%"])
        if desde.strip():
            where.append("date(fecha_apertura) >= date(?)")
            params.append(desde.strip())
        if hasta.strip():
            where.append("date(fecha_apertura) <= date(?)")
            params.append(hasta.strip())
        sql = "SELECT * FROM cajas"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY fecha_apertura DESC"
        return [dict(row) for row in conn.execute(sql, params).fetchall()]


@app.get("/cajas/{caja_id}/ventas")
def ventas_por_caja(caja_id: int, x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    with _connect() as conn:
        rows = conn.execute("""SELECT v.*, COUNT(vi.id) AS items_count FROM ventas v
            LEFT JOIN venta_items vi ON v.id=vi.venta_id
            WHERE v.caja_id=? AND v.estado='completada'
            GROUP BY v.id ORDER BY v.fecha DESC""", (caja_id,)).fetchall()
        return [dict(row) for row in rows]


@app.get("/cajas/abierta")
def caja_abierta(x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    with _connect() as conn:
        row = conn.execute("SELECT * FROM cajas WHERE estado='abierta' ORDER BY id DESC LIMIT 1").fetchone()
    return dict(row) if row else None


@app.post("/cajas/abrir")
def abrir_caja(importe_apertura: float = 0.0, observaciones: str = "", x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    with _tx() as conn:
        cur = conn.execute(
            "INSERT INTO cajas (importe_apertura, observaciones, estado) VALUES (?,?, 'abierta')",
            (importe_apertura, observaciones),
        )
        return {"id": cur.lastrowid}


@app.post("/cajas/{caja_id}/cerrar")
def cerrar_caja(caja_id: int, observaciones: str = "", x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    with _tx() as conn:
        conn.execute(
            "UPDATE cajas SET estado='cerrada', fecha_cierre=CURRENT_TIMESTAMP, observaciones=? WHERE id=?",
            (observaciones, caja_id),
        )
    return {"ok": True}


class VentaIn(BaseModel):
    caja_id: int
    items: list[dict]
    metodo_pago: str = "efectivo"
    comprobante: str = ""


@app.post("/ventas")
def crear_venta(body: VentaIn, x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    with _tx() as conn:
        # validar caja abierta
        if not conn.execute("SELECT id FROM cajas WHERE id=? AND estado='abierta'", (body.caja_id,)).fetchone():
            raise HTTPException(400, "caja no abierta")
        total = 0.0
        stocks = {}
        for it in body.items:
            pid = int(it["producto_id"]); cant = int(it["cantidad"]); precio = float(it["precio_unitario"])
            if cant <= 0 or precio < 0:
                raise HTTPException(400, "item inválido")
            row = conn.execute("SELECT stock_actual FROM productos WHERE id=?", (pid,)).fetchone()
            import intrashop_checkout_store as reservation_store
            reservation_store.ensure_schema(conn)
            if not row or reservation_store.available(conn, pid) < cant:
                raise HTTPException(409, f"stock disponible insuficiente prod={pid} (reservas IntraShop)")
            stocks[pid] = int(row["stock_actual"])
            total += precio * cant
        cur = conn.execute(
            "INSERT INTO ventas (caja_id, fecha, total, estado, metodo_pago, comprobante) VALUES (?,?,?,?,?,?)",
            (body.caja_id, None, round(total, 2), "completada", body.metodo_pago, body.comprobante or ""),
        )
        # fecha default CURRENT_TIMESTAMP no aplica porque pasamos None -> set now
        conn.execute("UPDATE ventas SET fecha=CURRENT_TIMESTAMP WHERE id=?", (cur.lastrowid,))
        venta_id = int(cur.lastrowid)
        for it in body.items:
            pid = int(it["producto_id"]); cant = int(it["cantidad"]); precio = float(it["precio_unitario"])
            subtotal = round(precio * cant, 2)
            conn.execute(
                "INSERT INTO venta_items (venta_id, producto_id, cantidad, precio_unitario, subtotal) VALUES (?,?,?,?,?)",
                (venta_id, pid, cant, precio, subtotal),
            )
            anterior = stocks[pid]
            nuevo = anterior - cant
            conn.execute("UPDATE productos SET stock_actual=?, fecha_modificacion=CURRENT_TIMESTAMP WHERE id=?", (nuevo, pid))
            conn.execute(
                """INSERT INTO movimientos_stock (producto_id, tipo, cantidad, stock_anterior, stock_nuevo, referencia_id, observaciones)
                   VALUES (?, 'venta', ?, ?, ?, ?, ?)""",
                (pid, cant, anterior, nuevo, venta_id, f"Venta #{venta_id}"),
            )
        return {"venta_id": venta_id, "total": round(total, 2)}


@app.get("/ventas/dia/{caja_id}")
def ventas_dia(caja_id: int, x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    with _connect() as conn:
        rows = conn.execute(
            """SELECT v.*, COUNT(vi.id) AS items_count FROM ventas v
               LEFT JOIN venta_items vi ON v.id = vi.venta_id
               WHERE v.caja_id=? AND v.estado='completada'
               GROUP BY v.id ORDER BY v.fecha DESC""", (caja_id,)).fetchall()
    return [dict(r) for r in rows]


@app.get("/ventas/{venta_id}/items")
def items_venta(venta_id: int, x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    with _connect() as conn:
        rows = conn.execute(
            """SELECT vi.*, p.descripcion AS producto_nombre FROM venta_items vi
               JOIN productos p ON vi.producto_id = p.id WHERE vi.venta_id=?""", (venta_id,)).fetchall()
    return [dict(r) for r in rows]


class FacturaIn(BaseModel):
    venta_id: int
    numero_factura: str
    cae: str
    vencimiento_cae: str


@app.post("/ventas/factura")
def actualizar_factura(body: FacturaIn, x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    with _tx() as conn:
        conn.execute(
            "UPDATE ventas SET numero_factura=?, cae=?, vencimiento_cae=? WHERE id=?",
            (body.numero_factura, body.cae, body.vencimiento_cae, body.venta_id),
        )
    return {"ok": True}


@app.get("/productos/bajo_stock")
def bajo_stock(x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM productos WHERE stock_actual <= stock_minimo ORDER BY descripcion").fetchall()
    return [dict(r) for r in rows]


@app.get("/reportes/top_productos")
def top_productos(desde: str, hasta: str, limit: int = 10,
                  x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    with _connect() as conn:
        rows = conn.execute(
            """SELECT p.id, p.descripcion,
                      COALESCE(SUM(vi.cantidad), 0) AS cantidad_total,
                      COALESCE(SUM(vi.subtotal), 0) AS monto_total,
                      COUNT(DISTINCT v.id) AS num_ventas
               FROM venta_items vi
               JOIN ventas v ON vi.venta_id = v.id
               JOIN productos p ON vi.producto_id = p.id
               WHERE v.fecha BETWEEN ? AND ? AND v.estado = 'completada'
               GROUP BY p.id ORDER BY cantidad_total DESC, monto_total DESC LIMIT ?""",
            (desde, hasta, int(limit))).fetchall()
    return [dict(r) for r in rows]


@app.get("/reportes/ventas_por_dia")
def ventas_por_dia(desde: str, hasta: str, x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    with _connect() as conn:
        rows = conn.execute(
            """SELECT date(fecha) AS dia, COUNT(*) AS cantidad, ROUND(SUM(total), 2) AS total
               FROM ventas WHERE fecha BETWEEN ? AND ? AND estado = 'completada'
               GROUP BY date(fecha) ORDER BY dia""", (desde, hasta)).fetchall()
    return [dict(r) for r in rows]


def run(host: str = "0.0.0.0", port: int = 8000):
    import uvicorn

    uvicorn.run(app, host=host, port=port, log_level="info")


def _montar_flet_web() -> None:
    """Sirve la UI web (Flet) junto a la API: /cliente y /stock en el mismo puerto."""
    global _flet_web_montado
    try:
        from flet.controls.types import RouteUrlStrategy
        from flet_web.fastapi import app as flet_web_app

        from main import main as flet_main
        from utils.paths import base_dir

        app.mount(
            "/",
            flet_web_app(
                flet_main,
                assets_dir=str(base_dir() / "assets"),
                route_url_strategy=RouteUrlStrategy.PATH,
            ),
        )
        _flet_web_montado = True
    except Exception as ex:  # noqa: BLE001
        logging.getLogger(__name__).warning("No se pudo montar la UI web: %s", ex)


if os.getenv("POS_API_ONLY", "").lower() not in ("1", "true", "yes"):
    _montar_flet_web()


# Reposición y proveedores. Nunca se abre una SQLite en el proceso cliente.
# Las mutaciones se serializan con el mismo lock del servidor.
def _gestor_reposicion():
    from database_manager import DatabaseManager
    return DatabaseManager()


@app.get("/proveedores")
def api_proveedores(termino: str = "", limit: int = 500, x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    return _gestor_reposicion().listar_proveedores(termino, min(max(limit, 1), 1000))


@app.get("/proveedores/{proveedor_id}")
def api_proveedor(proveedor_id: int, x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    return _gestor_reposicion().obtener_proveedor(proveedor_id)


@app.post("/proveedores")
def api_guardar_proveedor(body: dict, x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    with _write_lock:
        return {"id": _gestor_reposicion().guardar_proveedor(body["datos"], body.get("contactos"))}


@app.post("/proveedores/obtener-o-crear")
def api_obtener_o_crear_proveedor(body: dict, x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    with _write_lock:
        return {"id": _gestor_reposicion().obtener_o_crear_proveedor(body["nombre"])}


@app.post("/proveedores/{proveedor_id}/eliminar")
def api_eliminar_proveedor(proveedor_id: int, x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    with _write_lock:
        return {"ok": _gestor_reposicion().eliminar_proveedor(proveedor_id)}


@app.get("/reposicion/stock")
def api_stock_reposicion(x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    return _gestor_reposicion().obtener_stock_productos()


@app.get("/reposicion/movimientos")
def api_movimientos_reposicion(producto_id: int | None = None, limit: int = 100, x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    return _gestor_reposicion().obtener_movimientos_stock(producto_id, min(max(limit, 1), 1000))


@app.get("/reposicion/movimientos/detallados")
def api_movimientos_detallados(producto_id: int | None = None, limit: int = 500, x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    return _gestor_reposicion().obtener_movimientos_stock_detallado(producto_id, min(max(limit, 1), 1000))


@app.get("/reposicion/productos/{producto_id}/resumen")
def api_resumen_movimientos(producto_id: int, x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    return _gestor_reposicion().resumen_movimientos_producto(producto_id)


@app.get("/reposicion/productos/{producto_id}/pendientes")
def api_ordenes_pendientes_producto(producto_id: int, x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    return _gestor_reposicion().buscar_ordenes_pendientes_producto(producto_id)


@app.post("/reposicion/productos/{producto_id}/ingresar")
def api_ingresar_stock(producto_id: int, body: dict, x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    with _write_lock:
        ok, mensaje = _gestor_reposicion().ingresar_stock_directo(producto_id, body["cantidad"], body.get("remito", ""), body.get("observaciones", ""))
    return {"ok": ok, "mensaje": mensaje}


@app.get("/reposicion/ordenes/contar")
def api_contar_ordenes(estado: str = "en_proceso", x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    return {"total": _gestor_reposicion().contar_ordenes_compra(estado)}


@app.get("/reposicion/ordenes/pendientes")
def api_contar_pendientes(x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    return {"total": _gestor_reposicion().contar_ordenes_pendientes()}


@app.get("/reposicion/ordenes")
def api_listar_ordenes(estado: str | None = None, proveedor: str = "", desde: str = "", hasta: str = "", ordenar: str = "fecha", ascendente: bool = False, x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    return _gestor_reposicion().listar_ordenes_compra(estado, proveedor, desde, hasta, ordenar, ascendente)


@app.post("/reposicion/ordenes")
def api_crear_orden(body: dict, x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    with _write_lock:
        return {"id": _gestor_reposicion().crear_orden_compra(body["items"], body.get("observaciones", ""))}


@app.get("/reposicion/ordenes/{orden_id}")
def api_obtener_orden(orden_id: int, x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    return _gestor_reposicion().obtener_orden_compra(orden_id)


@app.post("/reposicion/ordenes/{orden_id}/actualizar")
def api_actualizar_orden(orden_id: int, body: dict, x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    with _write_lock:
        return {"ok": _gestor_reposicion().actualizar_orden_compra(orden_id, body["items"], body.get("observaciones"))}


@app.post("/reposicion/ordenes/{orden_id}/confirmar")
def api_confirmar_orden(orden_id: int, x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    with _write_lock:
        ok, mensaje = _gestor_reposicion().confirmar_orden_compra(orden_id)
    return {"ok": ok, "mensaje": mensaje}


@app.post("/reposicion/ordenes/{orden_id}/recibir")
def api_recibir_orden(orden_id: int, body: dict, x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    with _write_lock:
        ok, mensaje = _gestor_reposicion().recibir_orden_compra(orden_id, body["recepciones"], body.get("remito", ""), body.get("observaciones", ""), body.get("cancelar_restante", False))
    return {"ok": ok, "mensaje": mensaje}


@app.post("/reposicion/ordenes/{orden_id}/cancelar")
def api_cancelar_orden(orden_id: int, x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    with _write_lock:
        return {"ok": _gestor_reposicion().cancelar_orden_compra(orden_id)}


# Paridad de consultas y operaciones generales. Los datos pertenecen al servidor.
@app.get("/productos/por-codigo")
def api_producto_codigo(codigo: str, x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    return _gestor_reposicion().obtener_producto_por_codigo(codigo)


@app.get("/productos/{producto_id}")
def api_producto_id(producto_id: int, x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    return _gestor_reposicion().obtener_producto(producto_id)


@app.post("/productos/{producto_id}/eliminar")
def api_eliminar_producto(producto_id: int, x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    with _write_lock:
        return {"ok": _gestor_reposicion().eliminar_producto(producto_id)}


@app.post("/productos/{producto_id}/stock")
def api_actualizar_stock(producto_id: int, body: dict, x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    with _write_lock:
        ok = _gestor_reposicion().actualizar_stock(producto_id, body["cantidad"], body.get("tipo", "ajuste"), body.get("referencia_id"), body.get("observaciones", ""))
    return {"ok": ok}


@app.get("/reportes/ventas")
def api_ventas_rango(desde: str, hasta: str, x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    return _gestor_reposicion().obtener_ventas_por_fechas(desde, hasta)


@app.get("/reportes/ventas/detalle")
def api_ventas_detalle(desde: str, hasta: str, x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    return _gestor_reposicion().obtener_detalle_ventas(desde, hasta)


@app.get("/cajas/{caja_id}/gastos")
def api_gastos_caja(caja_id: int, x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    return _gestor_reposicion().obtener_gastos_caja(caja_id)


@app.post("/cajas/{caja_id}/gastos")
def api_agregar_gasto(caja_id: int, body: dict, x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    with _write_lock:
        return {"id": _gestor_reposicion().agregar_gasto(caja_id, body["monto"], body["concepto"])}


@app.get("/admin/datos/conteos")
def api_conteos_datos(operador: str = Depends(require_config)):
    return _gestor_reposicion().contar_datos()


@app.get("/admin/datos/primer-uso")
def api_primer_uso(operador: str = Depends(require_config)):
    return {"activo": _gestor_reposicion().es_primer_uso()}


@app.post("/admin/datos/primer-uso")
def api_marcar_primer_uso(body: dict, operador: str = Depends(require_config)):
    with _write_lock:
        _gestor_reposicion().marcar_primer_uso(bool(body["activo"]))
    return {"ok": True}


# Vista previa de backup en el servidor. No restaura una SQLite mientras
# FastAPI y los cobros puedan mantener conexiones abiertas.
# El archivo viaja en el cuerpo HTTP; jamás en parámetros de URL.
@app.post("/admin/backups/validar")
async def api_validar_backup(
    request: Request,
    operador: str = Depends(require_config),
):
    """Vista previa únicamente: transmisión por fragmentos y límite de 100 MiB."""
    import tempfile
    from services.backup_service import validar_backup

    MAX_BACKUP_BYTES = 100 * 1024 * 1024
    with tempfile.TemporaryDirectory(prefix="pos-backup-preview-") as folder:
        archivo = Path(folder) / "backup.db"
        recibido = 0
        with archivo.open("wb") as salida:
            async for bloque in request.stream():
                recibido += len(bloque)
                if recibido > MAX_BACKUP_BYTES:
                    raise HTTPException(413, "Backup vacío o superior a 100 MiB")
                salida.write(bloque)
        if recibido == 0:
            raise HTTPException(413, "Backup vacío o superior a 100 MiB")
        try:
            info = validar_backup(archivo)
        except (ValueError, sqlite3.DatabaseError) as exc:
            raise HTTPException(422, f"Backup inválido: {exc}") from exc
    return {
        "valido": True,
        "bytes": info["bytes"],
        "conteos_backup": info["conteos"],
        "conteos_servidor": _gestor_reposicion().contar_datos(),
        "restauracion": "offline_obligatoria",
        "mensaje": "Vista previa solamente. Para aplicar, detener POS Server y usar la herramienta offline.",
    }


@app.get("/admin/backups/exportar")
def api_exportar_backup(operador: str = Depends(require_config)):
    """Exporta un snapshot SQLite consistente sin cargarlo en RAM.

    El archivo temporal persiste mientras FileResponse lo transmite y se
    limpia al finalizar, incluso cuando hay excepciones durante su creación.
    """
    import tempfile
    from fastapi.responses import FileResponse
    from starlette.background import BackgroundTask
    from services.backup_service import exportar_backup

    temporal = tempfile.TemporaryDirectory(prefix="pos-backup-export-")
    try:
        destino = Path(temporal.name) / "backup.db"
        with _write_lock:
            exportar_backup(DB_PATH, destino)
        return FileResponse(
            path=str(destino),
            filename="backup_pos_server.db",
            media_type="application/octet-stream",
            headers={"Cache-Control": "no-store"},
            background=BackgroundTask(temporal.cleanup),
        )
    except BaseException:
        temporal.cleanup()
        raise


@app.post("/productos/{producto_id}/stock-absoluto")
def api_ajustar_stock_absoluto(
    producto_id: int, body: dict,
    operador: str = Depends(require_config),
):
    """Ajuste manual autorizado; falla si cambió el stock desde que se abrió el diálogo."""
    try:
        nuevo = int(body["nuevo_stock"])
        esperado = int(body["stock_esperado"])
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(422, "nuevo_stock y stock_esperado deben ser enteros") from exc
    if min(nuevo, esperado) < 0:
        raise HTTPException(422, "El stock no puede ser negativo")
    with _write_lock:
        ok = _gestor_reposicion().ajustar_stock_absoluto(
            producto_id, nuevo, esperado, str(body.get("observaciones") or ""),
        )
    if not ok:
        raise HTTPException(409, "Stock modificado por otra operación o producto inexistente; actualizá la pantalla")
    return {"ok": True}

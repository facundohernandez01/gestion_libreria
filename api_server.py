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

from fastapi import FastAPI, HTTPException, Header
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
        yield
    finally:
        if app_manager is not None:
            try:
                await app_manager.shutdown()
            except Exception as ex:  # noqa: BLE001
                logging.getLogger(__name__).warning(
                    "Error cerrando Flet App Manager: %s", ex)


app = FastAPI(title="Librería Kiosko — API", version="1.0", lifespan=_lifespan)


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
    return {"ok": True, "db": DB_PATH}


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
            if not row or int(row["stock_actual"]) < cant:
                raise HTTPException(400, f"stock insuficiente prod={pid}")
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


_montar_flet_web()

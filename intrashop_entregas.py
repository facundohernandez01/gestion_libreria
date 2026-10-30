"""Cola de entregas IntraShop: separa cobro confirmado de retiro físico."""
import sqlite3
from fastapi import APIRouter, Header, HTTPException, Depends
from pos_auth import require_delivery
from pydantic import BaseModel, Field
import re
from core.settings import settings

router = APIRouter(prefix="/tienda/admin/entregas", tags=["Entregas IntraShop"])


def connect():
    conn = sqlite3.connect(settings.db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def ensure_schema(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS intrashop_entregas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        venta_id INTEGER NOT NULL UNIQUE REFERENCES ventas(id),
        checkout_id TEXT NOT NULL UNIQUE,
        estado TEXT NOT NULL DEFAULT 'pendiente'
            CHECK (estado IN ('pendiente','preparando','listo','entregado')),
        fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        fecha_actualizacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        entregado_por TEXT,
        fecha_entrega TEXT,
        totem_id TEXT,
        totem_nombre TEXT
    )""")
    columns = {row[1] for row in conn.execute("PRAGMA table_info(intrashop_entregas)")}
    for name in ("totem_id", "totem_nombre"):
        if name not in columns:
            conn.execute("ALTER TABLE intrashop_entregas ADD COLUMN " + name + " TEXT")
    conn.execute("""CREATE TABLE IF NOT EXISTS intrashop_totems (
        id TEXT PRIMARY KEY, nombre TEXT NOT NULL,
        ultimo_contacto TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        fecha_registro TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_intrashop_entregas_estado ON intrashop_entregas(estado, fecha_creacion)")


def authorize(key):
    if not settings.api_key or key != settings.api_key:
        raise HTTPException(401, "API key inválida")


def register_paid_sale(conn, venta_id, checkout_id, totem_id=None, totem_nombre=None):
    """Invocar en la MISMA transacción que registra la venta y descuenta stock."""
    conn.execute("INSERT INTO intrashop_entregas (venta_id, checkout_id, totem_id, totem_nombre) VALUES (?,?,?,?)", (venta_id, checkout_id, totem_id, totem_nombre))


class TotemRegister(BaseModel):
    id: str = Field(min_length=8, max_length=64)
    nombre: str = Field(min_length=1, max_length=80)


@router.get("/totems")
def list_totems(operador: str = Depends(require_delivery)):
    with connect() as conn:
        ensure_schema(conn)
        return [dict(row) for row in conn.execute(
            "SELECT * FROM intrashop_totems ORDER BY nombre COLLATE NOCASE"
        ).fetchall()]


class EntregaUpdate(BaseModel):
    estado: str
    operador: str = Field(min_length=1, max_length=100)


@router.get("")
def list_orders(estado: str = "", operador: str = Depends(require_delivery)):
    if estado and estado not in ("pendiente", "preparando", "listo", "entregado"):
        raise HTTPException(400, "Estado inválido")
    with connect() as conn:
        ensure_schema(conn)
        rows = conn.execute("""
            SELECT e.*, v.total, v.fecha FROM intrashop_entregas e
            JOIN ventas v ON v.id=e.venta_id
            WHERE (?='' OR e.estado=?)
            ORDER BY CASE WHEN e.estado='entregado' THEN 1 ELSE 0 END,
                     e.fecha_creacion ASC LIMIT 250
        """, (estado, estado)).fetchall()
        result = [dict(row) for row in rows]
        for order in result:
            order["items"] = [dict(item) for item in conn.execute("""
                SELECT vi.producto_id, p.descripcion, vi.cantidad, vi.precio_unitario, vi.subtotal
                FROM venta_items vi JOIN productos p ON p.id=vi.producto_id
                WHERE vi.venta_id=? ORDER BY vi.id
            """, (order["venta_id"],)).fetchall()]
    return result


@router.patch("/{order_id}")
def update_order(order_id: int, body: EntregaUpdate, operador: str = Depends(require_delivery)):
    transitions = {"pendiente": {"preparando", "listo", "entregado"}, "preparando": {"listo"}, "listo": {"entregado"}, "entregado": set()}
    with connect() as conn:
        ensure_schema(conn)
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT estado FROM intrashop_entregas WHERE id=?", (order_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Pedido no encontrado")
        if body.estado not in transitions[row["estado"]]:
            raise HTTPException(409, "Transición no permitida")
        conn.execute("""
            UPDATE intrashop_entregas SET estado=?, fecha_actualizacion=CURRENT_TIMESTAMP,
            entregado_por=CASE WHEN ?='entregado' THEN ? ELSE entregado_por END,
            fecha_entrega=CASE WHEN ?='entregado' THEN CURRENT_TIMESTAMP ELSE fecha_entrega END
            WHERE id=?
        """, (body.estado, body.estado, operador, body.estado, order_id))
        conn.commit()
    return {"ok": True, "id": order_id, "estado": body.estado}

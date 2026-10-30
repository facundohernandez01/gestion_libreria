"""Cola de entregas IntraShop: separa cobro confirmado de retiro físico."""
import sqlite3
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
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
        fecha_entrega TEXT
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_intrashop_entregas_estado ON intrashop_entregas(estado, fecha_creacion)")


def authorize(key):
    if not settings.api_key or key != settings.api_key:
        raise HTTPException(401, "API key inválida")


def register_paid_sale(conn, venta_id, checkout_id):
    """Invocar en la MISMA transacción que registra la venta y descuenta stock."""
    conn.execute("INSERT INTO intrashop_entregas (venta_id, checkout_id) VALUES (?,?)", (venta_id, checkout_id))


class EntregaUpdate(BaseModel):
    estado: str
    operador: str = Field(min_length=1, max_length=100)


@router.get("")
def list_orders(estado: str = "", x_api_key: str | None = Header(default=None)):
    authorize(x_api_key)
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
def update_order(order_id: int, body: EntregaUpdate, x_api_key: str | None = Header(default=None)):
    authorize(x_api_key)
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
        """, (body.estado, body.estado, body.operador, body.estado, order_id))
        conn.commit()
    return {"ok": True, "id": order_id, "estado": body.estado}

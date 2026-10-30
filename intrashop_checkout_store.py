"""Persistencia de reservas y asignaciones de terminales Mercado Pago.

La transacción BEGIN IMMEDIATE serializa los cambios de stock entre tótems.
No se libera una reserva mientras el resultado del pago sea incierto.
"""
import json
import sqlite3
import time

ACTIVE = ("reserved", "creating", "waiting", "verifying", "uncertain", "paid")
CLOSED = ("completed", "cancelled", "failed")


def ensure_schema(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS intrashop_mp_bindings (
        terminal_id TEXT PRIMARY KEY,
        terminal_type TEXT NOT NULL CHECK(terminal_type IN ('totem','caja')),
        pos_external_id TEXT NOT NULL UNIQUE,
        store_external_id TEXT NOT NULL,
        qr_url TEXT NOT NULL DEFAULT '',
        nombre TEXT NOT NULL DEFAULT ''
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS intrashop_checkouts (
        id TEXT PRIMARY KEY,
        totem_id TEXT,
        pos_external_id TEXT NOT NULL,
        store_external_id TEXT NOT NULL,
        estado TEXT NOT NULL,
        total REAL NOT NULL,
        items_json TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL,
        venta_id INTEGER UNIQUE
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS intrashop_reservas (
        checkout_id TEXT NOT NULL REFERENCES intrashop_checkouts(id),
        producto_id INTEGER NOT NULL,
        cantidad INTEGER NOT NULL CHECK(cantidad>0),
        PRIMARY KEY(checkout_id, producto_id)
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_intrashop_reservas_producto ON intrashop_reservas(producto_id)")


def binding(conn, terminal_id):
    return conn.execute("SELECT * FROM intrashop_mp_bindings WHERE terminal_id=? AND terminal_type='totem'", (terminal_id,)).fetchone()


def reserve(conn, checkout_id, totem_id, items, total):
    """Invocar con BEGIN IMMEDIATE; evita sobreventa y cobros simultáneos sobre el mismo QR."""
    assigned = binding(conn, totem_id)
    if not assigned:
        raise ValueError("Asigná un POS Mercado Pago exclusivo a este tótem desde Ajustes.")
    occupied = conn.execute("""SELECT id FROM intrashop_checkouts
        WHERE pos_external_id=? AND estado IN ('reserved','creating','waiting','verifying','uncertain','paid')
        LIMIT 1""", (assigned["pos_external_id"],)).fetchone()
    if occupied:
        raise ValueError("El QR de este tótem ya tiene un pago activo o pendiente de conciliación.")
    for item in items:
        row = conn.execute("""SELECT p.stock_actual, p.disponible_tienda,
            COALESCE((SELECT SUM(r.cantidad) FROM intrashop_reservas r
                JOIN intrashop_checkouts c ON c.id=r.checkout_id
                WHERE r.producto_id=p.id AND c.estado IN
                ('reserved','creating','waiting','verifying','uncertain','paid')),0) AS reservado
            FROM productos p WHERE p.id=?""", (item["producto_id"],)).fetchone()
        if not row or not row["disponible_tienda"] or int(row["stock_actual"])-int(row["reservado"]) < item["cantidad"]:
            raise ValueError("Stock disponible insuficiente: " + item["descripcion"])
    now = int(time.time())
    conn.execute("""INSERT INTO intrashop_checkouts
        (id,totem_id,pos_external_id,store_external_id,estado,total,items_json,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?)""",
        (checkout_id,totem_id,assigned["pos_external_id"],assigned["store_external_id"],
         "reserved",total,json.dumps(items,ensure_ascii=False),now,now))
    for item in items:
        conn.execute("INSERT INTO intrashop_reservas VALUES (?,?,?)",
                     (checkout_id,item["producto_id"],item["cantidad"]))
    return dict(assigned)


def set_status(conn, checkout_id, status, venta_id=None):
    conn.execute("""UPDATE intrashop_checkouts SET estado=?, updated_at=?,
        venta_id=COALESCE(?,venta_id) WHERE id=?""", (status,int(time.time()),venta_id,checkout_id))


def available(conn, producto_id):
    row=conn.execute("""SELECT p.stock_actual-COALESCE(SUM(r.cantidad),0)
        FROM productos p LEFT JOIN intrashop_reservas r ON r.producto_id=p.id
        LEFT JOIN intrashop_checkouts c ON c.id=r.checkout_id
          AND c.estado IN ('reserved','creating','waiting','verifying','uncertain','paid')
        WHERE p.id=? GROUP BY p.id""",(producto_id,)).fetchone()
    return int(row[0]) if row else 0

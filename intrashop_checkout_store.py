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
        venta_id INTEGER UNIQUE,
        qr_close_status TEXT NOT NULL DEFAULT 'not_checked',
        qr_close_checked_at INTEGER,
        mp_api TEXT NOT NULL DEFAULT 'legacy',
        mp_order_id TEXT,
        mp_cancel_requested INTEGER NOT NULL DEFAULT 0
    )""")
    # Migración aditiva para instalaciones anteriores.
    cols = {row[1] for row in conn.execute("PRAGMA table_info(intrashop_checkouts)")}
    if "qr_close_status" not in cols:
        conn.execute("ALTER TABLE intrashop_checkouts "
                     "ADD COLUMN qr_close_status TEXT NOT NULL DEFAULT 'not_checked'")
    if "qr_close_checked_at" not in cols:
        conn.execute("ALTER TABLE intrashop_checkouts ADD COLUMN qr_close_checked_at INTEGER")
    for name, sql in (
        ("mp_api", "TEXT NOT NULL DEFAULT 'legacy'"),
        ("mp_order_id", "TEXT"),
        ("mp_cancel_requested", "INTEGER NOT NULL DEFAULT 0"),
    ):
        if name not in cols:
            conn.execute(f"ALTER TABLE intrashop_checkouts ADD COLUMN {name} {sql}")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_intrashop_order_id "
        "ON intrashop_checkouts(mp_order_id) WHERE mp_order_id IS NOT NULL"
    )
    conn.execute("""CREATE TABLE IF NOT EXISTS intrashop_reservas (
        checkout_id TEXT NOT NULL REFERENCES intrashop_checkouts(id),
        producto_id INTEGER NOT NULL,
        cantidad INTEGER NOT NULL CHECK(cantidad>0),
        PRIMARY KEY(checkout_id, producto_id)
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_intrashop_reservas_producto ON intrashop_reservas(producto_id)")


def binding(conn, terminal_id):
    return conn.execute("SELECT * FROM intrashop_mp_bindings WHERE terminal_id=? AND terminal_type='totem'", (terminal_id,)).fetchone()


def reserve(conn, checkout_id, totem_id, items, total, mp_api="legacy"):
    """Invocar con BEGIN IMMEDIATE; evita sobreventa y cobros simultáneos sobre el mismo QR."""
    if mp_api not in ("legacy", "orders_v1"):
        raise ValueError("Proveedor QR desconocido")
    assigned = binding(conn, totem_id)
    if not assigned:
        raise ValueError("Asigná un POS Mercado Pago exclusivo a este tótem desde Ajustes.")
    if not assigned["qr_url"]:
        raise ValueError("El POS asignado no tiene URL de QR. Revisá la asignación.")
    occupied = conn.execute("""SELECT id FROM intrashop_checkouts
        WHERE pos_external_id=? AND estado IN ('reserved','creating','waiting','verifying','uncertain','paid')
        LIMIT 1""", (assigned["pos_external_id"],)).fetchone()
    if occupied:
        raise ValueError("El QR de este tótem ya tiene un pago activo o pendiente de conciliación.")
    # Validar también al nivel de persistencia: no confiar únicamente en
    # el validador HTTP, porque otros clientes pueden llamar reserve().
    ids = [int(item["producto_id"]) for item in items]
    if len(ids) != len(set(ids)):
        raise ValueError("El carrito contiene productos duplicados")
    if not ids or any(int(item["cantidad"]) <= 0 for item in items):
        raise ValueError("El carrito debe contener cantidades positivas")
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
        (id,totem_id,pos_external_id,store_external_id,estado,total,items_json,created_at,updated_at,mp_api)
        VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (checkout_id,totem_id,assigned["pos_external_id"],assigned["store_external_id"],
         "reserved",total,json.dumps(items,ensure_ascii=False),now,now,mp_api))
    for item in items:
        conn.execute("INSERT INTO intrashop_reservas VALUES (?,?,?)",
                     (checkout_id,item["producto_id"],item["cantidad"]))
    return dict(assigned)


def set_status(conn, checkout_id, status, venta_id=None):
    conn.execute("""UPDATE intrashop_checkouts SET estado=?, updated_at=?,
        venta_id=COALESCE(?,venta_id) WHERE id=?""", (status,int(time.time()),venta_id,checkout_id))


QR_CLOSE_STATES = frozenset({"not_checked", "closed", "not_active", "different_order", "uncertain"})


def set_qr_close_status(conn, checkout_id, state):
    """Solo registra evidencia del QR; no cambia el estado de cobro ni reservas."""
    if state not in QR_CLOSE_STATES:
        raise ValueError("Estado de cierre QR inválido")
    conn.execute(
        "UPDATE intrashop_checkouts SET qr_close_status=?, qr_close_checked_at=?, updated_at=? "
        "WHERE id=?",
        (state, int(time.time()), int(time.time()), checkout_id),
    )


def set_mp_order_id(conn, checkout_id, order_id):
    """No permite asociar una segunda orden distinta al mismo checkout."""
    if not order_id:
        raise ValueError("Falta ID de orden")
    row = conn.execute(
        "SELECT mp_api,mp_order_id FROM intrashop_checkouts WHERE id=?",
        (checkout_id,),
    ).fetchone()
    if not row or row["mp_api"] != "orders_v1":
        raise ValueError("Checkout Orders v1 inexistente")
    if row["mp_order_id"] and row["mp_order_id"] != order_id:
        raise ValueError("El checkout ya tiene otra orden Mercado Pago")
    conn.execute(
        "UPDATE intrashop_checkouts SET mp_order_id=?,updated_at=? WHERE id=?",
        (order_id, int(time.time()), checkout_id),
    )


def request_mp_cancel(conn, checkout_id):
    """Persistir el pedido de cancelación antes de avisar al worker."""
    conn.execute(
        "UPDATE intrashop_checkouts SET mp_cancel_requested=1,updated_at=? "
        "WHERE id=? AND mp_api='orders_v1' AND estado NOT IN ('completed','cancelled')",
        (int(time.time()), checkout_id),
    )


def available(conn, producto_id):
    row=conn.execute("""SELECT p.stock_actual-COALESCE(SUM(CASE WHEN c.id IS NOT NULL THEN r.cantidad ELSE 0 END),0)
        FROM productos p LEFT JOIN intrashop_reservas r ON r.producto_id=p.id
        LEFT JOIN intrashop_checkouts c ON c.id=r.checkout_id
          AND c.estado IN ('reserved','creating','waiting','verifying','uncertain','paid')
        WHERE p.id=? GROUP BY p.id""",(producto_id,)).fetchone()
    return int(row[0]) if row else 0

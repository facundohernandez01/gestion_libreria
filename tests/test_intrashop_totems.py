"""Regresión de múltiples tótems y asignación de comandas."""
import sqlite3
from intrashop_entregas import ensure_schema, register_paid_sale


def test_kiosk_identity_is_stored_with_sale(tmp_path):
    path = tmp_path / "pos.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE ventas (id INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO ventas(id) VALUES (1)")
        ensure_schema(conn)
        conn.execute("INSERT INTO intrashop_totems(id,nombre) VALUES (?,?)", ("kiosk-0001", "Entrada"))
        register_paid_sale(conn, 1, "checkout-001", "kiosk-0001", "Entrada")
        order = conn.execute("SELECT totem_id, totem_nombre, estado FROM intrashop_entregas").fetchone()
        assert order == ("kiosk-0001", "Entrada", "pendiente")


def test_old_orders_are_migrated_without_losing_history(tmp_path):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE ventas (id INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO ventas(id) VALUES (1)")
        conn.execute("""CREATE TABLE intrashop_entregas(
            id INTEGER PRIMARY KEY, venta_id INTEGER, checkout_id TEXT,
            estado TEXT, fecha_creacion TEXT, fecha_actualizacion TEXT,
            entregado_por TEXT, fecha_entrega TEXT)""")
        conn.execute("""INSERT INTO intrashop_entregas
            VALUES (1,1,'legacy-1','pendiente','2026-01-01','2026-01-01',NULL,NULL)""")
        ensure_schema(conn)
        row = conn.execute("SELECT checkout_id, totem_id FROM intrashop_entregas").fetchone()
        assert row == ("legacy-1", None)

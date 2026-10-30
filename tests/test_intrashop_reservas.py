"""Pruebas de reservas de inventario y exclusividad de POS Mercado Pago."""
import sqlite3
import pytest
from intrashop_checkout_store import ensure_schema, reserve, set_status, available


@pytest.fixture
def db(tmp_path):
    conn=sqlite3.connect(tmp_path/"checkout.db")
    conn.row_factory=sqlite3.Row
    conn.execute("CREATE TABLE productos(id INTEGER PRIMARY KEY, stock_actual INTEGER, disponible_tienda INTEGER)")
    conn.execute("INSERT INTO productos VALUES (1,5,1)")
    ensure_schema(conn)
    conn.execute("""INSERT INTO intrashop_mp_bindings VALUES
        ('totem-a','totem','mp-a','store','https://qr/a','A'),
        ('totem-b','totem','mp-b','store','https://qr/b','B')""")
    conn.commit()
    yield conn
    conn.close()


def item(qty):
    return [{"producto_id":1,"cantidad":qty,"descripcion":"Agua","precio_unitario":100}]


def test_reservation_prevents_oversell(db):
    db.execute("BEGIN IMMEDIATE")
    reserve(db,"order-a","totem-a",item(4),400)
    db.commit()
    assert available(db,1)==1
    db.execute("BEGIN IMMEDIATE")
    with pytest.raises(ValueError,match="Stock"):
        reserve(db,"order-b","totem-b",item(2),200)
    db.rollback()


def test_distinct_qr_and_confirmed_release(db):
    db.execute("BEGIN IMMEDIATE")
    reserve(db,"order-a","totem-a",item(2),200)
    with pytest.raises(ValueError,match="QR"):
        reserve(db,"order-b","totem-a",item(1),100)
    db.commit()
    assert available(db,1)==3
    db.execute("BEGIN IMMEDIATE")
    set_status(db,"order-a","cancelled")
    db.commit()
    assert available(db,1)==5
    db.execute("BEGIN IMMEDIATE")
    reserve(db,"order-b","totem-b",item(3),300)
    db.commit()
    assert available(db,1)==2

"""Pruebas de persistencia y transiciones de entregas IntraShop."""
import sqlite3
from unittest.mock import patch

import pytest
from fastapi import HTTPException

import intrashop_entregas as entregas


@pytest.fixture
def database(tmp_path):
    path = str(tmp_path / "test.db")
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE ventas (id INTEGER PRIMARY KEY, total REAL, fecha TEXT)")
        conn.execute("CREATE TABLE productos (id INTEGER PRIMARY KEY, descripcion TEXT)")
        conn.execute("CREATE TABLE venta_items (id INTEGER PRIMARY KEY, venta_id INTEGER, producto_id INTEGER, cantidad INTEGER, precio_unitario REAL, subtotal REAL)")
        conn.execute("INSERT INTO ventas VALUES (1, 1200, '2026-10-30 10:00:00')")
        conn.execute("INSERT INTO productos VALUES (1, 'Producto demo')")
        conn.execute("INSERT INTO venta_items VALUES (1,1,1,2,600,1200)")
    with patch.object(entregas.settings, "db_path", path):
        with entregas.connect() as conn:
            entregas.ensure_schema(conn)
            entregas.register_paid_sale(conn, 1, "checkout-test")
            conn.commit()
        yield path


def test_order_persists(database):
    with sqlite3.connect(database) as conn:
        assert conn.execute("SELECT estado FROM intrashop_entregas WHERE venta_id=1").fetchone()[0] == "pendiente"


def test_fulfillment_transitions(database):
    with patch.object(entregas.settings, "db_path", database):
        with patch.object(entregas.settings, "api_key", "test-key"):
            orders = entregas.list_orders(x_api_key="test-key")
            assert len(orders) == 1
            assert orders[0]["items"][0]["cantidad"] == 2
            for state in ("preparando", "listo", "entregado"):
                assert entregas.update_order(orders[0]["id"], entregas.EntregaUpdate(estado=state, operador="operador1"), x_api_key="test-key")["estado"] == state
            with pytest.raises(HTTPException) as exc:
                entregas.update_order(orders[0]["id"], entregas.EntregaUpdate(estado="preparando", operador="operador1"), x_api_key="test-key")
            assert exc.value.status_code == 409


def test_auth_required(database):
    with patch.object(entregas.settings, "api_key", "test-key"):
        with pytest.raises(HTTPException) as exc:
            entregas.list_orders(x_api_key="wrong")
        assert exc.value.status_code == 401

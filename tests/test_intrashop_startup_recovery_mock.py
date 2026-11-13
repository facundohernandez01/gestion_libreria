"""Recuperación real en SQLite temporal con Mercado Pago simulado.

No requiere acceso a la red ni credenciales de comercio.
"""
from contextlib import contextmanager
import json
import sqlite3
import time

import pytest

import intrashop_api as api
import intrashop_checkout_store as checkout
from services.mercadopago_service import mp_service


@contextmanager
def _connection(path):
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def recovery_db(tmp_path, monkeypatch):
    ruta = str(tmp_path / "checkout_recovery.db")
    with _connection(ruta) as conn:
        conn.execute("CREATE TABLE productos (id INTEGER PRIMARY KEY, stock_actual INTEGER NOT NULL)")
        conn.execute("INSERT INTO productos(id,stock_actual) VALUES(1,5)")
        checkout.ensure_schema(conn)
        now = int(time.time())
        conn.execute(
            "INSERT INTO intrashop_checkouts "
            "(id,totem_id,pos_external_id,store_external_id,estado,total,items_json,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            ("checkout-1", "totem-1", "POS-1", "STORE-1", "uncertain", 40,
             json.dumps([{"producto_id": 1, "cantidad": 3}]), now, now),
        )
        conn.execute("INSERT INTO intrashop_reservas VALUES('checkout-1', 1, 3)")
        conn.commit()

    @contextmanager
    def fake_connect():
        with _connection(ruta) as conn:
            yield conn

    monkeypatch.setattr(api, "_connect", fake_connect)
    return ruta


@pytest.mark.parametrize("close_status", [
    "closed", "not_active", "different_order", "uncertain",
])
def test_recuperacion_no_libera_stock_sin_pago_verificado(
    recovery_db, monkeypatch, close_status,
):
    llamadas = []
    monkeypatch.setattr(
        api, "_reconcile_checkout_impl",
        lambda checkout_id: {"estado": "uncertain"},
    )
    def cerrar(checkout_id, pos_ext="", store_ext=""):
        llamadas.append((checkout_id, pos_ext, store_ext))
        return {"estado": close_status}
    monkeypatch.setattr(mp_service, "cerrar_orden_referencia", cerrar)
    resultado = api._recover_checkout_after_restart("checkout-1")
    assert resultado["estado"] == "uncertain"
    assert resultado["qr_close_status"] == close_status
    assert llamadas == [("checkout-1", "POS-1", "STORE-1")]
    with _connection(recovery_db) as conn:
        assert checkout.available(conn, 1) == 2
        row = conn.execute(
            "SELECT estado,qr_close_status,venta_id FROM intrashop_checkouts WHERE id='checkout-1'"
        ).fetchone()
    assert row["estado"] == "uncertain"
    assert row["qr_close_status"] == close_status
    assert row["venta_id"] is None


def test_recuperacion_no_cierra_por_segunda_vez_qr_ya_cerrado(
    recovery_db, monkeypatch,
):
    monkeypatch.setattr(
        api, "_reconcile_checkout_impl",
        lambda checkout_id: {"estado": "uncertain"},
    )
    llamados = []
    monkeypatch.setattr(
        mp_service, "cerrar_orden_referencia",
        lambda *args, **kwargs: llamados.append(args) or {"estado": "closed"},
    )
    assert api._recover_checkout_after_restart("checkout-1")["qr_close_status"] == "closed"
    assert api._recover_checkout_after_restart("checkout-1")["qr_close_status"] == "closed"
    assert len(llamados) == 1


def test_recuperacion_reconsulta_pago_despues_de_cerrar(recovery_db, monkeypatch):
    llamadas = []
    def conciliar(checkout_id):
        llamadas.append("pago")
        return {"estado": "uncertain" if len(llamadas) == 1 else "completed"}
    def cerrar(*args, **kwargs):
        llamadas.append("cierre")
        return {"estado": "closed"}
    monkeypatch.setattr(api, "_reconcile_checkout_impl", conciliar)
    monkeypatch.setattr(mp_service, "cerrar_orden_referencia", cerrar)
    assert api._recover_checkout_after_restart("checkout-1")["estado"] == "completed"
    assert llamadas == ["pago", "cierre", "pago"]


def test_migracion_conserva_checkout_existente(tmp_path):
    path = str(tmp_path / "viejo.db")
    with _connection(path) as conn:
        conn.execute(
            "CREATE TABLE intrashop_checkouts ("
            "id TEXT PRIMARY KEY, totem_id TEXT, pos_external_id TEXT NOT NULL,"
            "store_external_id TEXT NOT NULL, estado TEXT NOT NULL,"
            "total REAL NOT NULL, items_json TEXT NOT NULL,"
            "created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,"
            "venta_id INTEGER UNIQUE)"
        )
        conn.execute(
            "INSERT INTO intrashop_checkouts VALUES('viejo','totem','POS','STORE',"
            "'uncertain',10,'[]',1,1,NULL)"
        )
        checkout.ensure_schema(conn)
        conn.commit()
        row = conn.execute(
            "SELECT id,estado,qr_close_status,qr_close_checked_at FROM intrashop_checkouts"
        ).fetchone()
    assert row["id"] == "viejo"
    assert row["estado"] == "uncertain"
    assert row["qr_close_status"] == "not_checked"
    assert row["qr_close_checked_at"] is None

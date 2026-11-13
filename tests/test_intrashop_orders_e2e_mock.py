"""Circuito IntraShop Orders v1: SQLite real y proveedor MP simulado."""
from contextlib import contextmanager
import sqlite3
import threading

import pytest

from database_manager import DatabaseManager
import intrashop_api as api
import intrashop_checkout_store as store


class FakeOrders:
    def __init__(self, state="approved", close="cancelled", cancel_after_poll=False):
        self.state = state
        self.close = close
        self.cancel_after_poll = cancel_after_poll
        self.creations = []
        self.consultations = []
        self.cancellations = []

    def crear(self, reference, pos, items, total):
        self.creations.append((reference, pos, total))
        return {"estado": "created", "order_id": "ORDTEST01"}

    def consultar(self, order_id, reference, total):
        self.consultations.append((order_id, reference, total))
        if self.cancel_after_poll:
            api._cancel_events[reference].set()
        return {"estado": self.state, "order_id": order_id}

    def cancelar(self, order_id, reference, total):
        self.cancellations.append((order_id, reference, total))
        return {"estado": self.close, "order_id": order_id}


@pytest.fixture
def database(tmp_path, monkeypatch):
    path = str(tmp_path / "orders.db")
    DatabaseManager(path)

    @contextmanager
    def connect():
        conn = sqlite3.connect(path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
        finally:
            conn.close()

    with connect() as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(productos)")}
        if "disponible_tienda" not in columns:
            conn.execute("ALTER TABLE productos ADD COLUMN disponible_tienda INTEGER DEFAULT 0")
        pid = conn.execute(
            "INSERT INTO productos (codigo,descripcion,precio_lista,stock_actual,disponible_tienda) "
            "VALUES ('ORDER-ITEM','Producto Orders',25,5,1)"
        ).lastrowid
        conn.execute(
            "INSERT INTO cajas (fecha_apertura,importe_apertura,estado) "
            "VALUES(CURRENT_TIMESTAMP,0,'abierta')"
        )
        store.ensure_schema(conn)
        conn.execute(
            "INSERT INTO intrashop_mp_bindings "
            "(terminal_id,terminal_type,pos_external_id,store_external_id,qr_url) "
            "VALUES('totem-test','totem','POS-TEST','STORE-TEST','https://example.test/qr')"
        )
        conn.commit()
    monkeypatch.setattr(api, "_connect", connect)
    api._jobs.clear()
    api._cancel_events.clear()
    api._reconciling.clear()
    return connect, pid


def checkout(database, ref="test_order_1"):
    connect, pid = database
    cart = [{
        "producto_id": pid, "cantidad": 2,
        "precio_unitario": 25, "descripcion": "Producto Orders",
    }]
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        store.reserve(conn, ref, "totem-test", cart, 50, mp_api="orders_v1")
        conn.commit()
    api._jobs[ref] = {
        "status": "queued", "sale_done": False,
        "items": cart, "total": 50, "totem_id": "totem-test",
        "totem_nombre": "Pruebas", "mp_api": "orders_v1",
    }
    api._cancel_events[ref] = threading.Event()
    return ref, cart


def counts(database):
    connect, pid = database
    with connect() as conn:
        return (
            conn.execute("SELECT COUNT(*) FROM ventas").fetchone()[0],
            conn.execute("SELECT stock_actual FROM productos WHERE id=?", (pid,)).fetchone()[0],
            conn.execute("SELECT COUNT(*) FROM intrashop_entregas").fetchone()[0],
        )


def test_pago_aprobado_descuenta_stock_registra_entrega_y_no_duplica(database, monkeypatch):
    ref, cart = checkout(database)
    fake = FakeOrders()
    monkeypatch.setattr(api, "_orders_client", lambda: fake)
    api._run_checkout_orders_v1(ref, cart, 50)
    assert counts(database) == (1, 3, 1)
    with database[0]() as conn:
        row = conn.execute(
            "SELECT estado,mp_api,mp_order_id,venta_id FROM intrashop_checkouts WHERE id=?",
            (ref,),
        ).fetchone()
        assert row["estado"] == "completed"
        assert row["mp_api"] == "orders_v1"
        assert row["mp_order_id"] == "ORDTEST01"
        assert row["venta_id"]
        assert store.available(conn, database[1]) == 3
    assert api._orders_reconcile(ref) == {"estado": "completed", "venta_id": row["venta_id"]}
    assert counts(database) == (1, 3, 1)
    assert len(fake.creations) == 1


def test_cancelacion_confirmada_libera_reserva_sin_venta(database, monkeypatch):
    ref, cart = checkout(database)
    fake = FakeOrders(state="pending", close="cancelled", cancel_after_poll=True)
    monkeypatch.setattr(api, "_orders_client", lambda: fake)
    api._run_checkout_orders_v1(ref, cart, 50)
    assert counts(database) == (0, 5, 0)
    with database[0]() as conn:
        assert conn.execute(
            "SELECT estado FROM intrashop_checkouts WHERE id=?", (ref,)
        ).fetchone()["estado"] == "cancelled"
        assert store.available(conn, database[1]) == 5
    assert len(fake.cancellations) == 1


def test_cierre_incierto_retiene_stock(database, monkeypatch):
    ref, cart = checkout(database)
    fake = FakeOrders(state="pending", close="uncertain", cancel_after_poll=True)
    monkeypatch.setattr(api, "_orders_client", lambda: fake)
    api._run_checkout_orders_v1(ref, cart, 50)
    assert counts(database) == (0, 5, 0)
    with database[0]() as conn:
        assert conn.execute(
            "SELECT estado FROM intrashop_checkouts WHERE id=?", (ref,)
        ).fetchone()["estado"] == "uncertain"
        assert store.available(conn, database[1]) == 3


def test_reinicio_con_order_id_recupera_venta_una_sola_vez(database, monkeypatch):
    ref, cart = checkout(database)
    with database[0]() as conn:
        conn.execute("BEGIN IMMEDIATE")
        store.set_mp_order_id(conn, ref, "ORDTEST01")
        store.set_status(conn, ref, "uncertain")
        conn.commit()
    api._jobs.clear()  # Worker perdido en el reinicio
    fake = FakeOrders()
    monkeypatch.setattr(api, "_orders_client", lambda: fake)
    result = api._recover_checkout_after_restart(ref)
    assert result["estado"] == "completed"
    assert counts(database) == (1, 3, 1)
    assert api._recover_checkout_after_restart(ref)["estado"] == "completed"
    assert counts(database) == (1, 3, 1)
    assert fake.creations == []


def test_liberacion_manual_v1_requiere_estado_terminal_verificado(database, monkeypatch):
    ref, cart = checkout(database)
    with database[0]() as conn:
        conn.execute("BEGIN IMMEDIATE")
        store.set_mp_order_id(conn, ref, "ORDTEST01")
        store.set_status(conn, ref, "uncertain")
        conn.commit()
    fake = FakeOrders(state="pending", close="cancelled")
    monkeypatch.setattr(api, "_orders_client", lambda: fake)
    result = api.release_checkout(
        ref, api.ReleaseRequest(confirmacion="VERIFIQUE EN MERCADO PAGO QUE NO EXISTE COBRO"),
        operador="TEST_ADMIN",
    )
    assert result["estado"] == "cancelled"
    assert result["liberacion"] == "estado_orders_verificado"
    with database[0]() as conn:
        assert store.available(conn, database[1]) == 5
    assert counts(database) == (0, 5, 0)


def test_liberacion_manual_v1_no_libera_orden_incierta(database, monkeypatch):
    ref, cart = checkout(database)
    with database[0]() as conn:
        conn.execute("BEGIN IMMEDIATE")
        store.set_mp_order_id(conn, ref, "ORDTEST01")
        store.set_status(conn, ref, "uncertain")
        conn.commit()
    fake = FakeOrders(state="pending", close="uncertain")
    monkeypatch.setattr(api, "_orders_client", lambda: fake)
    with pytest.raises(api.HTTPException) as error:
        api.release_checkout(
            ref, api.ReleaseRequest(confirmacion="VERIFIQUE EN MERCADO PAGO QUE NO EXISTE COBRO"),
            operador="TEST_ADMIN",
        )
    assert error.value.status_code == 409
    with database[0]() as conn:
        assert store.available(conn, database[1]) == 3

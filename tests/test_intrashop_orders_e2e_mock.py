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
        from intrashop_entregas import ensure_schema as ensure_deliveries
        ensure_deliveries(conn)
        conn.execute("INSERT INTO intrashop_totems (id,nombre) VALUES ('totem-test','Tótem prueba')")
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


def test_checkout_http_selecciona_orders_v1_solo_con_flag(database, monkeypatch):
    from threading import Event

    event = Event()
    calls = []
    monkeypatch.setenv("INTRASHOP_MP_ORDERS_V1", "1")
    monkeypatch.setattr(api.settings, "mp_activo", True)

    def fake_worker(ref, cart, total):
        calls.append((ref, total))
        event.set()

    monkeypatch.setattr(api, "_run_checkout_orders_v1", fake_worker)
    monkeypatch.setattr(
        api, "_run_checkout",
        lambda *args: (_ for _ in ()).throw(AssertionError("Se llamó legacy")),
    )
    result = api.iniciar_checkout(
        api.CheckoutIn(
            totem_id="totem-test",
            items=[api.CartItem(producto_id=database[1], cantidad=2)],
        )
    )
    assert result["mp_api"] == "orders_v1"
    assert event.wait(5)
    assert calls == [(result["checkout_id"], result["total"])]
    assert result["total"] == sum(
        item["precio_unitario"] * item["cantidad"] for item in result["items"]
    )
    with database[0]() as conn:
        row = conn.execute(
            "SELECT mp_api,estado FROM intrashop_checkouts WHERE id=?",
            (result["checkout_id"],),
        ).fetchone()
        assert row["mp_api"] == "orders_v1"
        assert row["estado"] == "reserved"


def test_checkout_http_no_migra_legacy_por_defecto(database, monkeypatch):
    from threading import Event

    event = Event()
    monkeypatch.setenv("INTRASHOP_MP_ORDERS_V1", "0")
    monkeypatch.setattr(api.settings, "mp_activo", True)
    monkeypatch.setattr(
        api, "_run_checkout",
        lambda ref, cart, total: event.set(),
    )
    monkeypatch.setattr(
        api, "_run_checkout_orders_v1",
        lambda *args: (_ for _ in ()).throw(AssertionError("Se llamó Orders v1")),
    )
    result = api.iniciar_checkout(
        api.CheckoutIn(
            totem_id="totem-test",
            items=[api.CartItem(producto_id=database[1], cantidad=2)],
        )
    )
    assert result["mp_api"] == "legacy"
    assert event.wait(5)
    with database[0]() as conn:
        assert conn.execute(
            "SELECT mp_api FROM intrashop_checkouts WHERE id=?",
            (result["checkout_id"],),
        ).fetchone()["mp_api"] == "legacy"


def test_admin_recupera_order_id_perdido_solo_por_get_valido(database, monkeypatch):
    ref, cart = checkout(database)
    with database[0]() as conn:
        conn.execute("BEGIN IMMEDIATE")
        store.set_status(conn, ref, "uncertain")
        conn.commit()
    fake = FakeOrders(state="pending")
    monkeypatch.setattr(api, "_orders_client", lambda: fake)
    result = api.resolve_mp_order_id(
        ref, api.ResolveMpOrderIn(order_id="ORDTEST01"), operador="TEST_ADMIN",
    )
    assert result["estado"] == "pending"
    with database[0]() as conn:
        row = conn.execute(
            "SELECT mp_order_id,estado FROM intrashop_checkouts WHERE id=?",
            (ref,),
        ).fetchone()
        assert row["mp_order_id"] == "ORDTEST01"
        assert row["estado"] == "uncertain"
        audit = conn.execute(
            "SELECT accion FROM intrashop_auditoria WHERE checkout_id=?", (ref,),
        ).fetchone()
        assert audit["accion"] == "ASOCIACION_MANUAL_ORDER_ID_VERIFICADO"


def test_admin_no_asocia_order_id_sin_validacion(database, monkeypatch):
    ref, cart = checkout(database)
    fake = FakeOrders(state="uncertain")
    monkeypatch.setattr(api, "_orders_client", lambda: fake)
    with pytest.raises(api.HTTPException) as exc:
        api.resolve_mp_order_id(
            ref, api.ResolveMpOrderIn(order_id="ORDTEST01"), operador="TEST_ADMIN",
        )
    assert exc.value.status_code == 409
    with database[0]() as conn:
        assert conn.execute(
            "SELECT mp_order_id FROM intrashop_checkouts WHERE id=?",
            (ref,),
        ).fetchone()["mp_order_id"] is None
        assert store.available(conn, database[1]) == 3


def test_conciliacion_periodica_procesa_inciertos_sin_webhook(database, monkeypatch):
    ref, cart = checkout(database)
    with database[0]() as conn:
        conn.execute("BEGIN IMMEDIATE")
        store.set_status(conn, ref, "uncertain")
        conn.commit()
    seen = []
    monkeypatch.setattr(
        api, "_recover_checkout_after_restart",
        lambda checkout_id: seen.append(checkout_id) or {"estado": "uncertain"},
    )

    class StopAfterOneCycle:
        calls = 0
        def wait(self, seconds):
            self.calls += 1
            return self.calls > 1
        def is_set(self):
            return False

    api.reconcile_orders_v1_periodically(StopAfterOneCycle(), interval=10)
    assert seen == [ref]


def test_cancelacion_legacy_cierra_qr_sin_buscar_pago_ni_crear_venta(database, monkeypatch):
    """Cancelar durante el PUT remoto libera el stock tras DELETE confirmado."""
    from services.mercadopago_service import mp_service

    ref, cart = checkout(database, "legacy-cancel-in-flight")
    with database[0]() as conn:
        conn.execute("UPDATE intrashop_checkouts SET mp_api='legacy' WHERE id=?", (ref,))
        conn.commit()
    api._jobs[ref].update(pos_ext="POS-TEST", store_ext="STORE-TEST", qr_url="https://example.test/qr")
    closures = []

    def crear(*args, **kw):
        # El usuario cancela mientras Mercado Pago responde a PUT.
        response = api.cancelar_checkout(ref)
        assert response == {"ok": True, "status": "cancelling"}
        return True

    monkeypatch.setattr(mp_service, "crear_orden", crear)
    monkeypatch.setattr(
        mp_service, "cerrar_orden_referencia",
        lambda *args, **kw: closures.append(kw.get("pos_ext")) or {"estado": "closed"},
    )
    monkeypatch.setattr(
        mp_service, "verificar_pago_referencia",
        lambda *args, **kw: (_ for _ in ()).throw(
            AssertionError("La cancelación no debe esperar búsqueda de pago")
        ),
    )
    api._run_checkout(ref, cart, 50)

    assert closures == ["POS-TEST"]
    assert counts(database) == (0, 5, 0)
    with database[0]() as conn:
        row = conn.execute(
            "SELECT estado,mp_cancel_requested FROM intrashop_checkouts WHERE id=?", (ref,)
        ).fetchone()
        assert (row["estado"], row["mp_cancel_requested"]) == ("cancelled", 1)
        assert store.available(conn, database[1]) == 5
        assert conn.execute("SELECT COUNT(*) FROM intrashop_ticket_jobs").fetchone()[0] == 0


def test_cancelacion_persistida_impide_venta_confirmada_tardia(database):
    ref, cart = checkout(database, "late-payment-after-cancel")
    with database[0]() as conn:
        conn.execute("BEGIN IMMEDIATE")
        store.request_mp_cancel(conn, ref)
        conn.commit()
    api._jobs[ref]["status"] = "paid"
    api._finalize_sale(ref, cart, 50)
    assert counts(database) == (0, 5, 0)
    with database[0]() as conn:
        assert conn.execute("SELECT COUNT(*) FROM intrashop_ticket_jobs").fetchone()[0] == 0


def test_ticket_confirmado_se_imprime_una_vez(database, monkeypatch, tmp_path):
    from services import intrashop_ticket_service as ticket

    ref, cart = checkout(database, "one-ticket-only")
    with database[0]() as conn:
        conn.execute("BEGIN IMMEDIATE")
        caja_id = conn.execute("SELECT caja_id FROM intrashop_checkouts WHERE id=?", (ref,)).fetchone()[0]
        venta_id = conn.execute(
            "INSERT INTO ventas(caja_id,fecha,total,estado,metodo_pago) "
            "VALUES(?,CURRENT_TIMESTAMP,50,'completada','mercadopago_qr')",
            (caja_id,),
        ).lastrowid
        store.set_status(conn, ref, "completed", venta_id)
        conn.execute(
            "INSERT INTO intrashop_ticket_jobs(venta_id,checkout_id) VALUES (?,?)",
            (venta_id, ref),
        )
        conn.commit()

    called = []
    monkeypatch.setenv("INTRASHOP_PRINT_TICKET", "1")
    monkeypatch.setattr(ticket, "_pdf_ticket", lambda path, *args: path.write_text("ticket de prueba"))
    monkeypatch.setattr(ticket, "_enviar_a_impresora", lambda path: called.append(path))
    monkeypatch.setattr(ticket, "time", ticket.time)
    # Ruta derivada de DB temporal, sin alterar la instalación real.
    db_file = str(tmp_path / "orders.db")
    result1 = ticket.emitir_ticket_venta(db_file, venta_id, ref, cart, 50)
    result2 = ticket.emitir_ticket_venta(db_file, venta_id, ref, cart, 50)
    assert result1["estado"] == "sent"
    assert result2["estado"] == "sent"
    assert len(called) == 1
    assert called[0].is_file()


def test_frontend_descarta_polling_y_cierra_modal_antes_de_llamar_al_servidor():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / "intrashop/src/pages/index.astro").read_text(
        encoding="utf-8",
    )
    assert "function cancelCheckout()" in source
    assert "cerrarPagoCancelado();" in source
    assert "if (id) solicitarCancelacion(id);" in source
    assert 'activeCheckoutId !== id || $("payment-modal").hidden' in source

"""Vínculo inmutable cobro IntraShop -> caja de origen (SQLite aislada)."""
from contextlib import contextmanager
import sqlite3
import threading

import pytest
from fastapi import HTTPException

from database_manager import DatabaseManager
import intrashop_api as api
import intrashop_checkout_store as store
from intrashop_entregas import ensure_schema as ensure_entregas


@pytest.fixture
def network_db(tmp_path, monkeypatch):
    path = str(tmp_path / "cajas_origen.db")
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
        if "disponible_tienda" not in {
            r[1] for r in conn.execute("PRAGMA table_info(productos)")
        }:
            conn.execute(
                "ALTER TABLE productos ADD COLUMN disponible_tienda INTEGER NOT NULL DEFAULT 0"
            )
        pid = conn.execute(
            "INSERT INTO productos(codigo,descripcion,precio_lista,stock_actual,disponible_tienda) "
            "VALUES ('CAJA-TEST','Producto origen',10,5,1)"
        ).lastrowid
        c1 = conn.execute(
            "INSERT INTO cajas (fecha_apertura,importe_apertura,estado) "
            "VALUES(CURRENT_TIMESTAMP,0,'abierta')"
        ).lastrowid
        c2 = conn.execute(
            "INSERT INTO cajas (fecha_apertura,importe_apertura,estado) "
            "VALUES(CURRENT_TIMESTAMP,0,'abierta')"
        ).lastrowid
        store.ensure_schema(conn)
        ensure_entregas(conn)
        conn.execute(
            "INSERT INTO intrashop_totems(id,nombre) VALUES('totem-test','Tótem prueba')"
        )
        conn.execute(
            "INSERT INTO intrashop_mp_bindings "
            "(terminal_id,terminal_type,pos_external_id,store_external_id,qr_url,caja_id) "
            "VALUES ('totem-test','totem','POS-TEST','STORE-TEST','https://example.test/qr',?)",
            (c1,),
        )
        conn.commit()

    monkeypatch.setattr(api, "_connect", connect)
    monkeypatch.setattr(api, "_save_internal_receipt", lambda *args: None)
    monkeypatch.setattr(api.settings, "mp_activo", True)
    api._jobs.clear()
    api._cancel_events.clear()
    api._reconciling.clear()
    return connect, pid, c1, c2


def reserve(db, checkout_id="checkout-one", mp_api="orders_v1"):
    connect, pid, *_ = db
    cart = [{
        "producto_id": pid, "cantidad": 2,
        "descripcion": "Producto origen", "precio_unitario": 10,
    }]
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        binding = store.reserve(
            conn, checkout_id, "totem-test", cart, 20, mp_api=mp_api
        )
        conn.commit()
    return binding, cart


def paid_job(db, checkout_id, cart):
    api._jobs[checkout_id] = {
        "status": "paid", "sale_done": False, "totem_id": "totem-test",
        "totem_nombre": "Tótem prueba", "items": cart, "total": 20,
    }


def test_asignacion_explicita_guarda_caja_y_finaliza_venta_en_origen(network_db):
    connect, pid, c1, c2 = network_db
    binding, cart = reserve(network_db)
    assert binding["caja_id"] == c1
    with connect() as conn:
        saved = conn.execute(
            "SELECT caja_id FROM intrashop_checkouts WHERE id='checkout-one'"
        ).fetchone()
        assert saved["caja_id"] == c1

    # Aunque exista otra caja abierta más reciente, nunca se usa como destino.
    paid_job(network_db, "checkout-one", cart)
    api._finalize_sale("checkout-one", cart, 20)
    with connect() as conn:
        sale = conn.execute("SELECT caja_id FROM ventas").fetchone()
        checkout = conn.execute(
            "SELECT estado,venta_id,caja_id FROM intrashop_checkouts"
        ).fetchone()
        stock = conn.execute(
            "SELECT stock_actual FROM productos WHERE id=?", (pid,)
        ).fetchone()[0]
        deliveries = conn.execute("SELECT COUNT(*) FROM intrashop_entregas").fetchone()[0]
    assert sale["caja_id"] == c1 != c2
    assert checkout["estado"] == "completed" and checkout["venta_id"]
    assert checkout["caja_id"] == c1 and stock == 3 and deliveries == 1

    # Reintento idempotente: nunca otra venta ni otro descuento.
    api._finalize_sale("checkout-one", cart, 20)
    with connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM ventas").fetchone()[0] == 1


def test_multicaja_sin_vinculo_explicito_rechaza_el_checkout(network_db):
    connect, pid, c1, c2 = network_db
    with connect() as conn:
        conn.execute("UPDATE intrashop_mp_bindings SET caja_id=NULL")
        conn.commit()
    with pytest.raises(ValueError, match="caja definida"):
        reserve(network_db)
    with connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM intrashop_checkouts").fetchone()[0] == 0


def test_auto_compatible_con_una_unica_caja_abierta(network_db):
    connect, pid, c1, c2 = network_db
    with connect() as conn:
        conn.execute("UPDATE intrashop_mp_bindings SET caja_id=NULL")
        conn.execute("UPDATE cajas SET estado='cerrada' WHERE id=?", (c2,))
        conn.commit()
    binding, _ = reserve(network_db)
    assert binding["caja_id"] == c1
    with connect() as conn:
        row = conn.execute("SELECT caja_id FROM intrashop_checkouts").fetchone()
        assert row["caja_id"] == c1


def test_caja_configurada_cerrada_no_permite_crear_nuevo_pago(network_db):
    connect, _, c1, _ = network_db
    with connect() as conn:
        conn.execute("UPDATE cajas SET estado='cerrada' WHERE id=?", (c1,))
        conn.commit()
    with pytest.raises(ValueError, match="no está abierta"):
        reserve(network_db)


def test_caja_cerrada_durante_cobro_retiene_reserva_y_no_mueve_venta(network_db):
    connect, pid, c1, c2 = network_db
    _, cart = reserve(network_db)
    with connect() as conn:
        conn.execute("UPDATE cajas SET estado='cerrada' WHERE id=?", (c1,))
        conn.commit()
    paid_job(network_db, "checkout-one", cart)
    api._finalize_sale("checkout-one", cart, 20)
    with connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM ventas").fetchone()[0] == 0
        row = conn.execute("SELECT estado,caja_id FROM intrashop_checkouts").fetchone()
        assert row["estado"] == "uncertain" and row["caja_id"] == c1
        assert store.available(conn, pid) == 3


def test_checkout_historico_sin_caja_no_se_imputa_al_ultimo_turno(network_db):
    connect, pid, c1, c2 = network_db
    _, cart = reserve(network_db)
    with connect() as conn:
        conn.execute("UPDATE intrashop_checkouts SET caja_id=NULL")
        conn.commit()
    paid_job(network_db, "checkout-one", cart)
    api._finalize_sale("checkout-one", cart, 20)
    with connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM ventas").fetchone()[0] == 0
        assert conn.execute(
            "SELECT estado FROM intrashop_checkouts"
        ).fetchone()["estado"] == "uncertain"


def test_admin_binding_valida_caja_abierta(network_db):
    connect, _, c1, c2 = network_db
    with connect() as conn:
        conn.execute("UPDATE cajas SET estado='cerrada' WHERE id=?", (c2,))
        conn.commit()
    body = api.BindingIn(
        terminal_id="totem-test", terminal_type="totem",
        pos_external_id="POS-TEST", store_external_id="STORE-TEST",
        qr_url="https://example.test/qr", caja_id=c2,
    )
    with pytest.raises(HTTPException) as exc:
        api.asignar_binding(body, operador="admin")
    assert exc.value.status_code == 409
    body.caja_id = c1
    assert api.asignar_binding(body, operador="admin") == {"ok": True}
    with connect() as conn:
        assert conn.execute(
            "SELECT caja_id FROM intrashop_mp_bindings"
        ).fetchone()[0] == c1


def test_api_checkout_devuelve_caja_fijada_sin_crear_cobro_externo(network_db, monkeypatch):
    connect, pid, c1, c2 = network_db
    called = threading.Event()
    monkeypatch.setenv("INTRASHOP_MP_ORDERS_V1", "0")
    monkeypatch.setattr(api, "_run_checkout", lambda *args: called.set())
    result = api.iniciar_checkout(api.CheckoutIn(
        totem_id="totem-test", items=[api.CartItem(producto_id=pid, cantidad=2)],
    ))
    assert result["caja_id"] == c1
    assert called.wait(5)
    with connect() as conn:
        assert conn.execute(
            "SELECT caja_id FROM intrashop_checkouts WHERE id=?",
            (result["checkout_id"],),
        ).fetchone()[0] == c1


def test_conciliacion_orders_tras_reinicio_respeta_caja_de_origen(network_db, monkeypatch):
    connect, pid, c1, c2 = network_db
    _, cart = reserve(network_db, "checkout-reinicio")
    with connect() as conn:
        store.set_mp_order_id(conn, "checkout-reinicio", "ORDREINICIO")
        conn.commit()
    # El worker desapareció, pero la base preservó el vínculo con la caja.
    api._jobs.clear()

    class OrdersAprobadas:
        def consultar(self, order_id, reference, total):
            assert order_id == "ORDREINICIO"
            assert reference == "checkout-reinicio" and total == 20
            return {"estado": "approved", "order_id": order_id}

    monkeypatch.setattr(api, "_orders_client", lambda: OrdersAprobadas())
    result = api._orders_reconcile("checkout-reinicio")
    assert result["estado"] == "completed"
    with connect() as conn:
        sale = conn.execute("SELECT caja_id FROM ventas").fetchone()
        row = conn.execute(
            "SELECT estado,venta_id,caja_id FROM intrashop_checkouts"
        ).fetchone()
    assert sale["caja_id"] == c1
    assert row["estado"] == "completed" and row["caja_id"] == c1
    assert api._orders_reconcile("checkout-reinicio") == {
        "estado": "completed", "venta_id": row["venta_id"],
    }
    with connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM ventas").fetchone()[0] == 1


def test_migracion_legacy_no_inventa_caja_en_checkouts_historicos(tmp_path):
    path = str(tmp_path / "legacy.db")
    with sqlite3.connect(path) as conn:
        conn.execute("""CREATE TABLE intrashop_mp_bindings (
            terminal_id TEXT PRIMARY KEY, terminal_type TEXT NOT NULL,
            pos_external_id TEXT UNIQUE NOT NULL, store_external_id TEXT NOT NULL,
            qr_url TEXT NOT NULL, nombre TEXT NOT NULL DEFAULT ''
        )""")
        conn.execute("""CREATE TABLE intrashop_checkouts (
            id TEXT PRIMARY KEY, totem_id TEXT, pos_external_id TEXT NOT NULL,
            store_external_id TEXT NOT NULL, estado TEXT NOT NULL, total REAL NOT NULL,
            items_json TEXT NOT NULL, created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL, venta_id INTEGER UNIQUE
        )""")
        conn.execute(
            "INSERT INTO intrashop_mp_bindings VALUES"
            "('viejo','totem','POS-LEGACY','STORE-LEGACY','https://example.test/qr','Antiguo')"
        )
        conn.execute(
            "INSERT INTO intrashop_checkouts "
            "(id,totem_id,pos_external_id,store_external_id,estado,total,items_json,created_at,updated_at)"
            " VALUES ('pago-viejo','viejo','POS-LEGACY','STORE-LEGACY','uncertain',100,'[]',1,1)"
        )
        store.ensure_schema(conn)
        store.ensure_schema(conn)
        assert conn.execute(
            "SELECT caja_id FROM intrashop_mp_bindings"
        ).fetchone()[0] is None
        row = conn.execute(
            "SELECT caja_id,estado FROM intrashop_checkouts"
        ).fetchone()
        assert row == (None, "uncertain")


def test_admin_recupera_origen_sin_asignarlo_automaticamente(network_db):
    connect, pid, c1, c2 = network_db
    _, cart = reserve(network_db, "checkout-legacy")
    with connect() as conn:
        conn.execute(
            "UPDATE intrashop_checkouts SET caja_id=NULL,estado='uncertain' "
            "WHERE id='checkout-legacy'"
        )
        conn.commit()

    req = api.AssignOriginCajaIn(
        caja_id=c1, confirmacion="ASIGNAR CAJA A CHECKOUT ANTIGUO"
    )
    with pytest.raises(HTTPException) as err:
        api.assign_checkout_origin_caja(
            "checkout-legacy",
            api.AssignOriginCajaIn(caja_id=c1, confirmacion="incorrecto"),
            operador="admin",
        )
    assert err.value.status_code == 400
    assert api.assign_checkout_origin_caja("checkout-legacy", req, operador="admin") == {
        "ok": True, "caja_id": c1, "requiere_conciliacion": True,
    }
    with connect() as conn:
        row = conn.execute(
            "SELECT caja_id,estado,venta_id FROM intrashop_checkouts "
            "WHERE id='checkout-legacy'"
        ).fetchone()
        audit = conn.execute(
            "SELECT operador,accion FROM intrashop_auditoria WHERE checkout_id='checkout-legacy'"
        ).fetchone()
    assert row["caja_id"] == c1 and row["estado"] == "uncertain"
    assert row["venta_id"] is None
    assert tuple(audit) == ("admin", f"ASIGNACION_CAJA_HISTORICA:{c1}")
    with pytest.raises(HTTPException) as again:
        api.assign_checkout_origin_caja(
            "checkout-legacy",
            api.AssignOriginCajaIn(
                caja_id=c2, confirmacion="ASIGNAR CAJA A CHECKOUT ANTIGUO"
            ),
            operador="admin",
        )
    assert again.value.status_code == 409


def test_admin_no_asigna_caja_cerrada_en_recuperacion(network_db):
    connect, _, c1, c2 = network_db
    reserve(network_db, "checkout-legacy")
    with connect() as conn:
        conn.execute(
            "UPDATE intrashop_checkouts SET caja_id=NULL WHERE id='checkout-legacy'"
        )
        conn.execute("UPDATE cajas SET estado='cerrada' WHERE id=?", (c2,))
        conn.commit()
    with pytest.raises(HTTPException) as err:
        api.assign_checkout_origin_caja(
            "checkout-legacy",
            api.AssignOriginCajaIn(
                caja_id=c2, confirmacion="ASIGNAR CAJA A CHECKOUT ANTIGUO"
            ),
            operador="admin",
        )
    assert err.value.status_code == 409
    with connect() as conn:
        assert conn.execute(
            "SELECT caja_id FROM intrashop_checkouts WHERE id='checkout-legacy'"
        ).fetchone()[0] is None


def test_cierre_solo_bloquea_caja_del_checkout(network_db, monkeypatch):
    import api_server as pos_api

    connect, pid, c1, c2 = network_db
    reserve(network_db, "checkout-per-caja")
    path = None
    with connect() as conn:
        path = conn.execute("PRAGMA database_list").fetchone()[2]
    monkeypatch.setattr(pos_api, "DB_PATH", path)
    monkeypatch.setattr(pos_api, "API_KEY", "TEST-KEY")

    # QR pendiente pertenece a caja 1. Caja 2 puede cerrar sin afectarlo.
    assert pos_api.cerrar_caja(c2, x_api_key="TEST-KEY") == {"ok": True}
    with pytest.raises(HTTPException) as err:
        pos_api.cerrar_caja(c1, x_api_key="TEST-KEY")
    assert err.value.status_code == 409
    with connect() as conn:
        assert conn.execute(
            "SELECT estado FROM cajas WHERE id=?", (c1,)
        ).fetchone()[0] == "abierta"
        store.set_status(conn, "checkout-per-caja", "cancelled")
        conn.commit()
    assert pos_api.cerrar_caja(c1, x_api_key="TEST-KEY") == {"ok": True}

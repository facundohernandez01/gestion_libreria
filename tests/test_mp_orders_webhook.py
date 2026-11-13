"""Webhook Orders con firma verificada. Notificaciones no acreditan por body."""
import hashlib
import hmac
import json
from contextlib import contextmanager
import sqlite3
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

import intrashop_api as api
import intrashop_checkout_store as checkout
from services.mp_orders_webhook import verify_orders_signature


def _signature(secret, order_id, request_id, timestamp):
    manifest = f"id:{order_id};request-id:{request_id};ts:{timestamp};"
    digest = hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()
    return f"ts={timestamp},v1={digest}"


def test_firma_contrato_hmac():
    secret, order_id, req, ts = "SECRET_TEST", "ORDTEST01", "request-1", "1763000000000"
    sig = _signature(secret, order_id, req, ts)
    assert verify_orders_signature(secret, order_id, req, sig)
    assert not verify_orders_signature(secret, order_id, "alterado", sig)
    assert not verify_orders_signature(secret, "ORDOTRA", req, sig)
    assert not verify_orders_signature("OTRA_CLAVE", order_id, req, sig)
    assert not verify_orders_signature(secret, order_id, req, "ts=1,v1=123")


@pytest.fixture
def webhook(tmp_path, monkeypatch):
    dbpath = str(tmp_path / "webhook.db")

    @contextmanager
    def connect():
        conn = sqlite3.connect(dbpath, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    with connect() as conn:
        checkout.ensure_schema(conn)
        conn.execute(
            "INSERT INTO intrashop_checkouts "
            "(id,totem_id,pos_external_id,store_external_id,estado,total,"
            "items_json,created_at,updated_at,mp_api,mp_order_id) "
            "VALUES('checkout-1','totem','POS','STORE','waiting',50,'[]',1,1,"
            "'orders_v1','ORDTEST01')"
        )
        conn.commit()

    monkeypatch.setenv("MP_ORDERS_WEBHOOK_SECRET", "SECRET_TEST")
    monkeypatch.setattr(api, "_connect", connect)
    reconciliations = []
    monkeypatch.setattr(
        api, "_reconcile_signed_order_notification",
        lambda checkout_id, order_id: reconciliations.append((checkout_id, order_id)),
    )
    app = FastAPI()
    app.include_router(api.router)
    return TestClient(app), reconciliations


def _send(client, order_id="ORDTEST01", secret="SECRET_TEST",
          body_order="ORDTEST01", signature=True, reference=None):
    req = "request-1"
    ts = str(int(time.time() * 1000))
    headers = {"x-request-id": req}
    if signature:
        headers["x-signature"] = _signature(secret, order_id, req, ts)
    return client.post(
        "/tienda/webhooks/mercadopago/orders",
        params={"type": "order", "data.id": order_id},
        headers=headers,
        json={"type": "order", "action": "order.processed",
              "data": {"id": body_order, "status": "processed",
                       "external_reference": reference}},
    )


def test_webhook_valido_agenda_reconciliacion_por_id(webhook):
    client, reconciliations = webhook
    response = _send(client)
    assert response.status_code == 200
    assert reconciliations == [("checkout-1", "ORDTEST01")]


def test_webhook_firma_falsa_rechazada(webhook):
    client, reconciliations = webhook
    assert _send(client, secret="FALSE_SECRET").status_code == 401
    assert _send(client, signature=False).status_code == 401
    assert reconciliations == []


def test_webhook_body_no_coincidente_rechazado(webhook):
    client, reconciliations = webhook
    assert _send(client, body_order="ORDSPOOF").status_code == 400
    assert reconciliations == []


def test_webhook_firmado_de_orden_desconocida_no_toca_ventas(webhook):
    client, reconciliations = webhook
    assert _send(client, order_id="ORDUNKNOWN", body_order="ORDUNKNOWN").status_code == 200
    assert reconciliations == []


def test_webhook_con_referencia_firmada_recupera_id_perdido(webhook, monkeypatch):
    client, reconciliations = webhook
    with api._connect() as conn:
        conn.execute(
            "UPDATE intrashop_checkouts SET mp_order_id=NULL WHERE id='checkout-1'"
        )
        conn.commit()
    recovered = []
    monkeypatch.setattr(
        api, "_recover_missing_order_id_from_webhook",
        lambda ref, order_id: recovered.append((ref, order_id)),
    )
    assert _send(client, reference="checkout-1").status_code == 200
    assert recovered == [("checkout-1", "ORDTEST01")]
    assert reconciliations == []


def test_webhook_no_asocia_order_sin_get_verificado(webhook, monkeypatch):
    client, reconciliations = webhook
    with api._connect() as conn:
        conn.execute(
            "UPDATE intrashop_checkouts SET mp_order_id=NULL WHERE id='checkout-1'"
        )
        conn.commit()

    class FakeOrders:
        def consultar(self, order_id, reference, total):
            return {"estado": "uncertain", "motivo": "Importe incorrecto"}

    monkeypatch.setattr(api, "_orders_client", lambda: FakeOrders())
    api._recover_missing_order_id_from_webhook("checkout-1", "ORDTEST01")
    with api._connect() as conn:
        assert conn.execute(
            "SELECT mp_order_id FROM intrashop_checkouts WHERE id='checkout-1'"
        ).fetchone()[0] is None


def test_webhook_recupera_id_tras_get_valido(webhook, monkeypatch):
    client, reconciliations = webhook
    with api._connect() as conn:
        conn.execute(
            "UPDATE intrashop_checkouts SET mp_order_id=NULL WHERE id='checkout-1'"
        )
        conn.commit()

    class FakeOrders:
        def consultar(self, order_id, reference, total):
            assert (order_id, reference, total) == ("ORDTEST01", "checkout-1", 50)
            return {"estado": "pending", "order_id": order_id}

    done = []
    monkeypatch.setattr(api, "_orders_client", lambda: FakeOrders())
    monkeypatch.setattr(
        api, "_orders_reconcile",
        lambda ref: done.append(ref) or {"estado": "pending"},
    )
    api._recover_missing_order_id_from_webhook("checkout-1", "ORDTEST01")
    with api._connect() as conn:
        assert conn.execute(
            "SELECT mp_order_id FROM intrashop_checkouts WHERE id='checkout-1'"
        ).fetchone()[0] == "ORDTEST01"
    assert done == ["checkout-1"]

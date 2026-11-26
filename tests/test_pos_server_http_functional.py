"""E2E HTTP local con FastAPI real, SQLite temporal y navegador simulado.

No toca libreria.db, no utiliza una cuenta Mercado Pago ni hace ping real.
"""
import sqlite3

import pytest
from fastapi.testclient import TestClient

import api_server as server
import intrashop_api as tienda
from database_manager import DatabaseManager
from intrashop_entregas import ensure_schema as ensure_totems
from services.intrashop_totem_registry import vincular_ip
from services.intrashop_totem_auth import generar_codigo


@pytest.fixture
def api_db(tmp_path, monkeypatch):
    path = str(tmp_path / "functional-http.db")
    DatabaseManager(path)
    monkeypatch.setattr(server, "DB_PATH", path)
    monkeypatch.setattr(server, "API_KEY", "TEST-INTRA-HTTP-KEY")
    monkeypatch.setattr(tienda, "DB_PATH", path)
    monkeypatch.setattr(tienda.settings, "mp_activo", True)
    with sqlite3.connect(path) as c:
        c.row_factory = sqlite3.Row
        ensure_totems(c)
        conn_ip = "192.168.35.40"
        vincular_ip(c, "totem-001", conn_ip)
        from intrashop_checkout_store import ensure_schema
        ensure_schema(c)
        c.execute(
            """INSERT INTO intrashop_mp_bindings
               (terminal_id,terminal_type,pos_external_id,store_external_id,qr_url)
               VALUES('totem-001','totem','POS-TEST','STORE-TEST','https://example.com/qr')"""
        )
        code = generar_codigo(c, "totem-001")
        c.execute(
            """INSERT INTO intrashop_checkouts
               (id,totem_id,pos_external_id,store_external_id,estado,total,items_json,created_at,updated_at)
               VALUES('test-checkout','totem-001','POS-TEST','STORE-TEST','cancelled',10,'[]',1,1)"""
        )
        c.commit()
    return path, code


def test_http_emparejamiento_y_bloqueo_qr_ajeno(api_db):
    path, code = api_db
    try:
        client = TestClient(server.app, client=("192.168.35.40", 52000))
    except TypeError:
        pytest.skip("TestClient instalado sin parámetro client; smoke de servicio cubierto")
    identidad = client.get("/tienda/totems/identity")
    assert identidad.status_code == 200
    assert identidad.json()["paired"] is True
    assert identidad.json()["authorized"] is False

    blocked = client.get("/tienda/checkout/test-checkout")
    assert blocked.status_code == 403
    blocked_cancel = client.post("/tienda/checkout/test-checkout/cancel")
    assert blocked_cancel.status_code == 403

    paired = client.post("/tienda/totems/pair", json={"codigo": code})
    assert paired.status_code == 200, paired.text
    assert "httponly" in paired.headers["set-cookie"].lower()
    assert "samesite=strict" in paired.headers["set-cookie"].lower()
    assert client.get("/tienda/totems/identity").json()["authorized"] is True

    own = client.get("/tienda/checkout/test-checkout")
    assert own.status_code == 200
    assert own.json()["status"] == "cancelled"
    assert client.post("/tienda/checkout/test-checkout/cancel").status_code == 200

    other = TestClient(server.app, client=("192.168.35.41", 52001))
    other.cookies.update(client.cookies)
    assert other.get("/tienda/checkout/test-checkout").status_code == 403


def test_http_arqueo_caja_via_pos_server(api_db):
    path, _ = api_db
    client = TestClient(server.app)
    headers = {"X-API-Key": "TEST-INTRA-HTTP-KEY"}
    opened = client.post(
        "/cajas/abrir?importe_apertura=200&observaciones=Prueba",
        headers=headers,
    )
    assert opened.status_code == 200, opened.text
    cid = opened.json()["id"]
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO ventas(caja_id,total,metodo_pago) VALUES(?,?,?)",
            (cid, 60, "mercadopago_qr"),
        )
        conn.execute(
            "INSERT INTO ventas(caja_id,total,metodo_pago) VALUES(?,?,?)",
            (cid, 25, "efectivo"),
        )
        conn.commit()
    summary = client.get(f"/cajas/{cid}/resumen", headers=headers)
    assert summary.status_code == 200, summary.text
    assert summary.json()["efectivo_esperado"] == 225
    close = client.post(
        f"/cajas/{cid}/cerrar",
        headers=headers,
        json={
            "importe_contado": 225, "observaciones": "",
            "efectivo_esperado": 225, "total_ventas": 85, "total_gastos": 0,
        },
    )
    assert close.status_code == 200, close.text
    assert close.json()["ok"] is True
    assert client.post(f"/cajas/{cid}/cerrar", headers=headers).status_code == 409
    with sqlite3.connect(path) as conn:
        assert conn.execute(
            "SELECT estado FROM cajas WHERE id=?", (cid,)
        ).fetchone()[0] == "cerrada"

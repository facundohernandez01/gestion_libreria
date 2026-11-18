"""Aperturas, caja, ventas y gastos por terminal POS con SQLite descartable.

No usa la base del usuario, claves reales ni servicios Mercado Pago.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import sqlite3
import threading
import time

from fastapi import HTTPException
import httpx
import pytest

import api_server as api
from api_client import ApiClient
from core import terminal_identity
from database_manager import DatabaseManager
import pos_auth


KEY = "TEST-MULTICAJA"
TERM_A = "caja-aa111111"
TERM_B = "caja-bb222222"
TOKEN_A = "test-token-a"
TOKEN_B = "test-token-b"


def headers(terminal=TERM_A, token=TOKEN_A):
    return {
        "x_api_key": KEY, "x_terminal_id": terminal,
        "authorization": "Bearer " + token,
    }


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = str(tmp_path / "cajas-terminal.db")
    DatabaseManager(path)
    with sqlite3.connect(path) as conn:
        pid = conn.execute(
            "INSERT INTO productos(codigo,descripcion,precio_lista,stock_actual) "
            "VALUES ('ITEM-A','Producto multi',10,7)"
        ).lastrowid
    monkeypatch.setattr(api, "DB_PATH", path)
    monkeypatch.setattr(api, "API_KEY", KEY)
    pos_auth._sessions.clear()
    pos_auth._sessions[TOKEN_A] = ("admin", time.time() + 120, True, TERM_A)
    pos_auth._sessions[TOKEN_B] = ("admin", time.time() + 120, True, TERM_B)
    yield path, pid
    pos_auth._sessions.clear()


def _open(terminal=TERM_A, token=TOKEN_A):
    return api.abrir_caja(
        importe_apertura=100, observaciones="Apertura prueba",
        **headers(terminal, token),
    )["id"]


def _sale(caja, pid, qty, terminal=TERM_A, token=TOKEN_A):
    return api.crear_venta(
        api.VentaIn(
            caja_id=caja, items=[
                {"producto_id": pid, "cantidad": qty, "precio_unitario": 10}
            ]
        ),
        **headers(terminal, token),
    )


def _expense(caja, amount, terminal=TERM_A, token=TOKEN_A):
    return api.api_agregar_gasto(
        caja, {"monto": amount, "concepto": "Prueba"},
        **headers(terminal, token),
    )


def test_dos_pos_abren_cajas_independientes_y_ven_solo_su_caja(db):
    path, pid = db
    a, b = _open(), _open(TERM_B, TOKEN_B)
    assert a != b
    assert api.caja_abierta(**headers())["id"] == a
    assert api.caja_abierta(**headers(TERM_B, TOKEN_B))["id"] == b
    with sqlite3.connect(path) as conn:
        filas = conn.execute(
            "SELECT terminal_id, usuario_apertura FROM cajas ORDER BY id"
        ).fetchall()
        assert filas == [(TERM_A, "admin"), (TERM_B, "admin")]
    with pytest.raises(HTTPException) as exc:
        _open()
    assert exc.value.status_code == 409


def test_un_token_de_otra_terminal_no_autoriza_ventas_gastos_ni_cierre(db):
    path, pid = db
    a = _open()
    b = _open(TERM_B, TOKEN_B)
    for fn in (
        lambda: _sale(b, pid, 1),
        lambda: _expense(b, 5),
        lambda: api.cerrar_caja(b, **headers()),
        lambda: api.ventas_dia(b, **headers()),
        lambda: api.api_gastos_caja(b, **headers()),
        lambda: api.caja_abierta(**headers(TERM_B, TOKEN_A)),
        lambda: _sale(a, pid, 1, TERM_B, TOKEN_A),
    ):
        with pytest.raises(HTTPException) as exc:
            fn()
        assert exc.value.status_code == 403
    # Una clave LAN sin sesión no puede operar sobre caja de otra terminal.
    with pytest.raises(HTTPException) as exc:
        api.crear_venta(
            api.VentaIn(caja_id=a, items=[
                {"producto_id": pid, "cantidad": 1, "precio_unitario": 10}
            ]),
            x_api_key=KEY, x_terminal_id="", authorization=None,
        )
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException) as no_token:
        api.abrir_caja(
            importe_apertura=1, x_api_key=KEY, x_terminal_id="caja-nuevo01",
            authorization=None,
        )
    assert no_token.value.status_code == 401
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM ventas").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM gastos").fetchone()[0] == 0


def test_venta_gasto_y_cierre_de_cada_terminal_quedan_separados(db):
    path, pid = db
    a, b = _open(), _open(TERM_B, TOKEN_B)
    _sale(a, pid, 2)
    _sale(b, pid, 1, TERM_B, TOKEN_B)
    _expense(a, 5)
    _expense(b, 2, TERM_B, TOKEN_B)
    assert api.cerrar_caja(a, "Cierre A", **headers()) == {"ok": True}
    assert api.caja_abierta(**headers()) is None
    assert api.caja_abierta(**headers(TERM_B, TOKEN_B))["id"] == b
    with sqlite3.connect(path) as conn:
        row_a = conn.execute(
            "SELECT importe_cierre,total_ventas,total_gastos,usuario_cierre,estado "
            "FROM cajas WHERE id=?", (a,),
        ).fetchone()
        assert row_a == (115, 20, 5, "admin", "cerrada")
    assert api.cerrar_caja(b, "Cierre B", **headers(TERM_B, TOKEN_B)) == {"ok": True}
    with sqlite3.connect(path) as conn:
        row_b = conn.execute(
            "SELECT importe_cierre,total_ventas,total_gastos,estado "
            "FROM cajas WHERE id=?", (b,),
        ).fetchone()
        assert row_b == (108, 10, 2, "cerrada")


def test_ventas_paralelas_comparten_stock_sin_sobreventa(db):
    path, pid = db
    a, b = _open(), _open(TERM_B, TOKEN_B)
    barrier = threading.Barrier(2)

    def do_sale(caja, term, token):
        barrier.wait(timeout=10)
        try:
            return _sale(caja, pid, 4, term, token)["venta_id"]
        except HTTPException as exc:
            return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(
            lambda args: do_sale(*args),
            [(a, TERM_A, TOKEN_A), (b, TERM_B, TOKEN_B)],
        ))
    assert sum(1 for x in results if x == 409) == 1
    assert sum(1 for x in results if x != 409) == 1
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT stock_actual FROM productos").fetchone()[0] == 3
        assert conn.execute("SELECT COUNT(*) FROM ventas").fetchone()[0] == 1


def test_aperturas_simultaneas_misma_terminal_no_duplican(db):
    path, _ = db
    barrier = threading.Barrier(2)

    def open_once(_):
        barrier.wait(timeout=10)
        try:
            return _open()
        except HTTPException as exc:
            return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(open_once, (1, 2)))
    assert sum(1 for value in results if value == 409) == 1
    with sqlite3.connect(path) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM cajas WHERE estado='abierta' AND terminal_id=?",
            (TERM_A,),
        ).fetchone()[0] == 1


def test_legacy_no_es_reclamada_automaticamente_y_adopcion_auditada(db):
    path, _ = db
    with sqlite3.connect(path) as conn:
        legacy = conn.execute(
            "INSERT INTO cajas(fecha_apertura,importe_apertura,estado) "
            "VALUES(CURRENT_TIMESTAMP,50,'abierta')"
        ).lastrowid
    assert api.caja_abierta(**headers()) is None
    with pytest.raises(HTTPException) as exc:
        _open()
    assert exc.value.status_code == 409
    pending = api.cajas_sin_terminal(**headers())
    assert [row["id"] for row in pending] == [legacy]
    with pytest.raises(HTTPException) as exc:
        api.asociar_caja_heredada(
            legacy, api.AdoptCajaIn(confirmacion="NO"), **headers()
        )
    assert exc.value.status_code == 400
    result = api.asociar_caja_heredada(
        legacy, api.AdoptCajaIn(confirmacion="ASOCIAR CAJA EXISTENTE"),
        **headers(),
    )
    assert result["caja_id"] == legacy and result["terminal_id"] == TERM_A
    assert api.caja_abierta(**headers())["id"] == legacy
    with sqlite3.connect(path) as conn:
        assert conn.execute(
            "SELECT operador,accion FROM pos_caja_auditoria WHERE caja_id=?",
            (legacy,),
        ).fetchone() == ("admin", "ASOCIACION_CAJA_HISTORICA")
    _open(TERM_B, TOKEN_B)
    with pytest.raises(HTTPException):
        api.asociar_caja_heredada(
            legacy, api.AdoptCajaIn(confirmacion="ASOCIAR CAJA EXISTENTE"),
            **headers(TERM_B, TOKEN_B),
        )


def test_rol_revocado_no_puede_vender_ni_operar_otra_caja(db):
    path, pid = db
    a = _open()
    with sqlite3.connect(path) as conn:
        conn.execute(
            "UPDATE roles SET es_admin=0,permisos='{}' WHERE nombre='ADMIN'"
        )
        conn.commit()
    with pytest.raises(HTTPException) as exc:
        _sale(a, pid, 1)
    assert exc.value.status_code == 403


def test_identidad_pos_cliente_es_local_estable_y_no_usa_sqlite(tmp_path, monkeypatch):
    file_path = tmp_path / "identidad" / "terminal"
    monkeypatch.setattr(terminal_identity, "_identity_path", lambda: file_path)
    import core.db_factory as factory
    monkeypatch.setattr(factory, "modo_actual", lambda: "cliente")
    a = terminal_identity.terminal_id()
    b = terminal_identity.terminal_id()
    assert a == b and a.startswith("caja-")
    assert file_path.read_text().strip() == a
    assert not list(tmp_path.rglob("*.db"))
    other = tmp_path / "otro" / "terminal"
    monkeypatch.setattr(terminal_identity, "_identity_path", lambda: other)
    assert terminal_identity.terminal_id() != a


def test_cliente_http_envia_sesion_y_terminal_sin_claves_en_url(monkeypatch):
    from adapters.entregas import set_session
    monkeypatch.setattr(terminal_identity, "terminal_id", lambda: TERM_A)
    set_session("AUTH-SESSION")
    captured = []

    def fake_post(url, **kwargs):
        captured.append((url, kwargs))
        request = httpx.Request("POST", url)
        return httpx.Response(200, json={"id": 11}, request=request)

    monkeypatch.setattr(httpx, "post", fake_post)
    client = ApiClient("http://127.0.0.1:8000", KEY)
    try:
        assert client.abrir_caja(1, "Prueba") == 11
        url, kwargs = captured[0]
        assert "api_key" not in url.lower() and "auth-session" not in url.lower()
        assert kwargs["headers"]["X-Terminal-Id"] == TERM_A
        assert kwargs["headers"]["Authorization"] == "Bearer AUTH-SESSION"
        assert kwargs["headers"]["X-API-Key"] == KEY
    finally:
        set_session(None)



def test_items_y_facturacion_no_permiten_acceder_a_ventas_de_otra_caja(db):
    path, pid = db
    a, b = _open(), _open(TERM_B, TOKEN_B)
    venta_a = _sale(a, pid, 1)["venta_id"]
    assert len(api.items_venta(venta_a, **headers())) == 1
    with pytest.raises(HTTPException) as err:
        api.items_venta(venta_a, **headers(TERM_B, TOKEN_B))
    assert err.value.status_code == 403

    factura = api.FacturaIn(
        venta_id=venta_a, numero_factura="TEST-001",
        cae="CAETEST", vencimiento_cae="2026-11-30",
    )
    with pytest.raises(HTTPException) as err:
        api.actualizar_factura(factura, **headers(TERM_B, TOKEN_B))
    assert err.value.status_code == 403
    with sqlite3.connect(path) as conn:
        assert conn.execute(
            "SELECT numero_factura FROM ventas WHERE id=?", (venta_a,)
        ).fetchone()[0] is None

    assert api.actualizar_factura(factura, **headers()) == {"ok": True}
    with sqlite3.connect(path) as conn:
        assert conn.execute(
            "SELECT numero_factura FROM ventas WHERE id=?", (venta_a,)
        ).fetchone()[0] == "TEST-001"


def test_fastapi_http_apertura_autenticada_y_rechazo_por_terminal(db):
    from fastapi.testclient import TestClient
    client = TestClient(api.app)  # sin lifespan: no iniciar reconciliaciones de MP
    auth_a = {
        "X-API-Key": KEY,
        "X-Terminal-Id": TERM_A,
        "Authorization": "Bearer " + TOKEN_A,
    }
    auth_b = {
        "X-API-Key": KEY,
        "X-Terminal-Id": TERM_B,
        "Authorization": "Bearer " + TOKEN_B,
    }
    opened = client.post(
        "/cajas/abrir", params={"importe_apertura": 10},
        headers=auth_a,
    )
    assert opened.status_code == 200, opened.text
    caja = opened.json()["id"]
    assert client.get("/cajas/abierta", headers=auth_a).json()["id"] == caja
    assert client.get("/cajas/abierta", headers=auth_b).json() is None
    assert client.post("/cajas/abrir", params={
        "importe_apertura": 20
    }, headers=auth_b).status_code == 200
    assert client.post(
        f"/cajas/{caja}/cerrar", headers=auth_b,
    ).status_code == 403
    assert client.post(
        f"/cajas/{caja}/cerrar", headers={
            "X-API-Key": KEY, "X-Terminal-Id": TERM_A,
            "Authorization": "Bearer " + TOKEN_B,
        },
    ).status_code == 403
    assert client.post(
        f"/cajas/{caja}/cerrar", headers=auth_a,
    ).status_code == 200



def test_login_pos_real_preserva_una_sola_sesion_y_accede_a_su_caja(db, monkeypatch):
    """Reproduce el 200/login seguido del 403/cajas de la interfaz Flet."""
    from fastapi.testclient import TestClient
    from adapters import entregas
    from core.pos_operator_session import preparar_sesion_operador

    db_path, product_id = db
    monkeypatch.setattr(pos_auth, "DatabaseManager", lambda: DatabaseManager(db_path))
    monkeypatch.setattr(terminal_identity, "terminal_id", lambda: TERM_A)
    asgi = TestClient(api.app)
    calls = []

    def proxy_post(url, **kwargs):
        calls.append(("POST", url, kwargs))
        assert url.startswith("http://127.0.0.1:8000/")
        return asgi.post(
            url.removeprefix("http://127.0.0.1:8000"),
            json=kwargs.get("json"), params=kwargs.get("params"),
            headers=kwargs.get("headers"),
        )

    def proxy_get(url, **kwargs):
        calls.append(("GET", url, kwargs))
        return asgi.get(
            url.removeprefix("http://127.0.0.1:8000"),
            params=kwargs.get("params"), headers=kwargs.get("headers"),
        )

    monkeypatch.setattr(httpx, "post", proxy_post)
    monkeypatch.setattr(httpx, "get", proxy_get)
    client = ApiClient("http://127.0.0.1:8000", KEY)
    try:
        user = client.autenticar_usuario("admin", "admin")
        assert user and user["es_admin"]
        first_token = entregas._session_token
        assert first_token
        assert preparar_sesion_operador("cliente", "admin", "admin")
        assert entregas._session_token == first_token
        assert len([request for request in calls if "/pos/auth/login" in request[1]]) == 1
        assert calls[0][2]["headers"]["X-Terminal-Id"] == TERM_A

        # La petición de caja debe aceptar el bearer del PR #5, no dar 403.
        assert client.obtener_caja_abierta() is None
        caja_id = client.abrir_caja(100, "Turno de prueba")
        assert caja_id > 0
        assert client.obtener_caja_abierta()["id"] == caja_id
        venta_id, ok = client.crear_venta(
            caja_id, [{"producto_id": product_id, "cantidad": 1,
                       "precio_unitario": 10}],
        )
        assert ok and venta_id > 0
        assert client.obtener_ventas_del_dia(caja_id)[0]["id"] == venta_id
        assert client.cerrar_caja(caja_id)
        client.cerrar_sesion_remota()
        assert entregas._session_token is None
        assert client.autenticar_usuario("admin", "contraseña inválida") is None
        assert entregas._session_token is None
    finally:
        entregas.set_session(None)


def test_formulario_login_no_emite_un_segundo_bearer_sin_terminal():
    """Evita que un cambio de UI vuelva a sobrescribir el bearer válido."""
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] /
              "componente_login.py").read_text(encoding="utf-8")
    assert '"/pos/auth/login"' not in source
    assert 'preparar_sesion_operador(' in source
    assert 'modo != "cliente"' in source

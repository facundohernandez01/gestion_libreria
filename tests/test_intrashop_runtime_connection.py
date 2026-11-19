"""Regresiones de conexión LAN, login POS y publicación Astro.

Usa SQLite temporal y respuestas HTTP simuladas. Nunca modifica libreria.db.
"""
from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import httpx
import pytest

from api_client import ApiClient
from core import db_factory
from database_manager import DatabaseManager

ROOT = Path(__file__).resolve().parents[1]


def test_intrashop_cliente_respeta_url_guardada_en_terminal(tmp_path, monkeypatch):
    monkeypatch.setenv("POS_API_ONLY", "0")
    monkeypatch.setenv("INTRASHOP_EDITION", "1")
    monkeypatch.setenv("SERVER_URL", "http://127.0.0.1:9999")
    path = tmp_path / "preferencias-terminal.db"
    monkeypatch.setattr(db_factory.settings, "db_path", str(path))
    monkeypatch.setattr(db_factory.settings, "server_url", "http://127.0.0.1:9999")
    db = DatabaseManager(str(path))
    db.set_config("SERVER_URL", "http://192.168.10.25:8000")

    assert db_factory.modo_actual() == "cliente"
    assert db_factory._server_url() == "http://192.168.10.25:8000"
    client, mode = db_factory.crear_acceso_datos()
    assert mode == "cliente"
    assert isinstance(client, ApiClient)
    assert client.base_url == "http://192.168.10.25:8000"


def _login_validator():
    # El módulo visual importa Flet, no instalado en el job ligero de CI.
    # Extraer SOLO la función para probar su lógica sin dependencias gráficas.
    tree = ast.parse((ROOT / "componente_login.py").read_text(encoding="utf-8"))
    fn = next(x for x in tree.body if isinstance(x, ast.FunctionDef)
              and x.name == "validar_login")
    ns = {"_USUARIO_DEFAULT": "admin", "_CLAVE_DEFAULT": "admin"}
    exec(compile(ast.Module(body=[fn], type_ignores=[]),
                 "componente_login.py", "exec"), ns)
    return ns["validar_login"]


class FalsoServidorRechazaLogin:
    def autenticar_usuario(self, usuario, clave):
        return None

    def get_config_value(self, key):
        # Simula credenciales antiguas locales. No autorizan acceso remoto.
        return {"LOGIN_USUARIO": "admin", "LOGIN_CLAVE": "admin"}.get(key)


def test_cliente_no_autentica_con_clave_de_config_local(monkeypatch):
    monkeypatch.setenv("INTRASHOP_EDITION", "1")
    assert _login_validator()(FalsoServidorRechazaLogin(), "admin", "admin") is False


def test_local_mantiene_fallback_compatibilidad(tmp_path, monkeypatch):
    monkeypatch.setenv("POS_API_ONLY", "0")
    monkeypatch.setenv("INTRASHOP_EDITION", "0")
    monkeypatch.setenv("MODO_RED", "local")
    monkeypatch.setattr(db_factory.settings, "db_path", str(tmp_path / "local.db"))
    assert _login_validator()(FalsoServidorRechazaLogin(), "admin", "admin") is True


def test_auth_cliente_distingue_rechazo_401_de_caida_servidor(monkeypatch):
    monkeypatch.setattr("core.terminal_identity.terminal_id", lambda: "terminal-ci")
    client = ApiClient("http://127.0.0.1:8000", "clave-de-prueba")

    monkeypatch.setattr(httpx, "post", lambda *a, **kw: httpx.Response(
        401, request=httpx.Request("POST", "http://127.0.0.1:8000/pos/auth/login")))
    assert client.autenticar_usuario("admin", "incorrecta") is None

    def disconnected(*args, **kwargs):
        raise httpx.ConnectError("sin conexión",
            request=httpx.Request("POST", "http://127.0.0.1:8000/pos/auth/login"))
    monkeypatch.setattr(httpx, "post", disconnected)
    with pytest.raises(ConnectionError, match="No se pudo conectar a POS Server"):
        client.autenticar_usuario("admin", "clave")

    monkeypatch.setattr(httpx, "post", lambda *a, **kw: httpx.Response(
        503, request=httpx.Request("POST", "http://127.0.0.1:8000/pos/auth/login")))
    with pytest.raises(RuntimeError, match="HTTP 503"):
        client.autenticar_usuario("admin", "clave")


def test_tienda_se_sirve_aunque_build_ocurra_despues_del_arranque(tmp_path, monkeypatch):
    import api_server

    dist = tmp_path / "dist"
    monkeypatch.setattr(api_server, "INTRASHOP_DIST", dist)
    static = api_server.AstroStaticFiles(
        directory=str(dist), check_dir=False, html=True
    )
    scope = {"type": "http", "method": "GET", "path": "/intrashop/",
             "root_path": "", "headers": []}

    # Antes del build: diagnóstico claro, no 404 opaco.
    absent = asyncio.run(static.get_response("", scope))
    assert absent.status_code == 503
    assert any(route.path == "/intrashop" for route in api_server.app.routes)

    # Se compila con el servidor ya iniciado: no es necesario reiniciar.
    dist.mkdir()
    (dist / "index.html").write_text("<h1>IntraShop</h1>", encoding="utf-8")
    (dist / "admin").mkdir()
    (dist / "admin" / "index.html").write_text("<h1>Admin</h1>", encoding="utf-8")
    home = asyncio.run(static.get_response("", scope))
    admin = asyncio.run(static.get_response("admin/", scope))
    assert home.status_code == 200
    assert admin.status_code == 200


@pytest.mark.parametrize("page", ("index.astro", "admin.astro", "entregas.astro"))
def test_logos_web_usan_prefijo_intrashop(page):
    source = (ROOT / "intrashop" / "src" / "pages" / page).read_text(encoding="utf-8")
    assert 'src="/intrashop/intrashop-logo.svg"' in source
    assert 'src="/intrashop-logo.svg"' not in source

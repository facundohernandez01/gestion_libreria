"""HTTPS LAN end-to-end (ASGI) y configuración de proxy; sin red real."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import api_server as server
from services import lan_https
from services.intrashop_totem_registry import ip_cliente


def test_tls_off_sigue_modo_lan_legacy(monkeypatch):
    monkeypatch.delenv("INTRASHOP_ENFORCE_HTTPS", raising=False)
    monkeypatch.delenv("POS_PUBLIC_URL", raising=False)
    assert lan_https.host_backend("0.0.0.0") == "0.0.0.0"
    assert lan_https.opciones_uvicorn() == {"proxy_headers": False}
    assert lan_https.url_visible("192.168.1.100", 8000) == "http://192.168.1.100:8000"


def test_tls_on_no_expone_backend_y_solo_confia_proxy_local(monkeypatch):
    monkeypatch.setenv("INTRASHOP_ENFORCE_HTTPS", "1")
    monkeypatch.setenv("POS_PUBLIC_URL", "https://pos.home.arpa")
    assert lan_https.host_backend("0.0.0.0") == "127.0.0.1"
    assert lan_https.host_backend("192.168.1.100") == "127.0.0.1"
    assert lan_https.url_visible("192.168.1.100", 8000) == "https://pos.home.arpa"
    opts = lan_https.opciones_uvicorn()
    assert opts["proxy_headers"] is True
    assert opts["forwarded_allow_ips"] == "127.0.0.1,::1"
    assert "*" not in opts["forwarded_allow_ips"]


@pytest.mark.parametrize("url", [
    "", "http://pos.home.arpa", "https://user:secret@pos.home.arpa",
    "https://pos.home.arpa/other/path", "https://pos.home.arpa/?token=abc",
    "https://pos.home.arpa/#fragment", "https://",
])
def test_tls_mal_configurado_no_permite_iniciar_backend(url, monkeypatch):
    monkeypatch.setenv("INTRASHOP_ENFORCE_HTTPS", "1")
    monkeypatch.setenv("POS_PUBLIC_URL", url)
    with pytest.raises(RuntimeError):
        lan_https.host_backend("0.0.0.0")


def test_fastapi_exige_https_incluso_para_login_astros_y_health(monkeypatch):
    monkeypatch.setenv("INTRASHOP_ENFORCE_HTTPS", "1")
    monkeypatch.setenv("POS_PUBLIC_URL", "https://pos.home.arpa")
    client_http = TestClient(server.app, base_url="http://pos.home.arpa")
    for path in (
        "/health", "/intrashop/", "/tienda/productos",
        "/pos/auth/login", "/cajas/abierta",
    ):
        response = client_http.get(path)
        assert response.status_code == 403, (path, response.text)
    # Ningún encabezado enviado por clientes HTTP puede fingir HTTPS;
    # Uvicorn solo acepta forwarded headers del proxy en 127.0.0.1.
    spoofed = client_http.get(
        "/health", headers={"X-Forwarded-Proto": "https",
                            "X-Forwarded-For": "192.168.1.44"},
    )
    assert spoofed.status_code == 403
    client_https = TestClient(server.app, base_url="https://pos.home.arpa")
    response = client_https.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "pos-lan"


def test_ip_cliente_ignora_header_no_confiable():
    class Fake:
        client = type("Client", (), {"host": "192.168.1.20"})()
        headers = {"x-forwarded-for": "192.168.1.40"}
    assert ip_cliente(Fake()) == "192.168.1.20"


def test_astro_no_reusa_url_http_almacenada_si_esta_publicada_tras_proxy():
    root = Path(__file__).resolve().parents[1]
    shop = (root / "intrashop/src/pages/index.astro").read_text()
    admin = (root / "intrashop/src/pages/admin.astro").read_text()
    assert "const servedByPosServer =" in shop
    assert "? window.location.origin" in shop
    assert "? location.origin" in admin
    assert "const defaultUrl = deployed ? origin" in admin


def test_consola_y_cli_respetan_backend_de_loopback():
    root = Path(__file__).resolve().parents[1]
    for name in ("pos_server.py", "server_manager.py", "pos_server_gui.py"):
        src = (root / name).read_text()
        assert "host_backend(" in src
    assert "url_visible(" in (root / "server_manager.py").read_text()
    caddy = (root / "deploy/Caddyfile.intrashop-lan.example").read_text()
    assert "tls internal" in caddy
    assert "reverse_proxy 127.0.0.1:8000" in caddy

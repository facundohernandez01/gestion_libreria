"""Preferencias LAN del POS cliente: persistencia real fuera de SQLite."""
from pathlib import Path

import pytest

from core import pos_client_settings as prefs
from core import db_factory


@pytest.fixture
def configured(tmp_path, monkeypatch):
    config = tmp_path / "config" / "pos-server.json"
    monkeypatch.setattr(prefs, "_config_path", lambda: config)
    monkeypatch.delenv("POS_API_ONLY", raising=False)
    monkeypatch.setenv("INTRASHOP_EDITION", "1")
    monkeypatch.setenv("SERVER_URL", "http://127.0.0.1:8000")
    yield config


def test_dialog_setting_overrides_default_and_persists_on_reopen(configured):
    assert db_factory._server_url() == "http://127.0.0.1:8000"
    url = "http://192.0.2.40:8000/"
    assert prefs.guardar_server_url(url) == "http://192.0.2.40:8000"
    assert configured.exists()
    assert db_factory._server_url() == "http://192.0.2.40:8000"
    assert prefs.leer_server_url() == "http://192.0.2.40:8000"
    assert "api_key" not in configured.read_text().lower()
    assert not list(configured.parent.rglob("*.db"))


@pytest.mark.parametrize("url", [
    "http://admin:1234@192.0.2.50:8000",
    "http://192.0.2.50:8000/?api_key=secreto",
    "https://example.test:8000/admin",
    "http://192.0.2.50:bad-port",
    "http://0.0.0.0:8000",
    "file:///etc/passwd",
    "https://example.test:8000/#token",
    "192.0.2.50:8000",
    "",
])
def test_url_insegura_no_se_guarda(configured, url):
    with pytest.raises(ValueError):
        prefs.guardar_server_url(url)
    assert not configured.exists()


def test_guardar_otra_url_no_modifica_db_ni_identidad(configured):
    first = prefs.guardar_server_url("http://192.0.2.1:8000")
    second = prefs.guardar_server_url("https://pos.example.test:8443")
    assert first != second
    assert db_factory._server_url() == second
    assert list(configured.parent.iterdir()) == [configured]


def test_direccion_guardada_no_existe_en_modo_legacy(configured, monkeypatch):
    prefs.guardar_server_url("http://192.0.2.2:8000")
    monkeypatch.setenv("POS_API_ONLY", "1")
    # La edición servidor/local no debe usar la URL de un cliente remoto.
    assert not db_factory.es_edicion_intrashop()


def test_dialog_carga_preferencia_sin_crear_sqlite_local():
    source = (Path(__file__).resolve().parents[1] /
              "componente_login.py").read_text(encoding="utf-8")
    assert "guardar_server_url(url.value or" in source
    assert "es_cliente_intrashop" in source
    assert "disabled=es_cliente_intrashop" in source

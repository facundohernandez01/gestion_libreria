"""Integración funcional sin LAN real, MP real ni escritura a libreria.db."""
from contextlib import contextmanager
import sqlite3
import types

import pytest

from database_manager import DatabaseManager
from intrashop_entregas import ensure_schema as ensure_totems
import intrashop_checkout_store as checkout_store
from services import intrashop_totem_auth as auth
from services.intrashop_totem_registry import vincular_ip, desvincular_ip, retirar_totem
from services import lan_discovery


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "lan-functional.db")
    DatabaseManager(path)

    @contextmanager
    def connect():
        conn = sqlite3.connect(path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
        finally:
            conn.close()

    with connect() as c:
        ensure_totems(c)
        checkout_store.ensure_schema(c)
        c.commit()
    return connect


def test_codigo_de_uso_unico_y_cookie_http_only_en_backend(db):
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        vincular_ip(conn, "totem-001", "192.168.33.81")
        codigo = auth.generar_codigo(conn, "totem-001")
        conn.commit()
        assert len(codigo.replace("-", "")) == 10
        row = conn.execute(
            "SELECT code_hash FROM intrashop_totem_pair_codes WHERE totem_id='totem-001'"
        ).fetchone()
        assert row["code_hash"] != codigo.replace("-", "")
        assert not auth.autorizado(conn, "192.168.33.81", "totem-001", "inventado")
        conn.execute("BEGIN IMMEDIATE")
        totem, cookie = auth.canjear_codigo(conn, "192.168.33.81", codigo)
        conn.commit()
        assert totem == "totem-001"
        assert len(cookie) >= 32
        assert auth.autorizado(conn, "192.168.33.81", "totem-001", cookie)
        assert not auth.autorizado(conn, "192.168.33.82", "totem-001", cookie)
        assert not auth.autorizado(conn, "192.168.33.81", "totem-002", cookie)
        conn.execute("BEGIN IMMEDIATE")
        with pytest.raises(ValueError, match="incorrecto"):
            auth.canjear_codigo(conn, "192.168.33.81", codigo)
        conn.rollback()


def test_cambiar_ip_o_eliminar_revoca_cookie_anteriores(db):
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        vincular_ip(conn, "totem-001", "192.168.33.81")
        codigo = auth.generar_codigo(conn, "totem-001")
        _id, cookie = auth.canjear_codigo(conn, "192.168.33.81", codigo)
        conn.commit()
        assert auth.autorizado(conn, "192.168.33.81", "totem-001", cookie)
        conn.execute("BEGIN IMMEDIATE")
        vincular_ip(conn, "totem-001", "192.168.33.82")
        conn.commit()
        assert not auth.autorizado(conn, "192.168.33.82", "totem-001", cookie)
        conn.execute("BEGIN IMMEDIATE")
        codigo = auth.generar_codigo(conn, "totem-001")
        _id, cookie = auth.canjear_codigo(conn, "192.168.33.82", codigo)
        conn.commit()
        conn.execute("BEGIN IMMEDIATE")
        desvincular_ip(conn, "totem-001")
        conn.commit()
        assert not auth.autorizado(conn, "192.168.33.82", "totem-001", cookie)
        conn.execute("BEGIN IMMEDIATE")
        vincular_ip(conn, "totem-001", "192.168.33.82")
        codigo = auth.generar_codigo(conn, "totem-001")
        _id, cookie = auth.canjear_codigo(conn, "192.168.33.82", codigo)
        conn.commit()
        conn.execute("BEGIN IMMEDIATE")
        retirar_totem(conn, "totem-001")
        conn.commit()
        assert not auth.autorizado(conn, "192.168.33.82", "totem-001", cookie)


def test_codigo_vencido_nunca_emite_credenciales(db):
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        vincular_ip(conn, "totem-001", "192.168.33.81")
        codigo = auth.generar_codigo(conn, "totem-001")
        conn.execute(
            "UPDATE intrashop_totem_pair_codes SET expires_at=1 WHERE totem_id='totem-001'"
        )
        conn.commit()
        with pytest.raises(ValueError, match="vencido"):
            auth.canjear_codigo(conn, "192.168.33.81", codigo)
        assert conn.execute(
            "SELECT COUNT(*) FROM intrashop_totem_sessions"
        ).fetchone()[0] == 0


def test_escaneo_lan_limitado_a_lan_privada_y_sin_vinculos(monkeypatch):
    monkeypatch.setattr(lan_discovery, "_ping", lambda ip: ip in {"192.168.15.9", "192.168.15.13"})
    monkeypatch.setattr(lan_discovery, "_arp_conocidos", lambda red: {"192.168.15.7"})
    progreso = []
    result = lan_discovery.detectar_lan(
        "192.168.15.33", max_workers=4, callback=lambda done, total: progreso.append((done,total))
    )
    assert result["subred"] == "192.168.15.0/24"
    assert [x["ip"] for x in result["equipos"]] == [
        "192.168.15.7", "192.168.15.9", "192.168.15.13"
    ]
    assert result["equipos"][0]["detalle"] == "Vecino conocido"
    assert progreso[-1] == (253,253)
    with pytest.raises(ValueError):
        lan_discovery.detectar_lan("8.8.8.8")
    with pytest.raises(ValueError):
        lan_discovery.detectar_lan("127.0.0.1")


def test_panel_no_enlaza_ip_detectada_sin_confirmacion():
    from pathlib import Path
    code = (Path(__file__).resolve().parents[1] / "pos_server_gui.py").read_text()
    assert "def scan_lan(self):" in code
    assert "self.bind_totem_ip(suggested_ip=chosen)" in code
    assert 'messagebox.askyesno(' in code
    assert "command=self.scan_lan" in code


def test_cors_y_credenciales_no_son_publicas():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    server = (root / "api_server.py").read_text()
    store = (root / "intrashop_api.py").read_text()
    assert 'allow_origins=["*"]' not in server
    assert 'allow_origins=_allowed_cors' in server
    assert '"database": str(DB_PATH)' not in store
    assert 'request.cookies.get(auth.COOKIE)' in store
    assert 'def _exigir_checkout_owner(' in store
    settings = (root / "core/settings.py").read_text()
    assert 'self.api_key = _default_secure_api_key(self.db_path)' in settings
    login = (root / "componente_login.py").read_text()
    assert 'json.dumps({"usuario": usuario})' in login

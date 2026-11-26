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


@pytest.mark.parametrize("mutation", [
    "UPDATE intrashop_totems SET retirado=1 WHERE id='totem-001'",
    "UPDATE intrashop_totems SET ip_vinculada='192.168.33.82' WHERE id='totem-001'",
])
def test_sesion_residual_no_autoriza_totem_inactivo_o_reasignado(db, mutation):
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        vincular_ip(conn, "totem-001", "192.168.33.81")
        codigo = auth.generar_codigo(conn, "totem-001")
        _, cookie = auth.canjear_codigo(conn, "192.168.33.81", codigo)
        conn.commit()
        assert auth.autorizado(conn, "192.168.33.81", "totem-001", cookie)
        # Simular una inconsistencia de mantenimiento sin revocación explícita.
        conn.execute(mutation)
        conn.commit()
        assert not auth.autorizado(conn, "192.168.33.81", "totem-001", cookie)


def test_primer_emparejamiento_sin_ip_manual(db):
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        code = auth.generar_codigo(conn, "totem-001")
        tid, token = auth.canjear_codigo(conn, "192.168.33.81", code)
        conn.commit()
        assert tid == "totem-001"
        assert auth.autorizado(conn, "192.168.33.81", tid, token)
        assert conn.execute("SELECT ip_vinculada FROM intrashop_totems WHERE id=?", (tid,)).fetchone()[0] == "192.168.33.81"
        with pytest.raises(ValueError, match="incorrecto"):
            auth.canjear_codigo(conn, "192.168.33.81", code)


def test_codigo_no_desplaza_otro_totem(db):
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        vincular_ip(conn, "totem-002", "192.168.33.81")
        code = auth.generar_codigo(conn, "totem-001")
        with pytest.raises(ValueError, match="otro tótem"):
            auth.canjear_codigo(conn, "192.168.33.81", code)
        assert conn.execute("SELECT ip_vinculada FROM intrashop_totems WHERE id='totem-001'").fetchone()[0] is None
        tid, token = auth.canjear_codigo(conn, "192.168.33.82", code)
        conn.commit()
        assert tid == "totem-001"
        assert auth.autorizado(conn, "192.168.33.82", tid, token)


def test_reconexion_tls_conserva_identidad_y_qr(db):
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        tid, token = auth.canjear_codigo(conn, "192.168.33.81", auth.generar_codigo(conn, "totem-001"))
        conn.execute(
            "INSERT INTO intrashop_mp_bindings(terminal_id,terminal_type,pos_external_id,store_external_id,qr_url,nombre) "
            "VALUES(?,?,?,?,?,?)", (tid, "totem", "POS-TEST", "STORE-TEST", "https://example.com/qr", "Prueba")
        )
        conn.commit()
        conn.execute("BEGIN IMMEDIATE")
        assert auth.recuperar_direccion(conn, "192.168.33.82", token) == tid
        conn.commit()
        assert auth.autorizado(conn, "192.168.33.82", tid, token)
        assert not auth.autorizado(conn, "192.168.33.81", tid, token)
        assert conn.execute("SELECT pos_external_id FROM intrashop_mp_bindings WHERE terminal_id=?", (tid,)).fetchone()[0] == "POS-TEST"


def test_reconexion_no_desplaza_otro_puesto_ni_revive_sesion(db):
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        tid, token = auth.canjear_codigo(conn, "192.168.33.81", auth.generar_codigo(conn, "totem-001"))
        vincular_ip(conn, "totem-002", "192.168.33.82")
        assert auth.recuperar_direccion(conn, "192.168.33.82", token) is None
        assert auth.autorizado(conn, "192.168.33.81", tid, token)
        auth.revocar_totem(conn, tid)
        assert auth.recuperar_direccion(conn, "192.168.33.83", token) is None
        conn.commit()


@pytest.mark.parametrize("scheme,enforce,expected", [
    ("http", "0", False), ("https", "0", False),
    ("http", "1", False), ("https", "1", True),
])
def test_identidad_recupera_solo_con_tls_configurado(db, monkeypatch, scheme, enforce, expected):
    import intrashop_api as api
    monkeypatch.setattr(api, "_connect", db)
    monkeypatch.setenv("INTRASHOP_ENFORCE_HTTPS", enforce)
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        tid, token = auth.canjear_codigo(conn, "192.168.33.81", auth.generar_codigo(conn, "totem-001"))
        conn.commit()
    request = types.SimpleNamespace(
        client=types.SimpleNamespace(host="192.168.33.83"),
        url=types.SimpleNamespace(scheme=scheme),
        cookies={auth.COOKIE: token},
    )
    result = api.identidad_totem(request)
    assert result["authorized"] is expected
    with db() as conn:
        address = conn.execute("SELECT ip_vinculada FROM intrashop_totems WHERE id=?", (tid,)).fetchone()[0]
        assert address == ("192.168.33.83" if expected else "192.168.33.81")

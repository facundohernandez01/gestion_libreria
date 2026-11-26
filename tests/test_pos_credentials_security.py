"""Regresión de credenciales con bases SQLite temporales, sin producción."""
import sqlite3

import pytest

from database_manager import DatabaseManager
from services.passwords import hash_password, check_password, validar_nueva_clave


def test_passwords_tienen_sal_aleatoria_y_verificacion_constante():
    a, b = hash_password("ClaveDePruebaSegura567"), hash_password("ClaveDePruebaSegura567")
    assert a != b
    assert a.startswith("pbkdf2_sha256$")
    assert check_password(a, "ClaveDePruebaSegura567") == (True, False)
    assert check_password(a, "otra-clave") == (False, False)
    assert check_password("ClaveAntigua987", "ClaveAntigua987") == (True, True)
    with pytest.raises(ValueError):
        validar_nueva_clave("123456")


def test_admin_default_no_permite_login_y_rotacion_restaura_acceso(tmp_path):
    db = DatabaseManager(str(tmp_path / "auth.db"))
    usuarios = db.listar_usuarios()
    admin = next(u for u in usuarios if u["es_admin"])
    assert "clave" not in admin
    assert db.autenticar_usuario("admin", "admin") is None
    uid, error = db.guardar_usuario({
        "id": admin["id"], "usuario": admin["usuario"],
        "nombre": "Administrador", "rol_id": admin["rol_id"],
        "activo": True, "clave": "ClaveSuperSegura12345",
    })
    assert uid == admin["id"], error
    assert "clave" not in db.autenticar_usuario("admin", "ClaveSuperSegura12345")
    with sqlite3.connect(db.db_path) as conn:
        secret = conn.execute(
            "SELECT clave FROM usuarios WHERE id=?", (uid,),
        ).fetchone()[0]
        assert secret.startswith("pbkdf2_sha256$")
        conn.execute(
            "INSERT INTO config(clave,valor) VALUES('LOGIN_CLAVE','admin') "
            "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor"
        )
        conn.commit()
    # La clave heredada no es una segunda contraseña de administrador.
    assert db.autenticar_usuario("admin", "admin") is None


def test_credenciales_legacy_se_rehashean_tras_login_valido(tmp_path):
    db = DatabaseManager(str(tmp_path / "legacy.db"))
    with sqlite3.connect(db.db_path) as conn:
        conn.execute(
            "UPDATE usuarios SET clave=?,activo=1 WHERE usuario='admin'",
            ("LegadoQueSoloConozcoYo45",),
        )
        conn.commit()
    assert db.autenticar_usuario("admin", "LegadoQueSoloConozcoYo45")
    with sqlite3.connect(db.db_path) as conn:
        pwd = conn.execute("SELECT clave FROM usuarios WHERE usuario='admin'").fetchone()[0]
        assert pwd.startswith("pbkdf2_sha256$")
    assert db.autenticar_usuario("admin", "LegadoQueSoloConozcoYo45")


def test_login_recordado_elimina_clave_del_archivo(tmp_path, monkeypatch):
    pytest.importorskip("flet")
    import componente_login as login

    path = tmp_path / "login_recordado.json"
    path.write_text('{"usuario":"admin","clave":"secreto-en-claro"}')
    monkeypatch.setattr(login, "_RECUERDO_LOGIN", path)
    assert login._cargar_recordado() == ("admin", "")
    assert "secreto-en-claro" not in path.read_text()
    login._guardar_recordado("operador", "clave-que-no-debe-guardarse")
    assert "clave-que-no-debe-guardarse" not in path.read_text()


def test_config_lan_no_entrega_ni_permite_modificar_secretos(tmp_path, monkeypatch):
    import api_server as server

    path = str(tmp_path / "safe.db")
    DatabaseManager(path)
    monkeypatch.setattr(server, "DB_PATH", path)
    monkeypatch.setattr(server, "API_KEY", "TEST-KEY-EN-MEMORIA")
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO config(clave,valor) VALUES('ACCESS_TOKEN','sensitive123')"
        )
        conn.execute(
            "INSERT INTO config(clave,valor) VALUES('LOGIN_CLAVE','sensitiveLogin') "
            "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor"
        )
        conn.commit()
    values = server.get_config(x_api_key="TEST-KEY-EN-MEMORIA")
    assert "ACCESS_TOKEN" not in values
    assert "LOGIN_CLAVE" not in values
    with pytest.raises(Exception) as exc:
        server.set_config(
            server.ConfigIn(clave="ACCESS_TOKEN", valor="to-attackers"),
            x_api_key="TEST-KEY-EN-MEMORIA",
        )
    assert getattr(exc.value, "status_code", None) == 403
    with sqlite3.connect(path) as conn:
        assert conn.execute(
            "SELECT valor FROM config WHERE clave='ACCESS_TOKEN'",
        ).fetchone()[0] == "sensitive123"


def test_credenciales_individuales_canje_rotacion_y_revocacion(tmp_path):
    from services import pos_device_credentials as devices
    with sqlite3.connect(tmp_path / "devices.db") as conn:
        conn.execute("BEGIN IMMEDIATE")
        a, b = "caja-" + "a" * 32, "caja-" + "b" * 32
        code = devices.emitir_codigo(conn, "Caja A")
        token = devices.canjear(conn, code, a)
        assert devices.autorizado(conn, token)
        with pytest.raises(ValueError):
            devices.canjear(conn, code, b)
        other = devices.canjear(conn, devices.emitir_codigo(conn, "Caja B"), b)
        assert token != other
        assert devices.revocar(conn, a)
        assert not devices.autorizado(conn, token)
        assert devices.autorizado(conn, other)
        renewed = devices.canjear(conn, devices.emitir_codigo(conn, "Caja A"), a)
        assert devices.autorizado(conn, renewed)
        assert not devices.autorizado(conn, token)
        assert len(devices.listar(conn)) == 2
        assert conn.execute("SELECT token_hash FROM pos_device_credentials WHERE terminal_id=?", (a,)).fetchone()[0] != renewed


def test_codigo_pos_vencido_no_emite_credencial(tmp_path):
    from services import pos_device_credentials as devices
    with sqlite3.connect(tmp_path / "devices.db") as conn:
        conn.execute("BEGIN IMMEDIATE")
        code = devices.emitir_codigo(conn, "Caja A")
        conn.execute("UPDATE pos_device_codes SET expires_at=0")
        with pytest.raises(ValueError):
            devices.canjear(conn, code, "caja-" + "a" * 32)
        assert not devices.listar(conn)


def test_credencial_individual_no_se_confunde_con_clave_global(tmp_path, monkeypatch):
    from pathlib import Path
    from core import settings as config
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("API_KEY", raising=False)
    value = "posd_" + "x" * 48
    config.guardar_credencial_pos(value)
    assert config.credencial_pos_local() == value
    assert config._default_secure_api_key(str(tmp_path / "db.sqlite")) != value
    with pytest.raises(ValueError):
        config.guardar_clave_lan_local(value)


def test_sesion_de_caja_revocada_no_recupera_acceso(tmp_path, monkeypatch):
    import pos_auth
    from services import pos_device_credentials as devices
    from types import SimpleNamespace
    db = DatabaseManager(str(tmp_path / "session-device.db"))
    monkeypatch.setattr(pos_auth, "DatabaseManager", lambda: db)
    monkeypatch.setenv("INTRASHOP_ENFORCE_HTTPS", "1")
    admin = next(u for u in db.listar_usuarios() if u["es_admin"])
    db.guardar_usuario({"id": admin["id"], "usuario": admin["usuario"], "nombre": "Admin",
        "rol_id": admin["rol_id"], "activo": True, "clave": "TestSeguro123456789"})
    tid = "caja-" + "a" * 32
    with db._connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        key = devices.canjear(conn, devices.emitir_codigo(conn, "Caja"), tid)
        conn.commit()
    request = SimpleNamespace(headers={"x-api-key": key}, url=SimpleNamespace(scheme="https"),
                              client=SimpleNamespace(host="192.168.1.23"))
    body = pos_auth.LoginRequest(usuario=admin["usuario"], clave="TestSeguro123456789")
    session = pos_auth.login(body, tid, request)["access_token"]
    assert pos_auth.require_delivery("Bearer " + session) == admin["usuario"]
    with db._connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        devices.revocar(conn, tid)
        conn.commit()
    with pytest.raises(Exception) as err:
        pos_auth.require_delivery("Bearer " + session)
    assert err.value.status_code == 401
    with pytest.raises(Exception) as err:
        pos_auth.login(body, tid, request)
    assert err.value.status_code == 403

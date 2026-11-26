"""Regresión de credenciales con bases SQLite temporales, sin producción."""
import sqlite3

import pytest

import api_server as server
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
    import componente_login as login

    path = tmp_path / "login_recordado.json"
    path.write_text('{"usuario":"admin","clave":"secreto-en-claro"}')
    monkeypatch.setattr(login, "_RECUERDO_LOGIN", path)
    assert login._cargar_recordado() == ("admin", "")
    assert "secreto-en-claro" not in path.read_text()
    login._guardar_recordado("operador", "clave-que-no-debe-guardarse")
    assert "clave-que-no-debe-guardarse" not in path.read_text()


def test_config_lan_no_entrega_ni_permite_modificar_secretos(tmp_path, monkeypatch):
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

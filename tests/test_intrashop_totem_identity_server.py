"""Tótems identificados por POS Server: SQLite temporal y HTTP simulado.

No toca libreria.db ni una cuenta de Mercado Pago real.
"""
from contextlib import contextmanager
from types import SimpleNamespace
import sqlite3

import pytest
from fastapi import HTTPException

from database_manager import DatabaseManager
from intrashop_entregas import ensure_schema
import intrashop_checkout_store as checkout_store
import intrashop_api as api
from services.intrashop_totem_registry import (
    normalizar_ip, provisionar, resolve_ip, vincular_ip, desvincular_ip,
)


@pytest.fixture
def server_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "server.db")
    DatabaseManager(db_path)

    @contextmanager
    def connect():
        conn = sqlite3.connect(db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
        finally:
            conn.close()

    with connect() as conn:
        ensure_schema(conn)
        checkout_store.ensure_schema(conn)
        conn.execute(
            "INSERT INTO intrashop_totems(id,nombre,ip_address) "
            "VALUES ('legacy-uuid','Tótem entrada','192.168.30.41')"
        )
        conn.execute(
            "INSERT INTO intrashop_mp_bindings"
            "(terminal_id,terminal_type,pos_external_id,store_external_id,qr_url,nombre) "
            "VALUES('legacy-uuid','totem','POS-LEGACY','STORE-01','https://example.com/qr','Tótem entrada')"
        )
        conn.commit()
    monkeypatch.setattr(api, "_connect", connect)
    return connect


def request(ip):
    return SimpleNamespace(client=SimpleNamespace(host=ip),
                           headers={"x-forwarded-for": "192.168.1.200"})


def test_numeracion_central_precreada_y_persistente(server_db):
    with server_db() as conn:
        slots = conn.execute(
            "SELECT id,ip_vinculada FROM intrashop_totems WHERE id LIKE 'totem-%' ORDER BY id"
        ).fetchall()
        assert [row["id"] for row in slots] == [
            f"totem-{n:03d}" for n in range(1, 9)
        ]
        assert all(row["ip_vinculada"] is None for row in slots)
        assert provisionar(conn, 1)[0]["id"] == "totem-009"
        conn.commit()
    with server_db() as conn:
        ensure_schema(conn)
        conn.commit()
        assert conn.execute(
            "SELECT COUNT(*) FROM intrashop_totems WHERE id LIKE 'totem-%'"
        ).fetchone()[0] == 9


def test_identidad_no_depende_de_cache_y_conserva_qr_legacy(server_db):
    # Migración sin volver a registrar/renombrar un tótem y sin modificar su QR.
    with server_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        vincular_ip(conn, "legacy-uuid", "192.168.30.41")
        conn.commit()
    first = api.identidad_totem(request("192.168.30.41"))
    second = api.identidad_totem(request("192.168.30.41"))
    assert first == second
    assert first["paired"] is True
    assert first["id"] == "legacy-uuid"
    assert first["nombre"] == "Tótem entrada"
    assert first["qr_assigned"] is True
    with server_db() as conn:
        row = conn.execute(
            "SELECT pos_external_id FROM intrashop_mp_bindings "
            "WHERE terminal_id='legacy-uuid'"
        ).fetchone()
        assert row["pos_external_id"] == "POS-LEGACY"


def test_navegador_no_crea_tótems_y_ip_sin_asignar_no_es_valida(server_db):
    data = api.identidad_totem(request("192.168.30.42"))
    assert data["paired"] is False
    with pytest.raises(HTTPException) as error:
        api.registrar_totem_obsoleto()
    assert error.value.status_code == 410
    with server_db() as conn:
        assert conn.execute(
            "SELECT 1 FROM intrashop_totems WHERE ip_vinculada='192.168.30.42'"
        ).fetchone() is None


def test_doble_asignacion_ip_rechazada_sin_tocar_qr(server_db):
    with server_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        vincular_ip(conn, "totem-001", "192.168.30.42")
        with pytest.raises(ValueError, match="ya vinculada"):
            vincular_ip(conn, "totem-002", "192.168.30.42")
        conn.commit()
    with server_db() as conn:
        assert resolve_ip(conn, "192.168.30.42")["id"] == "totem-001"
        assert desvincular_ip(conn, "totem-001") is True
        conn.commit()
    assert api.identidad_totem(request("192.168.30.42"))["paired"] is False


def test_ip_de_cabecera_x_forwarded_for_no_suplanta_cliente(server_db):
    with server_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        vincular_ip(conn, "totem-003", "192.168.1.200")
        conn.commit()
    # La cabecera engañosa no puede sustituir la IP TCP real.
    assert api.identidad_totem(request("192.168.30.43"))["paired"] is False


def test_checkout_rechaza_uuid_ajeno_a_ip_del_equipo(server_db, monkeypatch):
    with server_db() as conn:
        conn.execute("ALTER TABLE productos ADD COLUMN disponible_tienda INTEGER DEFAULT 0")
        pid = conn.execute(
            "INSERT INTO productos(codigo,descripcion,precio_lista,stock_actual,disponible_tienda) "
            "VALUES('TEST-IP','Prueba',10,5,1)"
        ).lastrowid
        conn.execute("BEGIN IMMEDIATE")
        vincular_ip(conn, "totem-001", "192.168.30.42")
        conn.commit()
    monkeypatch.setattr(api.settings, "mp_activo", True)
    body = api.CheckoutIn(
        totem_id="legacy-uuid", items=[api.CartItem(producto_id=pid, cantidad=1)]
    )
    with pytest.raises(HTTPException) as err:
        api.iniciar_checkout(body, request("192.168.30.42"))
    assert err.value.status_code == 403
    with server_db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM intrashop_checkouts").fetchone()[0] == 0


def test_frontend_no_registra_identidad_local_ni_uuid():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] /
              "intrashop/src/pages/index.astro").read_text(encoding="utf-8")
    assert "/tienda/totems/identity" in source
    assert "/tienda/totems/register" not in source
    assert "localStorage.getItem(\"intrashop_totem_id\")" not in source
    assert "localStorage.setItem(\"intrashop_totem_id\"" not in source

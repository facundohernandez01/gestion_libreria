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
    resumen_retiro, retirar_totem, restaurar_totem,
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


def test_retiro_con_qr_libera_asociacion_sin_borrar_registro_ni_historial(server_db):
    with server_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        vincular_ip(conn, "legacy-uuid", "192.168.30.41")
        previo = resumen_retiro(conn, "legacy-uuid")
        assert previo["pos_external_id"] == "POS-LEGACY"
        result = retirar_totem(conn, "legacy-uuid")
        assert result["retirado"] is True
        conn.commit()

    with server_db() as conn:
        row = conn.execute(
            "SELECT retirado,ip_vinculada,ip_address,nombre FROM intrashop_totems "
            "WHERE id='legacy-uuid'"
        ).fetchone()
        assert (row["retirado"], row["ip_vinculada"], row["ip_address"]) == (1, None, None)
        assert row["nombre"] == "Tótem entrada"
        assert conn.execute(
            "SELECT COUNT(*) FROM intrashop_mp_bindings WHERE terminal_id='legacy-uuid'"
        ).fetchone()[0] == 0
    assert api.identidad_totem(request("192.168.30.41"))["paired"] is False
    assert "legacy-uuid" not in [
        row["id"] for row in api.admin_listar_totems(operador="admin")
    ]
    assert "legacy-uuid" in [
        row["id"] for row in api.admin_listar_totems(
            incluir_eliminados=True, operador="admin"
        )
    ]


def test_restaura_tótem_sin_recuperar_ip_ni_vinculo_qr(server_db):
    with server_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        retirar_totem(conn, "legacy-uuid")
        restored = restaurar_totem(conn, "legacy-uuid")
        conn.commit()
        assert restored["retirado"] is False
    assert api.identidad_totem(request("192.168.30.41"))["paired"] is False
    with server_db() as conn:
        vincular_ip(conn, "legacy-uuid", "192.168.30.41")
        conn.commit()
        assert conn.execute(
            "SELECT COUNT(*) FROM intrashop_mp_bindings WHERE terminal_id='legacy-uuid'"
        ).fetchone()[0] == 0
    assert api.identidad_totem(request("192.168.30.41"))["paired"] is True


def test_retiro_no_recrea_numerados_y_el_siguiente_id_es_009(server_db):
    with server_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        retirar_totem(conn, "totem-008")
        conn.commit()
    with server_db() as conn:
        ensure_schema(conn)
        ensure_schema(conn)
        conn.commit()
        assert conn.execute(
            "SELECT retirado FROM intrashop_totems WHERE id='totem-008'"
        ).fetchone()["retirado"] == 1
        assert provisionar(conn, 1)[0]["id"] == "totem-009"
        conn.commit()


def test_eliminar_no_borra_ordenes_cobradas_y_bloquea_si_hay_pendiente(server_db):
    with server_db() as conn:
        conn.execute("""INSERT INTO intrashop_checkouts
            (id,totem_id,pos_external_id,store_external_id,estado,
             total,items_json,created_at,updated_at)
            VALUES ('prueba-checkout','legacy-uuid','POS-LEGACY','STORE-01',
                    'waiting',10,'[]',1,1)""")
        conn.commit()
        conn.execute("BEGIN IMMEDIATE")
        with pytest.raises(ValueError, match="cobro"):
            retirar_totem(conn, "legacy-uuid")
        conn.rollback()
        row = conn.execute(
            "SELECT retirado FROM intrashop_totems WHERE id='legacy-uuid'"
        ).fetchone()
        assert row["retirado"] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM intrashop_mp_bindings WHERE terminal_id='legacy-uuid'"
        ).fetchone()[0] == 1
        conn.execute(
            "UPDATE intrashop_checkouts SET estado='completed' WHERE id='prueba-checkout'"
        )
        conn.commit()
        conn.execute("BEGIN IMMEDIATE")
        retirar_totem(conn, "legacy-uuid")
        conn.commit()
        assert tuple(conn.execute(
            "SELECT id,estado,totem_id FROM intrashop_checkouts WHERE id='prueba-checkout'"
        ).fetchone()) == ("prueba-checkout", "completed", "legacy-uuid")


def test_no_retirar_tótem_con_entrega_pendiente(server_db):
    with server_db() as conn:
        conn.execute("INSERT INTO cajas(fecha_apertura,importe_apertura,estado) "
                     "VALUES(CURRENT_TIMESTAMP,0,'abierta')")
        caja = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO ventas(caja_id,total,metodo_pago) VALUES(?,?,?)",
            (caja, 10, "mercadopago_qr"),
        )
        venta = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO intrashop_entregas(venta_id,checkout_id,totem_id,totem_nombre) "
            "VALUES(?,?,?,?)",
            (venta, "entrega-prueba", "legacy-uuid", "Tótem entrada"),
        )
        conn.commit()
        conn.execute("BEGIN IMMEDIATE")
        with pytest.raises(ValueError, match="comanda"):
            retirar_totem(conn, "legacy-uuid")
        conn.rollback()
        conn.execute(
            "UPDATE intrashop_entregas SET estado='entregado' WHERE checkout_id='entrega-prueba'"
        )
        conn.commit()
        conn.execute("BEGIN IMMEDIATE")
        retirar_totem(conn, "legacy-uuid")
        conn.commit()
        assert tuple(conn.execute(
            "SELECT totem_id,totem_nombre,estado FROM intrashop_entregas "
            "WHERE checkout_id='entrega-prueba'"
        ).fetchone()) == ("legacy-uuid", "Tótem entrada", "entregado")


def test_desvincular_ip_tiene_efecto_visible_y_preserva_qr(server_db):
    with server_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        vincular_ip(conn, "legacy-uuid", "192.168.30.41")
        conn.execute("UPDATE intrashop_totems SET ip_address='192.168.30.41' "
                     "WHERE id='legacy-uuid'")
        assert desvincular_ip(conn, "legacy-uuid") is True
        conn.commit()
        linked = conn.execute(
            "SELECT ip_vinculada,ip_address FROM intrashop_totems WHERE id='legacy-uuid'"
        ).fetchone()
        assert (linked["ip_vinculada"], linked["ip_address"]) == (None, None)
        assert conn.execute(
            "SELECT COUNT(*) FROM intrashop_mp_bindings WHERE terminal_id='legacy-uuid'"
        ).fetchone()[0] == 1


def test_pantalla_pos_server_explica_eliminar_y_desvincular():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "pos_server_gui.py").read_text()
    assert "Desvincular equipo (solo IP)" in src
    assert "Eliminar tótem…" in src
    assert "Mostrar eliminados" in src
    assert "def restore_totem(self):" in src

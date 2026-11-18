"""Regresión: consola POS Server con instalación nueva / DB histórica.

No usa Tk, pantalla, Mercado Pago ni datos de producción.
"""
import sqlite3

import pytest

from database_manager import DatabaseManager
from pos_server_snapshot import snapshot


def _connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def test_panel_inicializa_tablas_intrashop_ausentes_en_db_nueva(tmp_path):
    path = str(tmp_path / "pos-recien-clonado.db")
    DatabaseManager(path)
    with _connect(path) as conn:
        names = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert "intrashop_totems" not in names
        assert "intrashop_mp_bindings" not in names
        assert "intrashop_checkouts" not in names

    totems, bindings, pending = snapshot(path)
    assert (totems, bindings, pending) == ([], [], [])

    with _connect(path) as conn:
        names = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert {"intrashop_totems", "intrashop_mp_bindings",
                "intrashop_checkouts", "intrashop_entregas"} <= names
        conn.execute(
            "INSERT INTO intrashop_totems(id,nombre,ip_address) "
            "VALUES('totem-1','Puesto 1','192.0.2.5')"
        )
        conn.commit()
    totems, bindings, pending = snapshot(path)
    assert len(totems) == 1 and totems[0]["nombre"] == "Puesto 1"
    assert totems[0]["ip_address"] == "192.0.2.5"
    assert bindings == [] and pending == []


def test_panel_no_cambia_asignaciones_existentes_ni_historial(tmp_path):
    path = str(tmp_path / "con-qr.db")
    DatabaseManager(path)
    snapshot(path)
    with _connect(path) as conn:
        conn.execute(
            "INSERT INTO intrashop_mp_bindings "
            "(terminal_id,terminal_type,nombre,pos_external_id,store_external_id,qr_url) "
            "VALUES ('totem-2','totem','Puesto 2','POS-X','STORE-X','https://example.test/qr')"
        )
        conn.execute(
            "INSERT INTO intrashop_checkouts "
            "(id,totem_id,pos_external_id,store_external_id,estado,total,"
            "items_json,created_at,updated_at) "
            "VALUES('checkout-pendiente','totem-2','POS-X','STORE-X','waiting',"
            "45.0,'[]',1234,1235)"
        )
        conn.execute(
            "INSERT INTO intrashop_checkouts "
            "(id,totem_id,pos_external_id,store_external_id,estado,total,"
            "items_json,created_at,updated_at) "
            "VALUES('checkout-antiguo','totem-2','POS-X','STORE-X','completed',"
            "34.0,'[]',1233,1233)"
        )
        conn.commit()
    for _ in range(3):
        totems, bindings, pending = snapshot(path)
        assert totems == []
        assert [x["terminal_id"] for x in bindings] == ["totem-2"]
        assert [x["id"] for x in pending] == ["checkout-pendiente"]
    with _connect(path) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM intrashop_checkouts"
        ).fetchone()[0] == 2


def test_panel_migra_ip_de_totem_antiguo_sin_perderlo(tmp_path):
    path = str(tmp_path / "totem-antiguo.db")
    DatabaseManager(path)
    with _connect(path) as conn:
        conn.execute(
            "CREATE TABLE intrashop_totems (id TEXT PRIMARY KEY, nombre TEXT "
            "NOT NULL, ultimo_contacto TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, "
            "fecha_registro TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, ip TEXT)"
        )
        conn.execute(
            "INSERT INTO intrashop_totems(id,nombre,ip) "
            "VALUES('id-old','Histórico','192.0.2.55')"
        )
        conn.commit()
    totems, bindings, pending = snapshot(path)
    assert totems[0]["ip"] == "192.0.2.55"
    assert len(bindings) == len(pending) == 0
    with _connect(path) as conn:
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(intrashop_totems)")}
        assert "ip_address" in cols
        assert conn.execute("SELECT nombre FROM intrashop_totems").fetchone()[0] == "Histórico"


def test_panel_no_crea_otra_sqlite_si_la_ruta_es_incorrecta(tmp_path):
    bad = tmp_path / "otra-carpeta" / "libreria.db"
    with pytest.raises(FileNotFoundError, match="No existe la base"):
        snapshot(str(bad))
    assert not bad.exists()

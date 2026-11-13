"""Pruebas de validación SQLite sin afectar la base real."""
import sqlite3

import pytest

from services.backup_service import TABLAS_MINIMAS, validar_backup


def test_backup_valido_devuelve_conteos(tmp_path):
    ruta = tmp_path / "copia.db"
    with sqlite3.connect(ruta) as conn:
        for tabla in TABLAS_MINIMAS:
            conn.execute(f"CREATE TABLE {tabla} (id INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO productos DEFAULT VALUES")
    info = validar_backup(ruta)
    assert info["conteos"]["productos"] == 1
    assert info["conteos"]["ventas"] == 0


def test_backup_incompleto_es_rechazado(tmp_path):
    ruta = tmp_path / "incompleto.db"
    with sqlite3.connect(ruta) as conn:
        conn.execute("CREATE TABLE productos (id INTEGER PRIMARY KEY)")
    with pytest.raises(ValueError, match="faltan tablas"):
        validar_backup(ruta)


def test_archivo_que_no_es_sqlite_es_rechazado(tmp_path):
    ruta = tmp_path / "falso.db"
    ruta.write_bytes(b"no es una base sqlite")
    with pytest.raises((ValueError, sqlite3.DatabaseError)):
        validar_backup(ruta)

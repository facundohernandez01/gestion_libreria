"""Exportación y recuperación de backups en bases SQLite descartables."""
import sqlite3

from database_manager import DatabaseManager
from services.backup_service import exportar_backup, restaurar_backup, validar_backup


def _crear_producto(db_path, codigo, stock):
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO productos (codigo, descripcion, precio_lista, stock_actual) "
            "VALUES (?, ?, ?, ?)", (codigo, codigo, 100, stock)
        )


def _stock(db_path, codigo):
    with sqlite3.connect(db_path) as conn:
        return conn.execute(
            "SELECT stock_actual FROM productos WHERE codigo=?", (codigo,)
        ).fetchone()[0]


def test_exportar_y_reemplazar_recupera_stock_y_guarda_copia_previa(tmp_path):
    activa = tmp_path / "servidor.db"
    copia = tmp_path / "copia.db"
    DatabaseManager(str(activa))
    _crear_producto(activa, "TEST-BACKUP", 12)
    exportar_backup(activa, copia)
    assert validar_backup(copia)["conteos"]["productos"] >= 1

    with sqlite3.connect(activa) as conn:
        conn.execute("UPDATE productos SET stock_actual=99 WHERE codigo='TEST-BACKUP'")
    assert _stock(activa, "TEST-BACKUP") == 99

    resultado = restaurar_backup(activa, copia, "reemplazar")
    assert resultado["modo"] == "reemplazar"
    assert _stock(activa, "TEST-BACKUP") == 12
    assert _stock(resultado["seguridad"], "TEST-BACKUP") == 99


def test_fusionar_no_modifica_stock_de_productos_existentes(tmp_path):
    activa = tmp_path / "servidor.db"
    copia = tmp_path / "copia.db"
    DatabaseManager(str(activa))
    _crear_producto(activa, "TEST-BACKUP", 12)
    exportar_backup(activa, copia)
    with sqlite3.connect(activa) as conn:
        conn.execute("UPDATE productos SET stock_actual=99 WHERE codigo='TEST-BACKUP'")
    resultado = restaurar_backup(activa, copia, "fusionar")
    assert resultado["modo"] == "fusionar"
    assert _stock(activa, "TEST-BACKUP") == 99
    assert resultado["productos_omitidos"] >= 1

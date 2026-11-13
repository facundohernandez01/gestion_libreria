"""Pruebas reales sobre SQLite temporal; nunca usan libreria.db de producción."""
import sqlite3
import threading

from database_manager import DatabaseManager


def _producto(db):
    with db._connect() as conn:
        cursor = conn.execute(
            "INSERT INTO productos (codigo, descripcion, precio_lista, stock_actual) "
            "VALUES ('TEST-ABS', 'Prueba ajuste', 100, 20)"
        )
        conn.commit()
        return cursor.lastrowid


def test_ajuste_disminuye_y_aumenta_stock(tmp_path):
    db = DatabaseManager(str(tmp_path / "stock.db"))
    pid = _producto(db)
    assert db.ajustar_stock_absoluto(pid, 15, 20, "conteo físico")
    assert db.ajustar_stock_absoluto(pid, 22, 15, "reposición")
    with db._connect() as conn:
        assert conn.execute("SELECT stock_actual FROM productos WHERE id=?", (pid,)).fetchone()[0] == 22
        rows = conn.execute(
            "SELECT tipo, cantidad, stock_anterior, stock_nuevo FROM movimientos_stock "
            "WHERE producto_id=? ORDER BY id", (pid,)
        ).fetchall()
    assert [tuple(row) for row in rows] == [
        ("ajuste", 5, 20, 15),
        ("ajuste", 7, 15, 22),
    ]


def test_ajuste_rechaza_stock_obsoleto_y_negativo(tmp_path):
    db = DatabaseManager(str(tmp_path / "stock.db"))
    pid = _producto(db)
    assert not db.ajustar_stock_absoluto(pid, 10, 19)
    assert not db.ajustar_stock_absoluto(pid, -1, 20)
    assert db.ajustar_stock_absoluto(pid, 20, 20)
    with db._connect() as conn:
        assert conn.execute("SELECT stock_actual FROM productos WHERE id=?", (pid,)).fetchone()[0] == 20
        assert conn.execute("SELECT COUNT(*) FROM movimientos_stock WHERE producto_id=?", (pid,)).fetchone()[0] == 0


def test_dos_ajustes_con_mismo_stock_esperado_solo_uno_prospera(tmp_path):
    db_path = str(tmp_path / "stock.db")
    db = DatabaseManager(db_path)
    pid = _producto(db)
    barrier = threading.Barrier(2)
    results = []
    def ajustar(nuevo):
        local = DatabaseManager(db_path)
        barrier.wait(timeout=10)
        results.append(local.ajustar_stock_absoluto(pid, nuevo, 20))
    threads = [threading.Thread(target=ajustar, args=(15,)),
               threading.Thread(target=ajustar, args=(25,))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)
        assert not t.is_alive()
    assert sorted(results) == [False, True]
    with db._connect() as conn:
        assert conn.execute("SELECT stock_actual FROM productos WHERE id=?", (pid,)).fetchone()[0] in (15, 25)
        assert conn.execute("SELECT COUNT(*) FROM movimientos_stock WHERE producto_id=?", (pid,)).fetchone()[0] == 1

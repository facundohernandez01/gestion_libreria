"""Regresiones de stock en ventas POS, sin tocar bases reales."""
import sqlite3
import threading

from database_manager import DatabaseManager


def _preparar(tmp_path):
    ruta = str(tmp_path / "ventas.db")
    db = DatabaseManager(ruta)
    with sqlite3.connect(ruta) as conn:
        producto = conn.execute(
            "INSERT INTO productos (codigo, descripcion, precio_lista, stock_actual) "
            "VALUES ('TEST-VENTA', 'Venta concurrente', 10, 5)"
        ).lastrowid
        caja = conn.execute(
            "INSERT INTO cajas (estado, saldo_inicial) VALUES ('abierta', 0)"
        ).lastrowid
    return ruta, producto, caja


def _linea(producto, cantidad):
    return {"producto_id": producto, "cantidad": cantidad, "precio_unitario": 10}


def test_lineas_duplicadas_no_superan_stock(tmp_path):
    ruta, producto, caja = _preparar(tmp_path)
    db = DatabaseManager(ruta)
    venta, ok = db.crear_venta(caja, [_linea(producto, 3), _linea(producto, 3)])
    assert not ok and venta == 0
    with sqlite3.connect(ruta) as conn:
        assert conn.execute("SELECT stock_actual FROM productos WHERE id=?", (producto,)).fetchone()[0] == 5
        assert conn.execute("SELECT COUNT(*) FROM ventas").fetchone()[0] == 0


def test_lineas_duplicadas_registran_saldo_correcto(tmp_path):
    ruta, producto, caja = _preparar(tmp_path)
    db = DatabaseManager(ruta)
    venta, ok = db.crear_venta(caja, [_linea(producto, 2), _linea(producto, 3)])
    assert ok and venta > 0
    with sqlite3.connect(ruta) as conn:
        assert conn.execute("SELECT stock_actual FROM productos WHERE id=?", (producto,)).fetchone()[0] == 0
        movimientos = conn.execute(
            "SELECT stock_anterior, stock_nuevo FROM movimientos_stock "
            "WHERE referencia_id=? AND tipo='venta' ORDER BY id", (venta,)
        ).fetchall()
    assert movimientos == [(5, 3), (3, 0)]


def test_dos_cajas_no_venden_mismas_unidades(tmp_path):
    ruta, producto, caja = _preparar(tmp_path)
    barrera = threading.Barrier(2)
    resultados = []
    def cobrar():
        db = DatabaseManager(ruta)
        barrera.wait(timeout=10)
        resultados.append(db.crear_venta(caja, [_linea(producto, 4)])[1])
    hilos = [threading.Thread(target=cobrar) for _ in range(2)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=15)
        assert not hilo.is_alive()
    assert sorted(resultados) == [False, True]
    with sqlite3.connect(ruta) as conn:
        assert conn.execute("SELECT stock_actual FROM productos WHERE id=?", (producto,)).fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM ventas").fetchone()[0] == 1

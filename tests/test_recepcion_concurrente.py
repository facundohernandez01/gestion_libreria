"""Recepciones concurrentes y validación estricta sobre SQLite temporal."""
import sqlite3
import threading

from database_manager import DatabaseManager


def _preparar(tmp_path):
    ruta = str(tmp_path / "recepciones.db")
    db = DatabaseManager(ruta)
    with sqlite3.connect(ruta) as conn:
        producto_id = conn.execute(
            "INSERT INTO productos (codigo, descripcion, precio_lista, stock_actual) "
            "VALUES ('TEST-REC', 'Prueba recepción', 10, 0)"
        ).lastrowid
    orden_id = db.crear_orden_compra([
        {"producto_id": producto_id, "cantidad": 5, "precio_costo": 2}
    ])
    assert orden_id > 0
    detalle = db.obtener_orden_compra(orden_id)
    item_id = int(detalle["items"][0]["id"])
    return ruta, producto_id, orden_id, item_id


def test_recepcion_parcial_y_total(tmp_path):
    ruta, producto, orden, item = _preparar(tmp_path)
    db = DatabaseManager(ruta)
    assert db.recibir_orden_compra(orden, {item: 2})[0]
    assert db.recibir_orden_compra(orden, {item: 3})[0]
    assert not db.recibir_orden_compra(orden, {item: 1})[0]
    with sqlite3.connect(ruta) as conn:
        assert conn.execute("SELECT stock_actual FROM productos WHERE id=?", (producto,)).fetchone()[0] == 5
        assert conn.execute("SELECT cantidad_recibida FROM orden_compra_items WHERE id=?", (item,)).fetchone()[0] == 5
        assert conn.execute("SELECT COUNT(*) FROM movimientos_stock WHERE producto_id=? AND tipo='ingreso'", (producto,)).fetchone()[0] == 2


def test_recepcion_invalida_no_modifica_stock(tmp_path):
    ruta, producto, orden, item = _preparar(tmp_path)
    db = DatabaseManager(ruta)
    for payload in ({item: -1}, {item: 0}, {item: "abc"}, [{"item_id": item, "cantidad": None}]):
        assert not db.recibir_orden_compra(orden, payload)[0]
    with sqlite3.connect(ruta) as conn:
        assert conn.execute("SELECT stock_actual FROM productos WHERE id=?", (producto,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM orden_compra_recepciones WHERE orden_id=?", (orden,)).fetchone()[0] == 0


def test_dos_recepciones_simultaneas_no_duplican_stock(tmp_path):
    ruta, producto, orden, item = _preparar(tmp_path)
    barrera = threading.Barrier(2)
    resultados = []
    def recibir():
        db = DatabaseManager(ruta)
        barrera.wait(timeout=10)
        resultados.append(db.recibir_orden_compra(orden, {item: 5})[0])
    hilos = [threading.Thread(target=recibir) for _ in range(2)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=15)
        assert not hilo.is_alive()
    assert sorted(resultados) == [False, True]
    with sqlite3.connect(ruta) as conn:
        assert conn.execute("SELECT stock_actual FROM productos WHERE id=?", (producto,)).fetchone()[0] == 5
        assert conn.execute("SELECT COUNT(*) FROM movimientos_stock WHERE producto_id=? AND tipo='ingreso'", (producto,)).fetchone()[0] == 1


def test_confirmar_total_tras_recepcion_parcial(tmp_path):
    ruta, producto, orden, item = _preparar(tmp_path)
    db = DatabaseManager(ruta)
    assert db.recibir_orden_compra(orden, {item: 2})[0]
    assert db.confirmar_orden_compra(orden)[0]
    assert not db.confirmar_orden_compra(orden)[0]
    with sqlite3.connect(ruta) as conn:
        assert conn.execute(
            "SELECT stock_actual FROM productos WHERE id=?", (producto,)
        ).fetchone()[0] == 5
        assert conn.execute(
            "SELECT cantidad_recibida FROM orden_compra_items WHERE id=?", (item,)
        ).fetchone()[0] == 5


def test_confirmacion_total_y_recepcion_simultaneas_no_duplican(tmp_path):
    ruta, producto, orden, item = _preparar(tmp_path)
    barrera = threading.Barrier(2)
    resultados = []

    def confirmar():
        db = DatabaseManager(ruta)
        barrera.wait(timeout=10)
        resultados.append(db.confirmar_orden_compra(orden)[0])

    def recibir():
        db = DatabaseManager(ruta)
        barrera.wait(timeout=10)
        resultados.append(db.recibir_orden_compra(orden, {item: 5})[0])

    hilos = [threading.Thread(target=confirmar), threading.Thread(target=recibir)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=15)
        assert not hilo.is_alive()
    assert sorted(resultados) == [False, True]
    with sqlite3.connect(ruta) as conn:
        assert conn.execute(
            "SELECT stock_actual FROM productos WHERE id=?", (producto,)
        ).fetchone()[0] == 5
        assert conn.execute(
            "SELECT COUNT(*) FROM movimientos_stock WHERE producto_id=? AND tipo='ingreso'",
            (producto,),
        ).fetchone()[0] == 1

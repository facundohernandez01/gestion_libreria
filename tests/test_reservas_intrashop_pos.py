"""Las reservas de tótems deben impedir ventas simultáneas del POS."""
import sqlite3
import threading

from database_manager import DatabaseManager
import intrashop_checkout_store as checkout


def _preparar(tmp_path):
    ruta = str(tmp_path / "reservas.db")
    db = DatabaseManager(ruta)
    with sqlite3.connect(ruta) as conn:
        conn.execute("ALTER TABLE productos ADD COLUMN disponible_tienda INTEGER DEFAULT 0")
        producto = conn.execute(
            "INSERT INTO productos (codigo, descripcion, precio_lista, stock_actual, disponible_tienda) "
            "VALUES ('TEST-RESERVA', 'Producto reservado', 10, 5, 1)"
        ).lastrowid
        caja = conn.execute(
            "INSERT INTO cajas (fecha_apertura, importe_apertura, estado) "
            "VALUES (CURRENT_TIMESTAMP, 0, 'abierta')"
        ).lastrowid
        checkout.ensure_schema(conn)
        conn.execute(
            "INSERT INTO intrashop_mp_bindings "
            "(terminal_id, terminal_type, pos_external_id, store_external_id, qr_url) "
            "VALUES ('totem-test', 'totem', 'pos-test', 'store-test', 'https://example.test/qr')"
        )
    return ruta, producto, caja


def _reservar(ruta, producto, checkout_id, cantidad):
    with sqlite3.connect(ruta, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("BEGIN IMMEDIATE")
        checkout.reserve(conn, checkout_id, "totem-test", [
            {"producto_id": producto, "cantidad": cantidad, "descripcion": "Producto reservado"}
        ], 10 * cantidad)
        conn.commit()


def test_reserva_bloquea_venta_y_cancelacion_libera(tmp_path):
    ruta, producto, caja = _preparar(tmp_path)
    _reservar(ruta, producto, "checkout-test", 4)
    db = DatabaseManager(ruta)
    assert db.crear_venta(caja, [
        {"producto_id": producto, "cantidad": 2, "precio_unitario": 10}
    ]) == (0, False)
    with sqlite3.connect(ruta) as conn:
        conn.execute("BEGIN IMMEDIATE")
        checkout.set_status(conn, "checkout-test", "cancelled")
        conn.commit()
    venta, ok = db.crear_venta(caja, [
        {"producto_id": producto, "cantidad": 2, "precio_unitario": 10}
    ])
    assert ok and venta > 0
    with sqlite3.connect(ruta) as conn:
        assert conn.execute(
            "SELECT stock_actual FROM productos WHERE id=?", (producto,)
        ).fetchone()[0] == 3


def test_reserva_y_venta_simultaneas_no_sobrevenden(tmp_path):
    ruta, producto, caja = _preparar(tmp_path)
    barrier = threading.Barrier(2)
    resultados = []

    def reservar():
        barrier.wait(timeout=10)
        try:
            _reservar(ruta, producto, "checkout-test", 4)
            resultados.append("reserva")
        except ValueError:
            resultados.append("rechazada")

    def vender():
        db = DatabaseManager(ruta)
        barrier.wait(timeout=10)
        resultados.append("venta" if db.crear_venta(caja, [
            {"producto_id": producto, "cantidad": 4, "precio_unitario": 10}
        ])[1] else "rechazada")

    hilos = [threading.Thread(target=reservar), threading.Thread(target=vender)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=15)
        assert not hilo.is_alive()
    assert sorted(resultados) in (["rechazada", "reserva"], ["rechazada", "venta"])
    with sqlite3.connect(ruta) as conn:
        conn.row_factory = sqlite3.Row
        assert checkout.available(conn, producto) >= 0

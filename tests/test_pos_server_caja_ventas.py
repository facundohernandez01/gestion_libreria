"""Integración API POS: caja y venta, usando únicamente SQLite descartable.

No conecta a Mercado Pago ni escribe sobre la base operativa del comercio.
"""
import sqlite3

import httpx
import pytest
from fastapi import HTTPException

import api_server as api
from api_client import ApiClient
from database_manager import DatabaseManager
import intrashop_checkout_store as store


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = str(tmp_path / "pos-http-caja.db")
    DatabaseManager(path)
    monkeypatch.setattr(api, "DB_PATH", path)
    monkeypatch.setattr(api, "API_KEY", "TEST-LAN-KEY")
    with sqlite3.connect(path) as conn:
        pid = conn.execute(
            "INSERT INTO productos (codigo,descripcion,precio_lista,stock_actual) "
            "VALUES ('TEST-ITEM','Producto prueba',10,5)"
        ).lastrowid
        cols = {r[1] for r in conn.execute("PRAGMA table_info(productos)")}
        if "disponible_tienda" not in cols:
            conn.execute("ALTER TABLE productos ADD COLUMN disponible_tienda INTEGER NOT NULL DEFAULT 0")
        conn.execute("UPDATE productos SET disponible_tienda=1 WHERE id=?", (pid,))
    return path, pid


def _items(pid, *cantidades):
    return [
        {"producto_id": pid, "cantidad": cant, "precio_unitario": 10}
        for cant in cantidades
    ]


def _open():
    return api.abrir_caja(importe_apertura=100, observaciones="Apertura test",
                          x_api_key="TEST-LAN-KEY")["id"]


def test_abrir_caja_usa_columnas_reales_y_no_duplica(db):
    path, _ = db
    caja = _open()
    assert caja > 0
    with sqlite3.connect(path) as conn:
        fecha, importe, obs = conn.execute(
            "SELECT fecha_apertura, importe_apertura, observaciones_apertura "
            "FROM cajas WHERE id=?", (caja,),
        ).fetchone()
        assert fecha and importe == 100 and obs == "Apertura test"
    with pytest.raises(HTTPException) as exc:
        _open()
    assert exc.value.status_code == 409
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM cajas").fetchone()[0] == 1


def test_venta_no_sobrevende_producto_repetido_y_actualiza_movimientos(db):
    path, pid = db
    caja = _open()
    with pytest.raises(HTTPException) as exc:
        api.crear_venta(
            api.VentaIn(caja_id=caja, items=_items(pid, 3, 3)),
            x_api_key="TEST-LAN-KEY",
        )
    assert exc.value.status_code == 409
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM ventas").fetchone()[0] == 0
        assert conn.execute(
            "SELECT stock_actual FROM productos WHERE id=?", (pid,)
        ).fetchone()[0] == 5

    result = api.crear_venta(
        api.VentaIn(caja_id=caja, items=_items(pid, 2, 3)),
        x_api_key="TEST-LAN-KEY",
    )
    assert result["total"] == 50
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM ventas").fetchone()[0] == 1
        assert conn.execute(
            "SELECT stock_actual FROM productos WHERE id=?", (pid,)
        ).fetchone()[0] == 0
        movements = conn.execute(
            "SELECT stock_anterior, stock_nuevo FROM movimientos_stock "
            "WHERE referencia_id=? AND tipo='venta' ORDER BY id",
            (result["venta_id"],),
        ).fetchall()
        assert movements == [(5, 3), (3, 0)]


def test_venta_pos_respeta_reservas_de_totem(db):
    path, pid = db
    caja = _open()
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        store.ensure_schema(conn)
        conn.execute(
            "INSERT INTO intrashop_mp_bindings "
            "(terminal_id,terminal_type,pos_external_id,store_external_id,qr_url) "
            "VALUES('totem-test','totem','POS-A','STORE-A','https://example.test/qr')"
        )
        conn.commit()
        conn.execute("BEGIN IMMEDIATE")
        store.reserve(conn, "checkout-test", "totem-test", [
            {"producto_id": pid, "cantidad": 4, "descripcion": "Producto prueba",
             "precio_unitario": 10},
        ], 40)
        conn.commit()

    with pytest.raises(HTTPException) as exc:
        api.crear_venta(
            api.VentaIn(caja_id=caja, items=_items(pid, 2)),
            x_api_key="TEST-LAN-KEY",
        )
    assert exc.value.status_code == 409
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM ventas").fetchone()[0] == 0
        assert conn.execute("SELECT stock_actual FROM productos").fetchone()[0] == 5


def test_cierre_calcula_importes_y_no_se_repite(db):
    path, pid = db
    caja = _open()
    api.crear_venta(
        api.VentaIn(caja_id=caja, items=_items(pid, 2)),
        x_api_key="TEST-LAN-KEY",
    )
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO gastos (caja_id,monto,concepto) VALUES (?,?,?)",
            (caja, 5, "Transporte"),
        )
    assert api.cerrar_caja(caja, "Cierre test", x_api_key="TEST-LAN-KEY") == {"ok": True}
    with sqlite3.connect(path) as conn:
        fila = conn.execute(
            "SELECT estado,fecha_cierre,importe_cierre,total_ventas,total_gastos,"
            "observaciones_cierre FROM cajas WHERE id=?", (caja,),
        ).fetchone()
    assert fila[0] == "cerrada" and fila[1] and fila[2:5] == (115, 20, 5)
    assert fila[5] == "Cierre test"
    with pytest.raises(HTTPException) as exc:
        api.cerrar_caja(caja, x_api_key="TEST-LAN-KEY")
    assert exc.value.status_code == 409


def test_no_cierra_caja_con_cobros_intrashop_pendientes(db):
    path, pid = db
    caja = _open()
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        store.ensure_schema(conn)
        conn.execute(
            "INSERT INTO intrashop_mp_bindings "
            "(terminal_id,terminal_type,pos_external_id,store_external_id,qr_url) "
            "VALUES('totem-test','totem','POS-A','STORE-A','https://example.test/qr')"
        )
        conn.commit()
        conn.execute("BEGIN IMMEDIATE")
        store.reserve(conn, "checkout-test", "totem-test", [
            {"producto_id": pid, "cantidad": 1, "descripcion": "Producto prueba",
             "precio_unitario": 10},
        ], 10)
        conn.commit()

    with pytest.raises(HTTPException) as exc:
        api.cerrar_caja(caja, x_api_key="TEST-LAN-KEY")
    assert exc.value.status_code == 409
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT estado FROM cajas WHERE id=?", (caja,)).fetchone()[0] == "abierta"
        store.set_status(conn, "checkout-test", "cancelled")
    assert api.cerrar_caja(caja, x_api_key="TEST-LAN-KEY") == {"ok": True}


@pytest.mark.parametrize("method,expected", [
    ("abrir_caja", 0),
    ("cerrar_caja", False),
    ("crear_venta", (0, False)),
])
def test_cliente_no_confunde_rechazos_http_con_exito(method, expected, monkeypatch):
    client = ApiClient("http://127.0.0.1:1", "TEST-LAN-KEY")
    request = httpx.Request("POST", "http://127.0.0.1:1/cajas/abrir")
    response = httpx.Response(409, request=request)

    def fail(*args, **kwargs):
        raise httpx.HTTPStatusError("Conflicto", request=request, response=response)

    monkeypatch.setattr(client, "_post", fail)
    if method == "abrir_caja":
        got = client.abrir_caja(0)
    elif method == "cerrar_caja":
        got = client.cerrar_caja(1)
    else:
        got = client.crear_venta(1, [{"producto_id": 1, "cantidad": 1,
                                      "precio_unitario": 10}])
    assert got == expected

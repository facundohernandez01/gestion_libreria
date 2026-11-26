"""Arqueo POS local/API con SQLite aislada (sin tocar libreria.db)."""
from pathlib import Path
import sqlite3

import httpx
import pytest
from fastapi import HTTPException

import api_server as api
from api_client import ApiClient
from database_manager import DatabaseManager
from services.caja_cierre import resumen_caja


@pytest.fixture
def caja_db(tmp_path, monkeypatch):
    path = str(tmp_path / "arqueo.db")
    local = DatabaseManager(path)
    monkeypatch.setattr(api, "DB_PATH", path)
    monkeypatch.setattr(api, "API_KEY", "TEST-LAN-KEY")
    return path, local


def _abrir():
    return api.abrir_caja(importe_apertura=100, x_api_key="TEST-LAN-KEY")["id"]


def _movimientos(path, caja):
    with sqlite3.connect(path) as conn:
        for amount, method in ((20, "efectivo"), (30, "mercadopago_qr"),
                               (25, "tarjeta_debito")):
            conn.execute(
                "INSERT INTO ventas(caja_id,total,metodo_pago,estado) "
                "VALUES(?,?,?,'completada')",
                (caja, amount, method),
            )
        conn.execute(
            "INSERT INTO gastos(caja_id,monto,concepto) VALUES(?,?,?)",
            (caja, 5, "Transporte"),
        )
        conn.commit()


def test_resumen_caja_incluye_todos_los_dias_y_separa_electronicos(caja_db):
    path, local = caja_db
    caja = _abrir()
    _movimientos(path, caja)
    rem = api.resumen_caja(caja, x_api_key="TEST-LAN-KEY")
    assert rem["importe_apertura"] == 100
    assert rem["ventas_efectivo"] == 20
    assert rem["ventas_otros_medios"] == 55
    assert rem["total_ventas"] == 75
    assert rem["total_gastos"] == 5
    assert rem["efectivo_esperado"] == 115
    assert rem["cantidad_ventas"] == 3
    assert len(rem["gastos"]) == 1
    assert local.obtener_resumen_caja(caja)["efectivo_esperado"] == 115


def test_cierre_con_diferencia_guarda_conteo_y_observacion_en_servidor(caja_db):
    path, local = caja_db
    caja = _abrir()
    _movimientos(path, caja)
    preview = api.resumen_caja(caja, x_api_key="TEST-LAN-KEY")
    result = api.cerrar_caja(
        caja, x_api_key="TEST-LAN-KEY",
        body=api.CierreCajaIn(
            importe_contado=112, observaciones="Faltante de cambio",
            efectivo_esperado=preview["efectivo_esperado"],
            total_ventas=preview["total_ventas"],
            total_gastos=preview["total_gastos"],
        ),
    )
    assert result["ok"] and result["efectivo_esperado"] == 115
    assert result["efectivo_contado"] == 112
    assert result["diferencia_arqueo"] == -3
    with sqlite3.connect(path) as conn:
        saved = conn.execute(
            "SELECT estado,importe_cierre,efectivo_esperado,efectivo_contado,"
            "diferencia_arqueo,total_ventas,total_gastos,observaciones_cierre "
            "FROM cajas WHERE id=?", (caja,),
        ).fetchone()
        assert saved == ("cerrada", 112, 115, 112, -3, 75, 5, "Faltante de cambio")
    with pytest.raises(HTTPException) as exc:
        api.cerrar_caja(caja, x_api_key="TEST-LAN-KEY")
    assert exc.value.status_code == 409


def test_local_cierra_con_misma_logica_y_no_cierra_dos_veces(caja_db):
    path, local = caja_db
    caja = _abrir()
    _movimientos(path, caja)
    snapshot = local.obtener_resumen_caja(caja)
    result = local.cerrar_caja_arqueo(
        caja, 117, "Sobrante en conteo",
        snapshot={key: snapshot[key] for key in
                  ("efectivo_esperado", "total_ventas", "total_gastos")},
    )
    assert result["diferencia_arqueo"] == 2
    assert local.cerrar_caja(caja) is False


def test_impedir_cierre_sin_explicacion_de_sobrante(caja_db):
    path, _ = caja_db
    caja = _abrir()
    with pytest.raises(HTTPException) as exc:
        api.cerrar_caja(
            caja, x_api_key="TEST-LAN-KEY",
            body=api.CierreCajaIn(importe_contado=105),
        )
    assert "observación" in str(exc.value.detail)
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT estado FROM cajas WHERE id=?", (caja,)).fetchone()[0] == "abierta"


def test_rechaza_arqueo_obsoleto_si_hubo_venta_durante_conteo(caja_db):
    path, _ = caja_db
    caja = _abrir()
    preview = api.resumen_caja(caja, x_api_key="TEST-LAN-KEY")
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO ventas(caja_id,total,metodo_pago,estado) "
            "VALUES(?,10,'efectivo','completada')", (caja,),
        )
        conn.commit()
    with pytest.raises(HTTPException) as exc:
        api.cerrar_caja(
            caja, x_api_key="TEST-LAN-KEY",
            body=api.CierreCajaIn(
                importe_contado=100, observaciones="Conté antes de última venta",
                efectivo_esperado=preview["efectivo_esperado"],
                total_ventas=preview["total_ventas"],
                total_gastos=preview["total_gastos"],
            ),
        )
    assert "Actualizá el resumen" in str(exc.value.detail)


def test_pending_checkout_impide_cerrar_pero_comunica_causa(caja_db):
    path, _ = caja_db
    caja = _abrir()
    api.resumen_caja(caja, x_api_key="TEST-LAN-KEY")
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO intrashop_checkouts "
            "(id,pos_external_id,store_external_id,estado,total,items_json,created_at,updated_at,caja_id) "
            "VALUES('pendiente-qr','POS-1','STORE-1','uncertain',30,'[]',1,1,?)",
            (caja,),
        )
        conn.commit()
    preview = api.resumen_caja(caja, x_api_key="TEST-LAN-KEY")
    assert preview["cobros_pendientes"] == 1
    with pytest.raises(HTTPException) as exc:
        api.cerrar_caja(
            caja, x_api_key="TEST-LAN-KEY",
            body=api.CierreCajaIn(importe_contado=100),
        )
    assert exc.value.status_code == 409
    assert "IntraShop" in str(exc.value.detail)
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT estado FROM cajas WHERE id=?", (caja,)).fetchone()[0] == "abierta"


def test_cliente_muestra_el_motivo_del_409_en_vez_de_false(monkeypatch):
    client = ApiClient("http://127.0.0.1:8000", "TEST-LAN-KEY")
    request = httpx.Request("POST", "http://127.0.0.1:8000/cajas/1/cerrar")
    response = httpx.Response(409, json={"detail": "Cobros pendientes en caja 1"},
                              request=request)

    def fail(*args, **kwargs):
        raise httpx.HTTPStatusError("Conflict", request=request, response=response)

    monkeypatch.setattr(client, "_post", fail)
    with pytest.raises(ValueError, match="Cobros pendientes en caja 1"):
        client.cerrar_caja_arqueo(1, 100)


def test_modal_de_cierre_tiene_arqueo_y_refresca_desde_bd():
    code = (Path(__file__).resolve().parents[1] /
            "componente_cerrar_caja.py").read_text(encoding="utf-8")
    assert "db_manager.obtener_resumen_caja(caja_id)" in code
    assert "db_manager.cerrar_caja_arqueo(" in code
    assert "Faltante:" in code and "Sobrante:" in code
    assert "current[\"resumen\"][\"cobros_pendientes\"]" in code
    assert "snapshot=snapshot" in code


def test_no_se_pueden_agregar_gastos_despues_del_cierre(caja_db):
    path, local = caja_db
    caja = _abrir()
    assert local.agregar_gasto(caja, 5, "Movilidad") > 0
    assert api.cerrar_caja(
        caja, x_api_key="TEST-LAN-KEY",
        body=api.CierreCajaIn(importe_contado=95),
    )["ok"]
    assert local.agregar_gasto(caja, 2, "Gasto posterior") == 0
    with pytest.raises(HTTPException) as exc:
        api.api_agregar_gasto(
            caja, {"monto": 2, "concepto": "Gasto posterior"},
            x_api_key="TEST-LAN-KEY",
        )
    assert exc.value.status_code == 409
    with sqlite3.connect(path) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM gastos WHERE caja_id=?", (caja,)
        ).fetchone()[0] == 1


def test_rechaza_arqueo_no_finito(caja_db):
    path, _ = caja_db
    caja = _abrir()
    for count in (float("nan"), float("inf"), -1):
        with pytest.raises(HTTPException) as exc:
            api.cerrar_caja(
                caja, x_api_key="TEST-LAN-KEY",
                body=api.CierreCajaIn(importe_contado=count),
            )
        assert exc.value.status_code == 409
    with sqlite3.connect(path) as conn:
        assert conn.execute(
            "SELECT estado FROM cajas WHERE id=?", (caja,)
        ).fetchone()[0] == "abierta"

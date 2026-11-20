"""Control estructural: cancelar en el POS no debe dejar un QR activo."""
import ast
from pathlib import Path


SOURCE = (
    Path(__file__).resolve().parents[1] / "componente_nueva_venta.py"
).read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def _code(name):
    node = next(
        x for x in ast.walk(TREE)
        if isinstance(x, ast.FunctionDef) and x.name == name
    )
    return ast.get_source_segment(SOURCE, node)


def test_cancelar_pos_cierra_interfaz_sin_esperar_respuesta_remota():
    code = _code("cancelar_qr")
    assert "cancel_event.set()" in code
    assert 'pagando_qr["activo"] = False' in code
    assert "col_izquierda.content = log_box" in code
    assert 'mostrar_mensaje("Cobro QR cancelado."' in code
    assert "verificar_pago_referencia" not in code


def test_worker_no_registra_venta_tras_cancelar():
    code = _code("_registrar_pago_confirmado")
    assert 'if cancel_event.is_set() or pagando_qr["cancelado"]:' in code
    assert 'confirmar_venta(metodo_pago="mercadopago_qr", imprimir=True' in code


def test_pos_exige_referencia_unica_e_importe_verificado():
    code = _code("pagar_con_qr")
    assert "referencia = uuid.uuid4().hex" in code
    assert "reference=referencia" in code
    assert "mp_service.cerrar_orden_referencia(" in code
    assert "mp_service.verificar_pago_referencia(referencia, total)" in code
    assert 'pago["estado"] == "approved"' in code


def test_boton_abortar_solicita_cancelacion_remota():
    code = _code("abortar")
    assert 'if pagando_qr["activo"]:' in code
    assert 'getattr(pagar_con_qr, "_cancelar", None)' in code
    assert "cancelar()" in code

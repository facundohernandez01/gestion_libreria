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


def test_cancelar_pos_no_equivale_a_cerrar_solo_el_modal():
    code = _code("cancelar_qr")
    assert "cancel_event.set()" in code
    assert 'qr_estado.value = "Cancelando la orden en Mercado Pago…"' in code
    assert 'pagando_qr["activo"] = False' not in code
    assert 'mostrar_error("Pago QR cancelado")' not in code


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

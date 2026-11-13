"""Regresiones estructurales de cancelación QR sin llamar a Mercado Pago."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _func(name):
    source = (ROOT / "intrashop_api.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    return next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)


def test_cancelacion_incierta_no_devuelve_exito():
    node = _func("cancelar_checkout")
    source = ast.get_source_segment(
        (ROOT / "intrashop_api.py").read_text(encoding="utf-8"), node
    )
    assert 'in {"error", "cancel_error"}' in source
    assert "HTTPException(" in source
    assert "409" in source
    assert 'job.get("status") == "cancelling"' in source


def test_cancelacion_durante_creacion_no_republica_qr():
    source = (ROOT / "intrashop_api.py").read_text(encoding="utf-8")
    node = _func("_run_checkout")
    code = ast.get_source_segment(source, node)
    assert 'if cancel_event.is_set():' in code
    assert 'status="cancelling"' in code
    assert "_cerrar_qr_checkout(" in code
    assert 'verification["estado"] == "no_payment"' not in code

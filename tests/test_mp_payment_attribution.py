"""Verifica que IntraShop no registre ventas por un pago de otro checkout."""
import ast
from pathlib import Path

SOURCE = (Path(__file__).resolve().parents[1] / "intrashop_api.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def _function(name):
    node = next(
        n for n in TREE.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name
    )
    return ast.get_source_segment(SOURCE, node)


def test_polling_pagado_exige_validacion_referencia_y_monto():
    code = _function("_run_checkout")
    assert "mp_service.verificar_pago_referencia(job_id, total)" in code
    assert 'if verification["estado"] != "approved":' in code
    assert "Reserva retenida hasta conciliar" in code
    assert 'confirmed = paid or verification["estado"] == "approved"' not in code
    assert 'confirmed = verification["estado"] == "approved"' in code


def test_recuperacion_tras_reinicio_verifica_referencia():
    code = _function("_reconcile_checkout_impl")
    assert "mp_service.verificar_pago_referencia(checkout_id, row[\"total\"])" in code
    assert 'if verification["estado"] != "approved":' in code

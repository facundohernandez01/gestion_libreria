"""Contratos conservadores de cancelación de órdenes QR."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_delete_404_no_se_considera_cancelacion_confirmada():
    source = (ROOT / "services" / "mercadopago_service.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    service = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and any(
            isinstance(child, ast.FunctionDef) and child.name == "cancelar_orden"
            for child in node.body
        )
    )
    method = next(node for node in service.body if isinstance(node, ast.FunctionDef) and node.name == "cancelar_orden")
    code = ast.get_source_segment(source, method)
    assert "resp.status_code in (200, 202, 204)" in code
    assert "resp.status_code in (200, 202, 204, 404)" not in code


def test_liberacion_automatica_exige_cierre_y_verificacion():
    source = (ROOT / "intrashop_api.py").read_text(encoding="utf-8")
    assert 'closed and verification["estado"] == "no_payment"' in source
    assert 'verification["estado"] == "approved"' in source

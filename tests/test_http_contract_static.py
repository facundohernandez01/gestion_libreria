"""Comprobaciones estáticas de rutas HTTP POS cliente/servidor.

No sustituyen pruebas de integración con FastAPI y SQLite.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _parse(filename):
    return ast.parse((ROOT / filename).read_text(encoding="utf-8"))


def test_no_duplicate_api_routes():
    tree = _parse("api_server.py")
    routes = {}
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for deco in node.decorator_list:
            if not isinstance(deco, ast.Call) or not isinstance(deco.func, ast.Attribute):
                continue
            if not isinstance(deco.func.value, ast.Name) or deco.func.value.id != "app":
                continue
            if deco.func.attr.upper() not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                continue
            if not deco.args or not isinstance(deco.args[0], ast.Constant):
                continue
            key = (deco.func.attr.upper(), deco.args[0].value)
            assert key not in routes, f"Ruta duplicada: {key}: {routes.get(key)} / {node.name}"
            routes[key] = node.name


def test_replenishment_routes_are_declared():
    tree = _parse("api_server.py")
    paths = {
        deco.args[0].value
        for node in tree.body if isinstance(node, ast.FunctionDef)
        for deco in node.decorator_list
        if isinstance(deco, ast.Call) and isinstance(deco.func, ast.Attribute)
        and deco.args and isinstance(deco.args[0], ast.Constant)
    }
    assert {"/proveedores", "/reposicion/ordenes", "/reposicion/stock",
            "/reposicion/ordenes/{orden_id}/recibir"} <= paths

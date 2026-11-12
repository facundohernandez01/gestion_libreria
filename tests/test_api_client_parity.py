"""Contrato estático: los métodos públicos de DatabaseManager deben existir en ApiClient.

No requiere Flet, SQLite ni un servidor activo; detecta regresiones en CI.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _methods(filename: str) -> set[str]:
    module = ast.parse((ROOT / filename).read_text(encoding="utf-8"))
    classes = {node.name: node for node in module.body if isinstance(node, ast.ClassDef)}
    name = "DatabaseManager" if filename == "database_manager.py" else "ApiClient"
    return {
        node.name
        for node in classes[name].body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not node.name.startswith("_")
    }


def test_database_manager_api_client_parity():
    db_methods = _methods("database_manager.py")
    api_methods = _methods("api_client.py")
    # Estas operaciones son deliberadamente locales o administrativas, nunca
    # deben ejecutarse desde el cliente con una conexión SQLite.
    server_only = {
        "get_connection", "init_database", "set_usuario_actual",
        "limpiar_datos_prueba",
    }
    missing = sorted(db_methods - api_methods - server_only)
    assert not missing, (
        "Métodos DatabaseManager sin implementación HTTP en ApiClient: "
        + ", ".join(missing)
    )

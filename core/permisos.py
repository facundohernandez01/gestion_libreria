"""Permisos de roles y usuarios.

Cada permiso representa una sección/acción del sistema. Los roles guardan un
JSON ``{clave: bool}`` en la tabla ``roles``. El rol marcado como ``es_admin``
siempre tiene todos los permisos y es el único que puede administrar roles.
"""
from __future__ import annotations

PERMISOS = [
    ("CAJA", "Abrir y cerrar caja"),
    ("VENTAS", "Vender / nueva venta"),
    ("ARTICULOS", "Gestionar artículos"),
    ("STOCK", "Ingreso y movimientos de stock"),
    ("COMPRAS", "Órdenes de compra y recepción"),
    ("PROVEEDORES", "Proveedores"),
    ("HISTORIAL_CAJAS", "Historial de cajas"),
    ("REPORTES", "Reportes"),
    ("CONFIGURACION", "Ajustes del sistema"),
]

CLAVES = [clave for clave, _ in PERMISOS]
ETIQUETAS = dict(PERMISOS)


def permisos_todos() -> dict:
    return {clave: True for clave in CLAVES}


def permisos_vacios() -> dict:
    return {clave: False for clave in CLAVES}


def permisos_caja() -> dict:
    """Rol operativo de caja: vender, caja, artículos y stock."""
    permisos = permisos_vacios()
    for clave in ("CAJA", "VENTAS", "ARTICULOS", "STOCK"):
        permisos[clave] = True
    return permisos


def normalizar(permisos) -> dict:
    if isinstance(permisos, str):
        import json

        try:
            permisos = json.loads(permisos or "{}")
        except (TypeError, ValueError):
            permisos = {}
    permisos = permisos if isinstance(permisos, dict) else {}
    return {clave: bool(permisos.get(clave)) for clave in CLAVES}


def tiene(permisos: dict, clave: str, es_admin: bool = False) -> bool:
    if es_admin:
        return True
    return bool((permisos or {}).get(clave))

"""Factory de acceso a datos según modo: local (SQLite) o cliente (HTTP).

Modo servidor usa DatabaseManager local. Modo cliente usa ApiClient contra el
servidor LAN. La selección se guarda en la tabla config (MODO_RED) y .env.
"""
from __future__ import annotations

import os

from core.settings import settings


def es_edicion_intrashop() -> bool:
    """En esta rama el POS es cliente del servidor externo por defecto.

    POS_API_ONLY identifica al proceso servidor y evita aplicar esta regla allí.
    INTRASHOP_EDITION=0 permite compatibilidad temporal y pruebas de migración.
    """
    if os.getenv("POS_API_ONLY", "").strip() == "1":
        return False
    return os.getenv("INTRASHOP_EDITION", "1").strip().lower() not in (
        "0", "false", "no", "off"
    )


def _modo_red() -> str:
    if es_edicion_intrashop():
        return "cliente"
    modo = os.getenv("MODO_RED", "").strip().lower()
    try:
        from database_manager import DatabaseManager

        val = DatabaseManager().get_config_value("MODO_RED")
        if val and val.strip().lower() in ("servidor", "cliente", "local"):
            return val.strip().lower()
    except Exception:
        pass
    return modo if modo in ("servidor", "cliente", "local") else "local"


def _server_url() -> str:
    url = os.getenv("SERVER_URL", "").strip()
    # IntraShop no debe leer configuración de conexión desde una SQLite
    # potencialmente distinta de la base del servidor.
    if es_edicion_intrashop():
        return url or settings.server_url or "http://127.0.0.1:8000"
    try:
        from database_manager import DatabaseManager

        val = DatabaseManager().get_config_value("SERVER_URL")
        if val and val.strip():
            return val.strip()
    except Exception:
        pass
    return url or settings.server_url or "http://127.0.0.1:8000"


def crear_acceso_datos():
    """Devuelve (objeto, modo)."""
    modo = _modo_red()
    if modo == "cliente":
        from api_client import ApiClient

        return ApiClient(_server_url(), settings.api_key), "cliente"
    from database_manager import DatabaseManager

    return DatabaseManager(), modo


def es_servidor() -> bool:
    return _modo_red() in ("servidor", "local")


def modo_actual() -> str:
    return _modo_red()

"""Factory de acceso a datos según modo: local (SQLite) o cliente (HTTP).

Modo servidor usa DatabaseManager local. Modo cliente usa ApiClient contra el
servidor LAN. La selección se guarda en la tabla config (MODO_RED) y .env.
"""
from __future__ import annotations

import os

from core.settings import settings


def _modo_red() -> str:
    modo = os.getenv("MODO_RED", "").strip().lower()
    if modo in ("servidor", "cliente", "local"):
        return modo
    try:
        from database_manager import DatabaseManager

        val = DatabaseManager().get_config_value("MODO_RED")
        if val and val.strip().lower() in ("servidor", "cliente", "local"):
            return val.strip().lower()
    except Exception:
        pass
    return "local"


def _server_url() -> str:
    url = os.getenv("SERVER_URL", "").strip()
    if url:
        return url
    try:
        from database_manager import DatabaseManager

        val = DatabaseManager().get_config_value("SERVER_URL")
        if val and val.strip():
            return val.strip()
    except Exception:
        pass
    return settings.server_url or "http://127.0.0.1:8000"


def crear_acceso_datos():
    """Devuelve (objeto, modo)."""
    modo = _modo_red()
    if modo == "cliente":
        from api_client import ApiClient

        return ApiClient(_server_url(), os.getenv("API_KEY", "libreria-lan")), "cliente"
    from database_manager import DatabaseManager

    return DatabaseManager(), modo


def es_servidor() -> bool:
    return _modo_red() in ("servidor", "local")


def modo_actual() -> str:
    return _modo_red()

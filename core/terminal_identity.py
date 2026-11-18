"""Identidad estable de la terminal POS.

IntraShop LAN persiste el ID *en el equipo cliente*, sin abrir la SQLite del
servidor. Kiosmico local conserva la identidad histórica de su base SQLite.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import uuid


def _identity_path() -> Path:
    if os.name == "nt":
        base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Local"
    else:
        base = os.getenv("XDG_CONFIG_HOME")
        root = Path(base) if base else Path.home() / ".config"
    return root / "intrashop" / "pos-terminal-id"


def _client_terminal_id() -> str:
    path = _identity_path()
    try:
        value = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        value = ""
    if value:
        if not re.fullmatch(r"caja-[0-9a-f]{32}", value):
            raise ValueError("ID local de terminal POS corrupto; no se reemplazará automáticamente")
        return value

    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    new_value = "caja-" + uuid.uuid4().hex
    # Exclusividad: dos procesos del mismo dispositivo no generan IDs distintos.
    try:
        with path.open("x", encoding="utf-8") as file:
            file.write(new_value + "\n")
            file.flush()
            os.fsync(file.fileno())
        if os.name != "nt":
            path.chmod(0o600)
        return new_value
    except FileExistsError:
        value = path.read_text(encoding="utf-8").strip()
        if not re.fullmatch(r"caja-[0-9a-f]{32}", value):
            raise RuntimeError("Otro proceso todavía no terminó de guardar el ID de terminal")
        return value


def terminal_id() -> str:
    from core.db_factory import modo_actual
    if modo_actual() == "cliente":
        return _client_terminal_id()
    from database_manager import DatabaseManager

    db = DatabaseManager()
    value = db.get_config_value("POS_TERMINAL_ID")
    if not value:
        value = "caja-" + uuid.uuid4().hex
        db.set_config("POS_TERMINAL_ID", value)
    return value

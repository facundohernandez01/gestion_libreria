"""Dirección de POS Server, persistida por equipo cliente IntraShop.

No se usa libreria.db para guardar las preferencias del cliente LAN. Se
almacena únicamente la URL de la API, nunca usuario, token ni API key.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlsplit


def _config_path() -> Path:
    from core.terminal_identity import _identity_path
    return _identity_path().parent / "pos-server.json"


def validar_server_url(value: str) -> str:
    url = (value or "").strip().rstrip("/")
    parsed = urlsplit(url)
    if (parsed.scheme not in ("http", "https") or not parsed.hostname or
            parsed.username is not None or parsed.password is not None or
            parsed.path not in ("", "/") or parsed.query or parsed.fragment):
        raise ValueError(
            "Ingresá sólo la URL base de POS Server (http://IP:8000), "
            "sin claves, usuario, rutas ni parámetros."
        )
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("El puerto del servidor es inválido") from exc
    if parsed.hostname in ("0.0.0.0", "::") or (port is not None and port < 1):
        raise ValueError("Ingresá una IP o nombre de equipo accesible, no 0.0.0.0")
    return url


def guardar_server_url(value: str) -> str:
    validated = validar_server_url(value)
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_name(path.name + ".tmp-" + str(os.getpid()))
    try:
        with temp.open("w", encoding="utf-8") as file:
            json.dump({"url": validated}, file)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        if os.name != "nt":
            temp.chmod(0o600)
        os.replace(temp, path)
    finally:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass
    return validated


def leer_server_url() -> str:
    try:
        data = json.loads(_config_path().read_text(encoding="utf-8"))
        return validar_server_url(data.get("url", ""))
    except FileNotFoundError:
        return ""
    except (OSError, ValueError, TypeError, AttributeError):
        # Nunca tratar este archivo local como fuente de credenciales.
        # Las rutas alternativas (SERVER_URL env/localhost) siguen disponibles.
        return ""

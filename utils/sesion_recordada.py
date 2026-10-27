"""Sesión recordada para la web (/stock, /cliente): evita loguearse cada vez.

El navegador guarda un token aleatorio (SharedPreferences / localStorage) y el
servidor guarda solo su hash en ``sesiones_web.json`` junto con el usuario y la
fecha de vencimiento. Al volver, si el token es válido y el usuario sigue
activo, se entra sin pedir clave. Cerrar sesión revoca el token.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time

from utils.paths import base_dir

CLAVE_PREFS = "kiosmico_sesion"
DIAS = 30
_lock = threading.Lock()


def _archivo():
    return base_dir() / "sesiones_web.json"


def _cargar() -> dict:
    try:
        return json.loads(_archivo().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _guardar(datos: dict) -> None:
    try:
        _archivo().write_text(json.dumps(datos), encoding="utf-8")
    except OSError:
        pass


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def crear(usuario: dict) -> str:
    token = secrets.token_urlsafe(32)
    ahora = time.time()
    with _lock:
        datos = {h: v for h, v in _cargar().items() if v.get("exp", 0) > ahora}
        datos[_hash(token)] = {
            "usuario": usuario.get("usuario") or "",
            "usuario_id": int(usuario.get("id") or 0),
            "exp": ahora + DIAS * 86400,
        }
        _guardar(datos)
    return token


def validar(token: str | None, db) -> dict | None:
    """Devuelve el usuario si el token es válido y el usuario sigue activo."""
    if not token or not isinstance(token, str):
        return None
    ahora = time.time()
    with _lock:
        datos = _cargar()
        h = _hash(token)
        reg = datos.get(h)
        if not reg or reg.get("exp", 0) <= ahora:
            if reg:
                datos.pop(h, None)
                _guardar(datos)
            return None
        reg["exp"] = ahora + DIAS * 86400  # renueva mientras se use
        _guardar(datos)
    uid = int(reg.get("usuario_id") or 0)
    if uid:
        usuario = db.obtener_usuario(uid)
        return usuario if usuario and usuario.get("activo") else None
    # Clave única de versiones anteriores (no figura en la tabla de usuarios).
    from core.permisos import permisos_todos

    return {"usuario": reg.get("usuario") or "admin", "nombre": "Administrador",
            "rol": "ADMIN", "rol_id": 0, "es_admin": True, "activo": True,
            "permisos": permisos_todos()}


def revocar(token: str | None) -> None:
    if not token:
        return
    with _lock:
        datos = _cargar()
        if datos.pop(_hash(token), None) is not None:
            _guardar(datos)

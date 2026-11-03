"""OAuth de Mercado Pago desde el servidor POS, separado de caja y licencias.

El intercambio OAuth y refresh token viven en plugin_marketplace. Solo el
servidor LAN conoce el secreto de instalación. Los clientes Flet usan endpoints
de administración y nunca reciben el access_token.
"""
from __future__ import annotations

import os
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

import httpx
from cryptography.fernet import Fernet

from database_manager import DatabaseManager

_lock = threading.RLock()
_cached = None


def _db():
    return DatabaseManager()


def _hub(override=None):
    db = _db()
    raw = (override or db.get_config_value("MP_OAUTH_HUB_URL")
           or os.environ.get("MP_OAUTH_HUB_URL") or "").strip().rstrip("/")
    url = urlparse(raw)
    if not raw or (url.scheme != "https" and not
                   (url.scheme == "http" and url.hostname in ("localhost", "127.0.0.1"))):
        raise ValueError("Configurá una URL HTTPS para el backend OAuth (MP_OAUTH_HUB_URL).")
    if url.username or url.password or url.query or url.fragment or url.path not in ("", "/"):
        raise ValueError("La URL del backend debe contener solo el origen HTTPS.")
    return raw


def _cipher():
    from core.settings import settings
    # La clave debe persistir junto a la instalación local, pero no en SQLite.
    path = Path(settings.db_path).resolve().parent / ".mp-oauth-local.key"
    if not path.exists():
        try:
            with path.open("xb") as handle:
                handle.write(Fernet.generate_key())
            os.chmod(path, 0o600)
        except FileExistsError:
            pass
    return Fernet(path.read_bytes().strip())


def _secret(key):
    value = _db().get_config_value(key) or ""
    return _cipher().decrypt(value.encode()).decode() if value else ""


def _save_secret(key, value):
    _db().set_config(key, _cipher().encrypt(value.encode()).decode())


def _installation_id():
    db = _db()
    value = db.get_config_value("MP_OAUTH_INSTALLATION_ID")
    if not value:
        value = "pos-" + uuid.uuid4().hex
        db.set_config("MP_OAUTH_INSTALLATION_ID", value)
    return value


def _post(path, data, *, url=None, timeout=20):
    response = httpx.post(_hub(url) + "/api/integrations/mercadopago/" + path,
                          json=data, timeout=timeout, follow_redirects=False)
    response.raise_for_status()
    return response.json()


def start(hub_url=None):
    """Iniciar una vinculación nueva; no elimina el método manual actual."""
    with _lock:
        url = _hub(hub_url)
        response = _post("start", {"installation_id": _installation_id()}, url=url)
        db = _db()
        db.set_config("MP_OAUTH_HUB_URL", url)
        db.set_config("MP_OAUTH_SESSION_ID", response["session_id"])
        _save_secret("MP_OAUTH_SESSION_PROOF", response["session_proof"])
        _save_secret("MP_OAUTH_PENDING_INSTALLATION_SECRET", response["installation_secret"])
        # No activar el OAuth hasta comprobar que la cuenta autorizó y sincronizó.
        return {"authorize_url": response["authorize_url"],
                "expires_in": response["expires_in"]}


def status():
    """Verifica autorización; activa OAuth solo luego de obtener tokens válidos."""
    db = _db()
    session = db.get_config_value("MP_OAUTH_SESSION_ID") or ""
    if not session:
        return {"status": "connected" if db.get_config_value("MP_OAUTH_ENABLED") == "1" else "disconnected"}
    data = _post("status", {"session_id": session,
                            "session_proof": _secret("MP_OAUTH_SESSION_PROOF")})
    if data.get("status") == "connected":
        # Pedir las credenciales antes de activar el modo OAuth.
        credentials = _fetch_credentials(_secret("MP_OAUTH_PENDING_INSTALLATION_SECRET"))
        if not credentials.get("access_token") or not credentials.get("user_id"):
            raise ValueError("Mercado Pago no devolvió credenciales utilizables.")
        with _lock:
            global _cached
            _cached = (credentials["access_token"], str(credentials["user_id"]),
                       int(credentials["expires_at"]), time.monotonic())
            _save_secret("MP_OAUTH_INSTALLATION_SECRET", _secret("MP_OAUTH_PENDING_INSTALLATION_SECRET"))
            db.set_config("MP_OAUTH_PENDING_INSTALLATION_SECRET", "")
            db.set_config("MP_OAUTH_ENABLED", "1")
            db.set_config("MP_OAUTH_MP_USER_ID", str(credentials["user_id"]))
            db.set_config("MP_OAUTH_SESSION_ID", "")
            db.set_config("MP_OAUTH_SESSION_PROOF", "")
    return {"status": data.get("status", "pending"),
            "user_id": db.get_config_value("MP_OAUTH_MP_USER_ID") or ""}


def _fetch_credentials(proof=None):
    return _post("credentials", {
        "installation_id": _installation_id(),
        "installation_secret": proof or _secret("MP_OAUTH_INSTALLATION_SECRET"),
    })


def connected():
    return _db().get_config_value("MP_OAUTH_ENABLED") == "1"


def credentials():
    """Devuelve token solo para consumo interno del servidor POS.

    Se renueva periódicamente desde el backend central; una caída del backend
    permite reutilizar únicamente un token todavía válido en memoria.
    """
    global _cached
    if not connected():
        return None
    with _lock:
        if _cached and time.monotonic() - _cached[3] < 300 and _cached[2] > time.time() + 120:
            return _cached[0], _cached[1]
        try:
            result = _fetch_credentials()
            _cached = (result["access_token"], str(result["user_id"]),
                       int(result["expires_at"]), time.monotonic())
        except (httpx.HTTPError, ValueError, KeyError, OSError):
            if _cached and _cached[2] > time.time() + 120:
                return _cached[0], _cached[1]
            raise
        return _cached[0], _cached[1]


def disconnect():
    global _cached
    with _lock:
        if connected():
            _post("disconnect", {
                "installation_id": _installation_id(),
                "installation_secret": _secret("MP_OAUTH_INSTALLATION_SECRET"),
            })
        db = _db()
        db.set_config("MP_OAUTH_ENABLED", "0")
        db.set_config("MP_OAUTH_MP_USER_ID", "")
        db.set_config("MP_OAUTH_SESSION_ID", "")
        db.set_config("MP_OAUTH_INSTALLATION_SECRET", "")
        db.set_config("MP_OAUTH_SESSION_PROOF", "")
        _cached = None
        return {"status": "disconnected"}

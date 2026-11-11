"""Sesiones de operador POS para endpoints de entrega.

Los tokens se guardan en memoria del servidor y expiran a las 8 horas.
La autorización por rol se reevalúa contra la base en cada solicitud.
"""
import secrets
import threading
import time

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from database_manager import DatabaseManager
from core.permisos import tiene, normalizar

router = APIRouter(prefix="/pos/auth", tags=["Sesiones POS"])
_sessions = {}
_lock = threading.RLock()
TTL = 8 * 3600


class LoginRequest(BaseModel):
    usuario: str = Field(min_length=1, max_length=100)
    clave: str = Field(min_length=1)


@router.post("/login")
def login(body: LoginRequest, x_terminal_id: str = Header(default="")):
    usuario = DatabaseManager().autenticar_usuario(body.usuario, body.clave)
    if not usuario or not usuario.get("activo", True):
        raise HTTPException(401, "Credenciales incorrectas")
    token = secrets.token_urlsafe(36)
    with _lock:
        _sessions[token] = (usuario["usuario"], time.time() + TTL, bool(usuario.get("es_admin")), x_terminal_id[:100])
        if len(_sessions) > 5000:
            now = time.time()
            for key, session in list(_sessions.items()):
                if session[1] < now:
                    _sessions.pop(key, None)
    return {"access_token": token, "token_type": "bearer", "expires_in": TTL,
            "usuario": usuario["usuario"], "permisos": usuario.get("permisos", {}),
            "es_admin": bool(usuario.get("es_admin")), "rol": usuario.get("rol", "OPERADOR")}


def require_delivery(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Iniciá sesión como operador POS")
    token = authorization[7:]
    with _lock:
        session = _sessions.get(token)
        if not session or session[1] <= time.time():
            _sessions.pop(token, None)
            raise HTTPException(401, "Sesión vencida")
    # Revalidar rol en cada operación: revocar permisos surte efecto inmediato.
    with DatabaseManager()._connect() as conn:
        row = conn.execute("""
            SELECT u.activo, r.es_admin, r.permisos FROM usuarios u
            LEFT JOIN roles r ON r.id=u.rol_id WHERE u.usuario=? COLLATE NOCASE
        """, (session[0],)).fetchone()
    if not row:
        # Instalaciones antiguas usan LOGIN_USUARIO/LOGIN_CLAVE sin fila
        # en usuarios. La sesión se autenticó previamente con esas credenciales.
        legacy_user = (DatabaseManager().get_config_value("LOGIN_USUARIO") or "admin").strip()
        if session[2] and session[0] == legacy_user:
            return session[0]
        raise HTTPException(403, "Usuario inexistente")
    if not row["activo"]:
        raise HTTPException(403, "Usuario inactivo o eliminado")
    if session[2] and session[0] == (DatabaseManager().get_config_value("LOGIN_USUARIO") or "admin").strip():
        return session[0]
    if not tiene(normalizar(row["permisos"]), "ENTREGAS_INTRASHOP", bool(row["es_admin"])):
        raise HTTPException(403, "El rol no permite gestionar entregas")
    return session[0]


def require_config(authorization: str | None = Header(default=None)):
    operador = require_delivery(authorization)
    with DatabaseManager()._connect() as conn:
        row = conn.execute("""SELECT r.es_admin, r.permisos FROM usuarios u
            LEFT JOIN roles r ON r.id=u.rol_id WHERE u.usuario=? COLLATE NOCASE""",
            (operador,)).fetchone()
    if not row:
        legacy_user = (DatabaseManager().get_config_value("LOGIN_USUARIO") or "admin").strip()
        if operador == legacy_user:
            with _lock:
                session = _sessions.get(authorization[7:]) if authorization else None
            if session and session[2]:
                return operador
    if row and operador == (DatabaseManager().get_config_value("LOGIN_USUARIO") or "admin").strip():
        with _lock:
            session = _sessions.get(authorization[7:]) if authorization else None
        if session and session[2]:
            return operador
    if not row or not tiene(normalizar(row["permisos"]), "CONFIGURACION", bool(row["es_admin"])):
        raise HTTPException(403, "Solo administración puede asignar terminales")
    return operador


@router.post("/logout")
def logout(authorization: str | None = Header(default=None)):
    if authorization and authorization.startswith("Bearer "):
        with _lock:
            _sessions.pop(authorization[7:], None)
    return {"ok": True}

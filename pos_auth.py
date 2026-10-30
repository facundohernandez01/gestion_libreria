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
def login(body: LoginRequest):
    usuario = DatabaseManager().autenticar_usuario(body.usuario, body.clave)
    if not usuario or not usuario.get("activo", True):
        raise HTTPException(401, "Credenciales incorrectas")
    token = secrets.token_urlsafe(36)
    with _lock:
        _sessions[token] = (usuario["usuario"], time.time() + TTL)
        if len(_sessions) > 5000:
            now = time.time()
            for key, (_, expiry) in list(_sessions.items()):
                if expiry < now:
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
    if not row or not row["activo"]:
        raise HTTPException(403, "Usuario inactivo o eliminado")
    if not tiene(normalizar(row["permisos"]), "ENTREGAS_INTRASHOP", bool(row["es_admin"])):
        raise HTTPException(403, "El rol no permite gestionar entregas")
    return session[0]


@router.post("/logout")
def logout(authorization: str | None = Header(default=None)):
    if authorization and authorization.startswith("Bearer "):
        with _lock:
            _sessions.pop(authorization[7:], None)
    return {"ok": True}

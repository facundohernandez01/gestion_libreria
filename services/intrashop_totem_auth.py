"""Autenticación de dispositivo para checkout IntraShop.

Una IP sirve para descubrir el tótem, pero no para autorizar pagos. El operador
en POS Server genera un código de un solo uso, válido 10 minutos. El navegador
lo canjea por una cookie aleatoria HttpOnly (no localStorage). Su hash y la IP
asignada quedan en POS Server. Borrar cookies exige volver a emparejar SIN
cambiar el ID del tótem ni su vínculo QR.

Las cookies sobre HTTP no resisten un MITM; para una LAN hostil usar HTTPS con
certificados confiables y el modo INTRASHOP_ENFORCE_HTTPS=1.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import time

COOKIE = "intrashop_terminal"
SESSION_TTL = 30 * 24 * 3600
CODE_TTL = 10 * 60
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS intrashop_totem_pair_codes (
        totem_id TEXT PRIMARY KEY,
        code_hash TEXT NOT NULL,
        expires_at INTEGER NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS intrashop_totem_sessions (
        token_hash TEXT PRIMARY KEY,
        totem_id TEXT NOT NULL,
        ip TEXT NOT NULL,
        expires_at INTEGER NOT NULL
    )""")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_totem_sessions_totem "
        "ON intrashop_totem_sessions(totem_id)"
    )


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def generar_codigo(conn: sqlite3.Connection, totem_id: str) -> str:
    ensure_schema(conn)
    row = conn.execute(
        "SELECT id,ip_vinculada FROM intrashop_totems "
        "WHERE id=? AND retirado=0", (totem_id,),
    ).fetchone()
    if not row or not row["ip_vinculada"]:
        raise ValueError("Primero vinculá una IP al tótem activo.")
    code = "".join(secrets.choice(ALPHABET) for _ in range(10))
    conn.execute(
        """INSERT INTO intrashop_totem_pair_codes(totem_id,code_hash,expires_at)
           VALUES(?,?,?)
           ON CONFLICT(totem_id) DO UPDATE SET
           code_hash=excluded.code_hash,expires_at=excluded.expires_at""",
        (totem_id, _digest(code), int(time.time()) + CODE_TTL),
    )
    return code[:5] + "-" + code[5:]


def canjear_codigo(conn: sqlite3.Connection, ip: str, codigo: str) -> tuple[str, str]:
    """Llamar con BEGIN IMMEDIATE. No emitir cookie para otra IP."""
    from services.intrashop_totem_registry import resolve_ip

    ensure_schema(conn)
    totem = resolve_ip(conn, ip)
    if not totem:
        raise ValueError("La IP de este equipo no está vinculada a ningún tótem.")
    clean = (codigo or "").upper().replace("-", "").replace(" ", "")
    row = conn.execute(
        "SELECT code_hash,expires_at FROM intrashop_totem_pair_codes WHERE totem_id=?",
        (totem["id"],),
    ).fetchone()
    if not row or row["expires_at"] < int(time.time()) or len(clean) != 10:
        raise ValueError("Código incorrecto o vencido.")
    if not hmac.compare_digest(_digest(clean), row["code_hash"]):
        raise ValueError("Código incorrecto o vencido.")
    session = secrets.token_urlsafe(36)
    conn.execute(
        "DELETE FROM intrashop_totem_pair_codes WHERE totem_id=?", (totem["id"],),
    )
    # Emparejar de nuevo revoca sesiones anteriores de este puesto.
    conn.execute("DELETE FROM intrashop_totem_sessions WHERE totem_id=?", (totem["id"],))
    conn.execute(
        """INSERT INTO intrashop_totem_sessions(token_hash,totem_id,ip,expires_at)
           VALUES(?,?,?,?)""",
        (_digest(session), totem["id"], ip, int(time.time()) + SESSION_TTL),
    )
    return totem["id"], session


def autorizado(conn: sqlite3.Connection, ip: str, totem_id: str, cookie: str | None) -> bool:
    if not cookie or len(cookie) > 200:
        return False
    ensure_schema(conn)
    row = conn.execute(
        """SELECT s.totem_id,s.ip,s.expires_at FROM intrashop_totem_sessions s
           JOIN intrashop_totems t ON t.id=s.totem_id
           WHERE s.token_hash=? AND t.retirado=0 AND t.ip_vinculada=s.ip""", (_digest(cookie),),
    ).fetchone()
    return bool(
        row and hmac.compare_digest(row["totem_id"], totem_id)
        and hmac.compare_digest(row["ip"], ip)
        and row["expires_at"] > int(time.time())
    )


def revocar_totem(conn: sqlite3.Connection, totem_id: str) -> None:
    ensure_schema(conn)
    conn.execute("DELETE FROM intrashop_totem_sessions WHERE totem_id=?", (totem_id,))
    conn.execute("DELETE FROM intrashop_totem_pair_codes WHERE totem_id=?", (totem_id,))


def exigir_https(request) -> None:
    if os.getenv("INTRASHOP_ENFORCE_HTTPS", "0").strip() not in ("1", "true", "yes"):
        return
    from fastapi import HTTPException

    # Si hay proxy TLS, montar el backend detrás de proxy y configurar
    # sus forwarded headers con lista explícita de IPs confiables.
    if request.url.scheme != "https":
        raise HTTPException(403, "La tienda requiere HTTPS para autorizar cobros.")

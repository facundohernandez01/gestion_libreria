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
    if not row:
        raise ValueError("Seleccioná un tótem activo.")
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
    """Llamar con BEGIN IMMEDIATE. Vincular por código, sin desplazar puestos."""
    from services.intrashop_totem_registry import resolve_ip, vincular_ip

    ensure_schema(conn)
    clean = (codigo or "").upper().replace("-", "").replace(" ", "")
    if len(clean) != 10:
        raise ValueError("Código incorrecto o vencido.")
    # El código identifica un puesto preexistente, no crea dispositivos.
    # Una dirección ya asignada jamás desplaza a otro puesto.
    rows = conn.execute(
        """SELECT p.totem_id,p.code_hash,t.ip_vinculada
           FROM intrashop_totem_pair_codes p
           JOIN intrashop_totems t ON t.id=p.totem_id
           WHERE p.expires_at>? AND t.retirado=0""", (int(time.time()),),
    ).fetchall()
    matches = [r for r in rows if hmac.compare_digest(_digest(clean), r["code_hash"])]
    if len(matches) != 1:
        raise ValueError("Código incorrecto o vencido.")
    row = matches[0]
    totem = {"id": row["totem_id"]}
    existing = resolve_ip(conn, ip)
    if existing and existing["id"] != totem["id"]:
        raise ValueError("Este equipo ya está vinculado a otro tótem.")
    if row["ip_vinculada"] and row["ip_vinculada"] != ip:
        raise ValueError("El tótem ya tiene otro equipo vinculado. Solicitá al administrador que lo desvincule.")
    if not row["ip_vinculada"]:
        vincular_ip(conn, totem["id"], ip)
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


def recuperar_direccion(conn: sqlite3.Connection, ip: str, cookie: str | None) -> str | None:
    """Reconectar con una sesión vigente, exclusivamente sobre TLS verificado.

    El llamador debe exigir HTTPS y BEGIN IMMEDIATE. No desplaza otro tótem,
    no resucita sesiones revocadas ni modifica la asociación QR.
    """
    from services.intrashop_totem_registry import normalizar_ip, resolve_ip

    if not cookie or len(cookie) > 200:
        return None
    ip = normalizar_ip(ip)
    ensure_schema(conn)
    row = conn.execute(
        """SELECT s.totem_id,s.ip FROM intrashop_totem_sessions s
           JOIN intrashop_totems t ON t.id=s.totem_id
           WHERE s.token_hash=? AND s.expires_at>? AND t.retirado=0
             AND t.ip_vinculada=s.ip""",
        (_digest(cookie), int(time.time())),
    ).fetchone()
    if not row:
        return None
    existing = resolve_ip(conn, ip)
    if existing and existing["id"] != row["totem_id"]:
        return None
    if row["ip"] != ip:
        conn.execute(
            "UPDATE intrashop_totems SET ip_vinculada=?,ip_address=? WHERE id=?",
            (ip, ip, row["totem_id"]),
        )
        conn.execute(
            "UPDATE intrashop_totem_sessions SET ip=? WHERE token_hash=?",
            (ip, _digest(cookie)),
        )
        conn.execute(
            "DELETE FROM intrashop_totem_pair_codes WHERE totem_id=?",
            (row["totem_id"],),
        )
    return row["totem_id"]


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

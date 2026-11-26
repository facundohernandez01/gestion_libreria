"""Credenciales POS individuales. Las funciones de escritura requieren BEGIN IMMEDIATE."""
from __future__ import annotations

import hashlib
import re
import secrets
import sqlite3
import time

CODE_TTL = 600
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def ensure_schema(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS pos_device_codes (
        code_hash TEXT PRIMARY KEY, name TEXT NOT NULL, expires_at INTEGER NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS pos_device_credentials (
        terminal_id TEXT PRIMARY KEY, name TEXT NOT NULL,
        token_hash TEXT NOT NULL UNIQUE, issued_at INTEGER NOT NULL,
        revoked INTEGER NOT NULL DEFAULT 0
    )""")


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def emitir_codigo(conn, nombre):
    nombre = str(nombre).strip()
    if not nombre or len(nombre) > 100:
        raise ValueError("Ingresá un nombre de caja de hasta 100 caracteres.")
    ensure_schema(conn)
    now = int(time.time())
    conn.execute("DELETE FROM pos_device_codes WHERE expires_at<=?", (now,))
    code = "".join(secrets.choice(ALPHABET) for _ in range(16))
    conn.execute("INSERT INTO pos_device_codes VALUES(?,?,?)",
                 (digest(code), nombre, now + CODE_TTL))
    return "-".join(code[i:i+4] for i in range(0, 16, 4))


def canjear(conn, codigo, terminal_id):
    if not re.fullmatch(r"caja-[a-f0-9]{32}", terminal_id or ""):
        raise ValueError("Identidad de terminal inválida.")
    clean = (codigo or "").replace("-", "").replace(" ", "").upper()
    if len(clean) != 16 or any(c not in ALPHABET for c in clean):
        raise ValueError("Código inválido o vencido.")
    ensure_schema(conn)
    now = int(time.time())
    row = conn.execute("SELECT name FROM pos_device_codes WHERE code_hash=? AND expires_at>?",
                       (digest(clean), now)).fetchone()
    if row is None:
        raise ValueError("Código inválido o vencido.")
    token = "posd_" + secrets.token_urlsafe(36)
    conn.execute("DELETE FROM pos_device_codes WHERE code_hash=?", (digest(clean),))
    conn.execute("""INSERT INTO pos_device_credentials(terminal_id,name,token_hash,issued_at,revoked)
        VALUES(?,?,?,?,0) ON CONFLICT(terminal_id) DO UPDATE SET
        name=excluded.name,token_hash=excluded.token_hash,issued_at=excluded.issued_at,revoked=0""",
        (terminal_id, row[0], digest(token), now))
    return token


def autorizado(conn, token):
    if not isinstance(token, str) or not token.startswith("posd_") or len(token) != 53:
        return False
    ensure_schema(conn)
    return conn.execute("SELECT 1 FROM pos_device_credentials WHERE token_hash=? AND revoked=0",
                        (digest(token),)).fetchone() is not None


def revocar(conn, terminal_id):
    ensure_schema(conn)
    return bool(conn.execute("UPDATE pos_device_credentials SET revoked=1 WHERE terminal_id=? AND revoked=0",
                             (terminal_id,)).rowcount)


def listar(conn):
    ensure_schema(conn)
    return conn.execute("SELECT terminal_id,name,issued_at,revoked FROM pos_device_credentials ORDER BY name").fetchall()


def modo_estricto(conn):
    """Política local, fuera de la tabla config expuesta por la API LAN."""
    conn.execute("""CREATE TABLE IF NOT EXISTS pos_device_policy (
        id INTEGER PRIMARY KEY CHECK(id=1), strict INTEGER NOT NULL DEFAULT 0
    )""")
    row = conn.execute("SELECT strict FROM pos_device_policy WHERE id=1").fetchone()
    return bool(row and row[0])


def configurar_modo_estricto(conn, enabled):
    """Activación local explícita; nunca desde una solicitud de la API LAN."""
    from services.lan_https import habilitado
    modo_estricto(conn)
    ensure_schema(conn)
    if enabled:
        if not habilitado():
            raise ValueError("Prepará HTTPS antes de activar seguridad estricta.")
        if not conn.execute("SELECT 1 FROM pos_device_credentials WHERE revoked=0 LIMIT 1").fetchone():
            raise ValueError("Vinculá al menos una caja antes de activar seguridad estricta.")
    conn.execute("INSERT INTO pos_device_policy(id,strict) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET strict=excluded.strict",
                 (int(bool(enabled)),))

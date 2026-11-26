"""Contraseñas POS: PBKDF2-HMAC-SHA256 con sal aleatoria, formato versionado.

La verificación de registros antiguos en texto plano permite migración sin
conocer la contraseña de cada usuario, tras autenticación correcta.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

ITERATIONS = 260_000
PREFIX = "pbkdf2_sha256"


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("La contraseña no puede estar vacía.")
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), ITERATIONS
    ).hex()
    return "{}{}{}{}{}{}{}".format(PREFIX, "$", ITERATIONS, "$", salt, "$", digest)


def check_password(stored: str, candidate: str) -> tuple[bool, bool]:
    """Retorna (válida, necesita_migración) sin exponer la contraseña."""
    if not stored or not candidate:
        return False, False
    if stored.startswith(PREFIX + "$"):
        try:
            _, rounds, salt, digest = stored.split("$")
            rounds = int(rounds)
            if not 200_000 <= rounds <= 1_000_000:
                return False, False
            actual = hashlib.pbkdf2_hmac(
                "sha256", candidate.encode("utf-8"), bytes.fromhex(salt), rounds,
            ).hex()
            return hmac.compare_digest(actual, digest), False
        except (ValueError, TypeError):
            return False, False
    return hmac.compare_digest(stored, candidate), True


def validar_nueva_clave(clave: str) -> None:
    if len(clave or "") < 12:
        raise ValueError("La nueva contraseña debe tener al menos 12 caracteres.")
    if clave.lower() in ("adminadmin123", "administrador", "contraseña123"):
        raise ValueError("Elegí una contraseña distinta de las claves conocidas.")

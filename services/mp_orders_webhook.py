"""Verificación HMAC de notificaciones Mercado Pago Orders API.

El webhook NO acredita ventas: solo dispara un GET autenticado /v1/orders/{id}.
"""
from __future__ import annotations

import hashlib
import hmac
import re


def verify_orders_signature(
    secret: str, data_id: str, request_id: str, signature: str,
) -> bool:
    """Verifica el manifest oficial id;request-id;ts con comparación constante."""
    if not all((secret, data_id, request_id, signature)):
        return False
    fields = {}
    for part in signature.split(","):
        key, sep, value = part.strip().partition("=")
        if sep and key not in fields:
            fields[key.strip()] = value.strip()
    ts, given = fields.get("ts", ""), fields.get("v1", "")
    if not re.fullmatch(r"\d{10,16}", ts) or not re.fullmatch(r"[a-fA-F0-9]{64}", given):
        return False
    manifest = f"id:{data_id};request-id:{request_id};ts:{ts};"
    expected = hmac.new(
        secret.encode("utf-8"), manifest.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, given.lower())

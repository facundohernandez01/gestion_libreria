"""Identidad de tótems administrada por POS Server, nunca por localStorage.

La IP de vinculación es una asignación explícita del administrador. No se
confía en X-Forwarded-For: sin proxy confiable, esos headers son falsificables.
Para DHCP usar reserva de IP; NAT/proxy con clientes tras una misma IP no
distingue tótems y requiere otra identidad de equipo.
"""
from __future__ import annotations

import ipaddress
import re
import sqlite3
from typing import Any


def normalizar_ip(value: str) -> str:
    try:
        ip = ipaddress.ip_address(str(value).strip())
    except ValueError as exc:
        raise ValueError("IP inválida. Ingresá la IP del tótem, no la del servidor.") from exc
    if ip.is_unspecified or ip.is_multicast:
        raise ValueError("La IP no identifica un equipo de la red.")
    return str(ip)


def ip_cliente(request) -> str:
    """Origen TCP real; jamás X-Forwarded-For del navegador."""
    if request is None or request.client is None:
        raise ValueError("No se conoce la IP de origen.")
    return normalizar_ip(request.client.host)


def resolve_ip(conn: sqlite3.Connection, ip: str) -> dict | None:
    ip = normalizar_ip(ip)
    result = conn.execute(
        "SELECT id,nombre,ip_vinculada FROM intrashop_totems "
        "WHERE ip_vinculada=? LIMIT 2",
        (ip,),
    ).fetchall()
    if len(result) > 1:
        raise ValueError("La IP está asociada a múltiples tótems; corregí la configuración.")
    return dict(result[0]) if result else None


def vincular_ip(conn: sqlite3.Connection, totem_id: str, ip: str) -> dict:
    """Llamar con BEGIN IMMEDIATE desde panel autorizado (GUI o API admin)."""
    ip = normalizar_ip(ip)
    row = conn.execute(
        "SELECT id,nombre FROM intrashop_totems WHERE id=?", (totem_id,),
    ).fetchone()
    if not row:
        raise ValueError("Tótem inexistente")
    in_use = resolve_ip(conn, ip)
    if in_use and in_use["id"] != totem_id:
        raise ValueError(f"IP {ip} ya vinculada a {in_use['nombre']} ({in_use['id']})")
    # No toca la relación QR ni el nombre.
    conn.execute(
        "UPDATE intrashop_totems SET ip_vinculada=? WHERE id=?",
        (ip, totem_id),
    )
    return {"id": row["id"], "nombre": row["nombre"], "ip_vinculada": ip}


def desvincular_ip(conn: sqlite3.Connection, totem_id: str) -> bool:
    """Desasociar IP sin destruir tótem, QR, historial ni caja."""
    return bool(conn.execute(
        "UPDATE intrashop_totems SET ip_vinculada=NULL WHERE id=?",
        (totem_id,),
    ).rowcount)


def provisionar(conn: sqlite3.Connection, cantidad: int = 1) -> list[dict]:
    """Alta administrada, consecutiva, sin reutilizar relaciones antiguas."""
    if not 1 <= cantidad <= 20:
        raise ValueError("Se pueden crear entre 1 y 20 tótems por operación.")
    rows = conn.execute("SELECT id FROM intrashop_totems").fetchall()
    numeros = [
        int(x["id"].split("-")[1]) for x in rows
        if re.fullmatch(r"totem-\d{3,}", str(x["id"]))
    ]
    actual = max(numeros, default=0)
    result = []
    for n in range(actual + 1, actual + 1 + cantidad):
        if n > 9999:
            raise ValueError("Se alcanzó el máximo de numeración de tótems")
        tid = f"totem-{n:03d}"
        nombre = f"Tótem {n:03d}"
        conn.execute(
            "INSERT INTO intrashop_totems(id,nombre) VALUES (?,?)",
            (tid, nombre),
        )
        result.append({"id": tid, "nombre": nombre})
    return result

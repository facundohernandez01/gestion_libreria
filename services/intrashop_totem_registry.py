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
        "WHERE ip_vinculada=? AND retirado=0 LIMIT 2",
        (ip,),
    ).fetchall()
    if len(result) > 1:
        raise ValueError("La IP está asociada a múltiples tótems; corregí la configuración.")
    return dict(result[0]) if result else None


def vincular_ip(conn: sqlite3.Connection, totem_id: str, ip: str) -> dict:
    """Llamar con BEGIN IMMEDIATE desde panel autorizado (GUI o API admin)."""
    ip = normalizar_ip(ip)
    row = conn.execute(
        "SELECT id,nombre,retirado,ip_vinculada FROM intrashop_totems WHERE id=?", (totem_id,),
    ).fetchone()
    if not row:
        raise ValueError("Tótem inexistente")
    if row["retirado"]:
        raise ValueError("El tótem fue eliminado; restauralo antes de vincularlo.")
    in_use = resolve_ip(conn, ip)
    if in_use and in_use["id"] != totem_id:
        raise ValueError(f"IP {ip} ya vinculada a {in_use['nombre']} ({in_use['id']})")
    # No toca la relación QR ni el nombre.
    if row["ip_vinculada"] != ip:
        from services.intrashop_totem_auth import revocar_totem
        revocar_totem(conn, totem_id)
    conn.execute(
        "UPDATE intrashop_totems SET ip_vinculada=? WHERE id=?",
        (ip, totem_id),
    )
    return {"id": row["id"], "nombre": row["nombre"], "ip_vinculada": ip}


def desvincular_ip(conn: sqlite3.Connection, totem_id: str) -> bool:
    """Quitar equipo asociado, sin borrar tótem, QR, caja ni pedidos."""
    row = conn.execute(
        "SELECT id,retirado FROM intrashop_totems WHERE id=?", (totem_id,)
    ).fetchone()
    if not row or row["retirado"]:
        return False
    from services.intrashop_totem_auth import revocar_totem
    revocar_totem(conn, totem_id)
    conn.execute(
        "UPDATE intrashop_totems SET ip_vinculada=NULL,ip_address=NULL WHERE id=?",
        (totem_id,),
    )
    return True


def resumen_retiro(conn: sqlite3.Connection, totem_id: str) -> dict:
    """Vista previa sin mutaciones. Mostrar antes de confirmar el retiro."""
    row = conn.execute(
        "SELECT id,nombre,retirado,ip_vinculada FROM intrashop_totems WHERE id=?",
        (totem_id,),
    ).fetchone()
    if not row:
        raise ValueError("El tótem no existe.")
    binding = conn.execute(
        "SELECT pos_external_id FROM intrashop_mp_bindings "
        "WHERE terminal_id=? AND terminal_type='totem'",
        (totem_id,),
    ).fetchone()
    pos_id = binding["pos_external_id"] if binding else None
    historical = conn.execute(
        "SELECT COUNT(*) FROM intrashop_checkouts WHERE totem_id=?",
        (totem_id,),
    ).fetchone()[0]
    entregas = conn.execute(
        "SELECT COUNT(*) FROM intrashop_entregas WHERE totem_id=?",
        (totem_id,),
    ).fetchone()[0]
    pendientes_entrega = conn.execute(
        "SELECT COUNT(*) FROM intrashop_entregas "
        "WHERE totem_id=? AND estado<>'entregado'",
        (totem_id,),
    ).fetchone()[0]
    # Un cobro en curso o ambiguo nunca se borra ni se libera a la fuerza.
    # Revisar también por POS externo, aunque no tenga totem_id.
    sin_resolver = conn.execute(
        """SELECT COUNT(*) FROM intrashop_checkouts
           WHERE (totem_id=? OR (? IS NOT NULL AND pos_external_id=?))
           AND estado NOT IN ('completed','cancelled','failed','expired')""",
        (totem_id, pos_id, pos_id),
    ).fetchone()[0]
    return {
        "id": row["id"], "nombre": row["nombre"],
        "retirado": bool(row["retirado"]),
        "ip_vinculada": row["ip_vinculada"],
        "pos_external_id": pos_id, "checkouts_historicos": historical,
        "entregas_historicas": entregas, "entregas_pendientes": pendientes_entrega,
        "cobros_pendientes": sin_resolver,
    }


def retirar_totem(conn: sqlite3.Connection, totem_id: str) -> dict:
    """Ocultar de la operación y desvincular QR/IP locales, preservando auditoría.

    Invocar bajo BEGIN IMMEDIATE. Los registros de venta, checkout, entrega,
    ticket e histórico permanecen sin alterar. No elimina QR remoto en MP.
    """
    estado = resumen_retiro(conn, totem_id)
    if estado["retirado"]:
        raise ValueError("Este tótem ya está eliminado de la lista activa.")
    if estado["cobros_pendientes"]:
        raise ValueError(
            f"El tótem tiene {estado['cobros_pendientes']} cobro(s) "
            "sin resolver. Regularizalos desde Conciliación antes de eliminarlo."
        )
    if estado["entregas_pendientes"]:
        raise ValueError(
            f"El tótem tiene {estado['entregas_pendientes']} comanda(s) "
            "pendiente(s). Finalizá las entregas antes de eliminarlo."
        )
    from services.intrashop_totem_auth import revocar_totem
    revocar_totem(conn, totem_id)
    conn.execute(
        "DELETE FROM intrashop_mp_bindings "
        "WHERE terminal_id=? AND terminal_type='totem'",
        (totem_id,),
    )
    conn.execute(
        "UPDATE intrashop_totems SET retirado=1,ip_vinculada=NULL,ip_address=NULL "
        "WHERE id=? AND retirado=0",
        (totem_id,),
    )
    return {**estado, "retirado": True}


def restaurar_totem(conn: sqlite3.Connection, totem_id: str) -> dict:
    """Recuperar un ID retirado: la IP y QR deben reconfirmarse."""
    row = conn.execute(
        "SELECT id,nombre,retirado FROM intrashop_totems WHERE id=?", (totem_id,)
    ).fetchone()
    if not row or not row["retirado"]:
        raise ValueError("No hay un tótem eliminado con ese identificador.")
    conn.execute(
        "UPDATE intrashop_totems SET retirado=0 WHERE id=?", (totem_id,),
    )
    return {"id": row["id"], "nombre": row["nombre"], "retirado": False}


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

"""Lectura de dispositivos del POS Server, aislada de Tkinter.

La consola puede arrancar sobre una SQLite existente que nunca recibió un
checkout ni un registro de tótem. Esas tablas son opcionales y se inicializan
sin borrar datos antes de consultar el panel.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from intrashop_checkout_store import ensure_schema as ensure_checkout_schema
from intrashop_entregas import ensure_schema as ensure_delivery_schema


def snapshot(db_path: str) -> tuple[list[dict], list[dict], list[dict]]:
    """Retorna tótems, vínculos de QR y cobros pendientes.

    La inicialización es aditiva e idempotente: no altera las ventas, cajas
    o el stock. Un error SQLite se propaga para mostrarlo en el panel y
    permitir reintentar; nunca se informa éxito con datos incompletos.
    """
    if not Path(db_path).is_file():
        raise FileNotFoundError(
            f"No existe la base de datos de POS Server: {db_path}. "
            "Verificá DB_PATH y la inicialización del servidor."
        )

    with sqlite3.connect(db_path, timeout=5) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=5000")

        # Las tablas de tienda no forman parte del SCHEMA del POS clásico.
        # En un clon/base nueva no existen hasta el primer registro o cobro.
        # Usar las migraciones oficiales y no replicar definiciones parciales.
        ensure_delivery_schema(conn)
        ensure_checkout_schema(conn)
        conn.commit()

        columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(intrashop_totems)")
        }
        ip_col = "ip" if "ip" in columns else (
            "ip_address" if "ip_address" in columns else None
        )
        fields = "id,nombre,ultimo_contacto" + ("," + ip_col if ip_col else "")
        totems = [
            dict(row) for row in conn.execute(
                f"SELECT {fields} FROM intrashop_totems ORDER BY nombre COLLATE NOCASE"
            )
        ]
        bindings = [
            dict(row) for row in conn.execute(
                "SELECT terminal_id,terminal_type,nombre,pos_external_id "
                "FROM intrashop_mp_bindings ORDER BY terminal_type,nombre"
            )
        ]
        pending = [
            dict(row) for row in conn.execute(
                "SELECT id,estado,pos_external_id,total FROM intrashop_checkouts "
                "WHERE estado IN ('reserved','creating','waiting','verifying',"
                "'uncertain','paid') ORDER BY created_at DESC LIMIT 100"
            )
        ]
    return totems, bindings, pending

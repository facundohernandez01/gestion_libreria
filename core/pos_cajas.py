"""Contrato de cajas por terminal para POS Server LAN.

No altera el modelo de caja única de Kiosmico local. La migración es aditiva:
las cajas históricas conservan terminal_id=NULL; no se adjudican a un equipo
sin confirmación administrativa.
"""
from __future__ import annotations

from fastapi import HTTPException


def ensure_schema(conn) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(cajas)")}
    if "terminal_id" not in columns:
        conn.execute("ALTER TABLE cajas ADD COLUMN terminal_id TEXT")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_cajas_terminal_abierta "
        "ON cajas(terminal_id) "
        "WHERE estado='abierta' AND terminal_id IS NOT NULL"
    )


def validate_owner(conn, caja_id: int, terminal_id: str | None,
                   *, require_open: bool = False) -> dict:
    """Impide usar otra caja aunque alguien conozca su ID y la API key LAN."""
    row = conn.execute(
        "SELECT id,terminal_id,estado FROM cajas WHERE id=?", (int(caja_id),)
    ).fetchone()
    if row is None:
        raise HTTPException(404, "Caja inexistente")
    owner = row["terminal_id"]
    if owner != (terminal_id or None):
        raise HTTPException(403, "La caja pertenece a otra terminal POS")
    if require_open and row["estado"] != "abierta":
        raise HTTPException(409, "La caja no está abierta")
    return dict(row)


def unassigned_open(conn) -> bool:
    return conn.execute(
        "SELECT 1 FROM cajas WHERE estado='abierta' AND terminal_id IS NULL LIMIT 1"
    ).fetchone() is not None

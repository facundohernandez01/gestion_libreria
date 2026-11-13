#!/usr/bin/env python3
"""Restauración OFFLINE de la base del POS Server.

Ejecutar en el equipo servidor con POS Server detenido. Por defecto solo
valida y muestra conteos; --aplicar requiere confirmación explícita.
Nunca se ejecuta sobre la SQLite local del POS cliente.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.backup_service import validar_backup, restaurar_backup


def _conteos(path: Path) -> dict:
    with sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True) as db:
        tablas = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        return {
            tabla: db.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]
            for tabla in ("productos", "proveedores", "ordenes_compra", "ventas", "cajas")
            if tabla in tablas
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backup", type=Path)
    parser.add_argument("--db", type=Path, required=True, help="Ruta absoluta de la base REAL del POS Server")
    parser.add_argument("--modo", choices=("fusionar", "reemplazar"), default="fusionar")
    parser.add_argument("--aplicar", action="store_true", help="Habilita restauración después de confirmación")
    args = parser.parse_args()
    backup_original = args.backup.expanduser()
    destino_original = args.db.expanduser()
    if backup_original.is_symlink() or destino_original.is_symlink():
        parser.error("No se admiten enlaces simbólicos como origen o destino")
    if not destino_original.is_absolute():
        parser.error("--db debe ser una ruta absoluta para evitar restaurar otra SQLite")
    backup = backup_original.resolve(strict=True)
    destino = destino_original.resolve(strict=True)
    if backup == destino:
        parser.error("Origen y destino son el mismo archivo")
    if not destino.is_file():
        parser.error("La base del servidor no existe")
    print("BACKUP:", backup)
    print("DESTINO:", destino)
    print("MODO:", args.modo)
    print("VALIDACIÓN:", validar_backup(backup)["conteos"])
    print("ACTUAL:", _conteos(destino))
    if args.modo == "fusionar":
        print("ADVERTENCIA: fusionar omite productos con el mismo código; NO actualiza su stock, precio ni descripción.")
        print("Para recuperar exactamente el estado del backup, usá reemplazar con el servidor detenido.")
    if not args.aplicar:
        print("SIMULACIÓN: no se modificó ninguna base. Para aplicar, agregá --aplicar.")
        return 0
    # Un proceso servidor abierto puede escribir fuera del lock de restauración.
    # No ofrecer una restauración online que prometa atomicidad falsa.
    try:
        import psutil
    except ImportError:
        parser.error("Para aplicar se requiere psutil: pip install psutil")
    objetivo = {str(destino), str(destino) + "-wal", str(destino) + "-shm"}
    abiertos = []
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            for item in proc.open_files() or []:
                if item.path in objetivo:
                    abiertos.append((proc.pid, proc.info.get("name")))
                    break
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
    if abiertos:
        parser.error(f"La base está abierta por procesos {abiertos}. Detené POS Server primero.")
    # psutil puede no tener permisos para enumerar todos los procesos.
    # En Linux, comprobar además los puertos del servidor antes de aplicar.
    if sys.platform.startswith("linux") and os.geteuid() != 0:
        print("ATENCIÓN: ejecutando sin privilegios; no se garantiza detectar conexiones SQLite de otros usuarios.")
        if input("Confirmá que detuviste TODOS los POS Server escribiendo DETENIDO: ").strip() != "DETENIDO":
            return 1
    if input("Escribí RESTAURAR para continuar: ").strip() != "RESTAURAR":
        print("Cancelado; no se modificó la base.")
        return 1
    # restaurar_backup crea primero una copia consistente de la base actual.
    resultado = restaurar_backup(destino, backup, args.modo)
    print("RESTAURACIÓN FINALIZADA:", resultado)
    print("CONTEOS POSTERIORES:", _conteos(destino))
    print("Antes de iniciar POS Server, verificá que estos conteos sean correctos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

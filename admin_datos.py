#!/usr/bin/env python3
"""Administración de datos de prueba y del asistente de primer uso.

Ejemplos:
    python admin_datos.py --estado
    python admin_datos.py --primer-uso si
    python admin_datos.py --limpiar-ventas --si
    python admin_datos.py --limpiar-productos --si
    python admin_datos.py --limpiar-todo --si
    python admin_datos.py --db /ruta/libreria.db --estado
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
os.chdir(BASE)
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))


def _resolver_db(valor: str | None) -> Path:
    if valor:
        return Path(valor).expanduser().resolve()
    from core.settings import settings

    return Path(settings.db_path).resolve()


def _mostrar_estado(db, ruta: Path) -> None:
    print(f"Base de datos: {ruta}")
    marca = db.get_config_value("PRIMER_USO")
    print(f"PRIMER_USO:    {marca if marca not in (None, '') else '(sin definir)'}")
    print("Datos:")
    for tabla, n in db.contar_datos().items():
        print(f"  {tabla:22} {n:>8}")


def _confirmar(accion: str, asumir_si: bool) -> bool:
    if asumir_si:
        return True
    print(f"\nATENCIÓN: {accion}.")
    print("Esta acción no se puede deshacer. Se recomienda exportar un backup antes.")
    try:
        return input("Escribí SI para confirmar: ").strip().upper() == "SI"
    except (EOFError, KeyboardInterrupt):
        return False


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Herramientas de administración de datos de la librería")
    parser.add_argument("--db", help="Ruta alternativa a la base SQLite")
    parser.add_argument("--estado", action="store_true",
                        help="Muestra conteos y estado del primer uso")
    parser.add_argument("--primer-uso", choices=["si", "no"],
                        help="Marca/desmarca el asistente de primer uso")
    parser.add_argument("--limpiar-ventas", action="store_true",
                        help="Borra ventas, cajas, gastos y movimientos de venta")
    parser.add_argument("--limpiar-productos", action="store_true",
                        help="Borra productos y órdenes (también ventas)")
    parser.add_argument("--limpiar-todo", action="store_true",
                        help="Borra ventas, cajas, productos y órdenes")
    parser.add_argument("--si", action="store_true",
                        help="No pedir confirmación interactiva")
    args = parser.parse_args(argv)

    if not any([args.estado, args.primer_uso, args.limpiar_ventas,
                args.limpiar_productos, args.limpiar_todo]):
        parser.print_help()
        return 1

    ruta = _resolver_db(args.db)
    if not ruta.exists():
        print(f"ERROR: no existe la base {ruta}", file=sys.stderr)
        return 2

    from database_manager import DatabaseManager

    db = DatabaseManager(str(ruta))
    db.init_database()

    if args.estado:
        _mostrar_estado(db, ruta)

    if args.primer_uso:
        activo = args.primer_uso == "si"
        db.marcar_primer_uso(activo)
        print(f"PRIMER_USO = {'SI' if activo else 'NO'}")

    acciones = []
    if args.limpiar_todo:
        acciones.append(("borrar TODOS los datos de prueba", True, True))
    else:
        if args.limpiar_ventas:
            acciones.append(("borrar ventas/cajas/gastos", True, False))
        if args.limpiar_productos:
            acciones.append(("borrar productos/órdenes (y ventas)", True, True))

    for descripcion, borrar_ventas, borrar_productos in acciones:
        if not _confirmar(descripcion, args.si):
            print("Cancelado.")
            return 1
        antes = db.contar_datos()
        db.limpiar_datos_prueba(borrar_ventas=borrar_ventas,
                                borrar_productos=borrar_productos)
        despues = db.contar_datos()
        print(f"OK: {descripcion}")
        for tabla in ("productos", "ventas", "venta_items", "cajas",
                      "movimientos_stock", "ordenes_compra"):
            print(f"  {tabla:18} {antes.get(tabla, 0):>6} -> {despues.get(tabla, 0):>6}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

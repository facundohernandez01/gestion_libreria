"""Copias de seguridad de la base SQLite (exportar / validar / restaurar).

- Exporta con la API de backup de SQLite (consistente aunque haya WAL).
- Valida integridad y tablas mínimas antes de restaurar.
- Restaura en modo `reemplazar` (equipo nuevo) o `fusionar` (sin duplicar
  productos ni ventas; usa huellas de venta calculadas con items + fecha).
"""
from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

TABLAS_MINIMAS = {
    "productos",
    "ventas",
    "venta_items",
    "cajas",
    "movimientos_stock",
    "config",
}


def _connect(path: str | Path, readonly: bool = False) -> sqlite3.Connection:
    p = Path(path)
    if readonly:
        conn = sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True, timeout=15)
    else:
        conn = sqlite3.connect(str(p), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def _tabla_existe(conn: sqlite3.Connection, tabla: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tabla,)
    ).fetchone()
    return row is not None


def _rows(conn: sqlite3.Connection, tabla: str) -> list[dict]:
    if not _tabla_existe(conn, tabla):
        return []
    return [dict(r) for r in conn.execute(f"SELECT * FROM {tabla}").fetchall()]


def _insertar_dict(conn: sqlite3.Connection, tabla: str, data: dict) -> Optional[int]:
    """INSERT filtrando columnas inexistentes en destino y sin id."""
    columnas = {r[1] for r in conn.execute(f"PRAGMA table_info({tabla})").fetchall()}
    cols = [c for c in data.keys() if c in columnas and c != "id"]
    if not cols:
        return None
    sql = f"INSERT INTO {tabla} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})"
    cur = conn.execute(sql, [data[c] for c in cols])
    return int(cur.lastrowid)


def _huella_venta(venta: dict, items: Iterable[dict]) -> str:
    base = "|".join(
        [
            str(venta.get("fecha") or ""),
            f"{float(venta.get('total') or 0):.2f}",
            str(venta.get("metodo_pago") or ""),
            str(venta.get("comprobante") or ""),
            str(venta.get("numero_factura") or ""),
        ]
    )
    partes = sorted(
        f"{it.get('producto_codigo') or it.get('codigo') or ''}:"
        f"{int(it.get('cantidad') or 0)}:"
        f"{float(it.get('precio_unitario') or 0):.2f}:"
        f"{float(it.get('subtotal') or 0):.2f}"
        for it in items
    )
    return hashlib.sha256((base + "||" + "|".join(partes)).encode("utf-8")).hexdigest()


def _huella_orden(orden: dict, items: Iterable[dict]) -> str:
    base = "|".join(
        [
            str(orden.get("fecha_creacion") or ""),
            str(orden.get("estado") or ""),
            str(orden.get("fecha_confirmacion") or ""),
            str(orden.get("observaciones") or ""),
        ]
    )
    partes = sorted(
        f"{it.get('producto_codigo') or it.get('codigo') or ''}:"
        f"{int(it.get('cantidad') or 0)}:"
        f"{float(it.get('precio_costo') or 0):.2f}"
        for it in items
    )
    return hashlib.sha256((base + "||" + "|".join(partes)).encode("utf-8")).hexdigest()


def _ventas_con_items(conn: sqlite3.Connection) -> tuple[dict[int, dict], dict[int, list[dict]]]:
    ventas = {int(v["id"]): v for v in _rows(conn, "ventas")}
    items: dict[int, list[dict]] = {}
    if _tabla_existe(conn, "venta_items"):
        cur = conn.execute(
            """SELECT vi.*, p.codigo AS producto_codigo
               FROM venta_items vi
               LEFT JOIN productos p ON p.id = vi.producto_id
               ORDER BY vi.venta_id, vi.id"""
        )
        for r in cur.fetchall():
            d = dict(r)
            items.setdefault(int(d["venta_id"]), []).append(d)
    return ventas, items


def _ordenes_con_items(conn: sqlite3.Connection) -> tuple[dict[int, dict], dict[int, list[dict]]]:
    ordenes = {int(o["id"]): o for o in _rows(conn, "ordenes_compra")}
    items: dict[int, list[dict]] = {}
    if _tabla_existe(conn, "orden_compra_items"):
        cur = conn.execute(
            """SELECT oi.*, p.codigo AS producto_codigo
               FROM orden_compra_items oi
               LEFT JOIN productos p ON p.id = oi.producto_id
               ORDER BY oi.orden_id, oi.id"""
        )
        for r in cur.fetchall():
            d = dict(r)
            items.setdefault(int(d["orden_id"]), []).append(d)
    return ordenes, items


def validar_backup(ruta: str | Path) -> dict:
    """Valida que el archivo sea una base SQLite usable. Lanza ValueError."""
    p = Path(ruta)
    if not p.exists() or not p.is_file():
        raise ValueError("El archivo de backup no existe")
    if p.stat().st_size == 0:
        raise ValueError("El archivo de backup está vacío")
    try:
        conn = _connect(p, readonly=True)
    except sqlite3.DatabaseError as e:
        raise ValueError(f"No es una base SQLite válida: {e}") from e
    try:
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("La base del backup está dañada (integrity_check)")
        tablas = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        faltan = sorted(TABLAS_MINIMAS - tablas)
        if faltan:
            raise ValueError(f"Backup inválido: faltan tablas {', '.join(faltan)}")
        conteos = {}
        for t in sorted(TABLAS_MINIMAS):
            conteos[t] = int(conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
        return {
            "ruta": str(p),
            "bytes": p.stat().st_size,
            "conteos": conteos,
        }
    finally:
        conn.close()


def exportar_backup(db_path: str | Path, destino: str | Path) -> dict:
    origen = Path(db_path).resolve()
    destino = Path(destino).resolve()
    if origen == destino:
        raise ValueError("El destino no puede ser la misma base en uso")
    destino.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(str(origen), timeout=30)
    try:
        src.execute("PRAGMA busy_timeout=10000")
        dst = sqlite3.connect(str(destino), timeout=30)
        try:
            src.backup(dst)
            dst.commit()
            dst.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            dst.close()
    finally:
        src.close()
    info = validar_backup(destino)
    info["destino"] = str(destino)
    return info


def crear_backup_seguridad(db_path: str | Path) -> str:
    origen = Path(db_path)
    carpeta = origen.parent / "backups"
    carpeta.mkdir(parents=True, exist_ok=True)
    sello = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    destino = carpeta / f"seguridad_antes_de_restaurar_{sello}.db"
    exportar_backup(origen, destino)
    return str(destino)


def _restaurar_reemplazar(db_path: str, backup_path: str) -> dict:
    src = sqlite3.connect(backup_path, timeout=30)
    try:
        dst = sqlite3.connect(db_path, timeout=30)
        try:
            dst.execute("PRAGMA busy_timeout=10000")
            src.backup(dst)
            dst.commit()
            dst.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            dst.close()
    finally:
        src.close()
    # Asegura tablas/columnas nuevas si el backup es de una versión anterior.
    from database_manager import DatabaseManager

    db = DatabaseManager(db_path)
    db.init_database()
    return db.contar_datos()


def _fusionar(db_path: str, backup_path: str) -> dict:
    from database_manager import DatabaseManager

    # Garantiza esquema actual en destino antes de comparar/insertar.
    DatabaseManager(db_path).init_database()
    src = _connect(backup_path, readonly=True)
    dst = sqlite3.connect(db_path, timeout=30)
    dst.row_factory = sqlite3.Row
    dst.execute("PRAGMA busy_timeout=10000")
    dst.execute("PRAGMA foreign_keys=ON")
    resumen = {
        "proveedores_importados": 0,
        "proveedores_omitidos": 0,
        "productos_importados": 0,
        "productos_omitidos": 0,
        "cajas_importadas": 0,
        "cajas_omitidas": 0,
        "ventas_importadas": 0,
        "ventas_omitidas": 0,
        "ordenes_importadas": 0,
        "ordenes_omitidas": 0,
        "movimientos_importados": 0,
    }
    try:
        # ---------- proveedores ----------
        prov_map: dict[int, int] = {}
        dst_prov = {
            str(p["nombre"]).strip().lower(): int(p["id"])
            for p in _rows(dst, "proveedores")
        }
        for p in _rows(src, "proveedores"):
            clave = str(p["nombre"]).strip().lower()
            if clave in dst_prov:
                prov_map[int(p["id"])] = dst_prov[clave]
                resumen["proveedores_omitidos"] += 1
                continue
            nuevo = _insertar_dict(
                dst,
                "proveedores",
                {k: p.get(k) for k in ("nombre", "cuit", "telefono", "email",
                                       "direccion", "notas", "fecha_creacion",
                                       "fecha_modificacion")},
            )
            if not nuevo:
                resumen["proveedores_omitidos"] += 1
                continue
            prov_map[int(p["id"])] = nuevo
            dst_prov[clave] = nuevo
            resumen["proveedores_importados"] += 1
            if _tabla_existe(src, "proveedor_contactos"):
                for c in src.execute(
                    "SELECT * FROM proveedor_contactos WHERE proveedor_id=?", (p["id"],)
                ).fetchall():
                    _insertar_dict(
                        dst,
                        "proveedor_contactos",
                        {"proveedor_id": nuevo, "nombre": c["nombre"],
                         "telefono": c["telefono"], "email": c["email"]},
                    )

        # ---------- productos ----------
        prod_map: dict[int, int] = {}
        dst_prod = {
            str(p["codigo"]).strip(): int(p["id"])
            for p in _rows(dst, "productos")
        }
        for p in _rows(src, "productos"):
            codigo = str(p["codigo"]).strip()
            if codigo in dst_prod:
                prod_map[int(p["id"])] = dst_prod[codigo]
                resumen["productos_omitidos"] += 1
                continue
            data = dict(p)
            data.pop("id", None)
            src_prov = data.get("proveedor_id")
            data["proveedor_id"] = prov_map.get(int(src_prov)) if src_prov else None
            nuevo = _insertar_dict(dst, "productos", data)
            if not nuevo:
                resumen["productos_omitidos"] += 1
                continue
            prod_map[int(p["id"])] = nuevo
            dst_prod[codigo] = nuevo
            resumen["productos_importados"] += 1

        # ---------- cajas (en fusión se importan cerradas) ----------
        caja_map: dict[int, int] = {}
        dst_cajas = {
            (str(c["fecha_apertura"]), round(float(c["importe_apertura"] or 0), 2)): int(c["id"])
            for c in _rows(dst, "cajas")
        }
        for c in _rows(src, "cajas"):
            clave = (str(c["fecha_apertura"]), round(float(c["importe_apertura"] or 0), 2))
            if clave in dst_cajas:
                caja_map[int(c["id"])] = dst_cajas[clave]
                resumen["cajas_omitidas"] += 1
                continue
            data = dict(c)
            data.pop("id", None)
            if str(data.get("estado") or "abierta") == "abierta":
                data["estado"] = "cerrada"
                data["fecha_cierre"] = data.get("fecha_cierre") or datetime.now().isoformat(" ")
                obs = str(data.get("observaciones_cierre") or "").strip()
                data["observaciones_cierre"] = (
                    (obs + " | ") if obs else ""
                ) + "Importada desde backup (cierre automático)"
            nuevo = _insertar_dict(dst, "cajas", data)
            if not nuevo:
                continue
            caja_map[int(c["id"])] = nuevo
            dst_cajas[clave] = nuevo
            resumen["cajas_importadas"] += 1

        # ---------- ventas ----------
        src_ventas, src_items = _ventas_con_items(src)
        dst_ventas, dst_items = _ventas_con_items(dst)
        huellas = {
            _huella_venta(v, dst_items.get(vid, []))
            for vid, v in dst_ventas.items()
        }
        venta_map: dict[int, int] = {}
        for vid, v in src_ventas.items():
            items = src_items.get(vid, [])
            huella = _huella_venta(v, items)
            if huella in huellas:
                resumen["ventas_omitidas"] += 1
                continue
            caja_dst = caja_map.get(int(v["caja_id"]))
            if not caja_dst:
                resumen["ventas_omitidas"] += 1
                continue
            items_dst = []
            ok = True
            for it in items:
                prod_dst = prod_map.get(int(it["producto_id"]))
                if not prod_dst:
                    ok = False
                    break
                items_dst.append((prod_dst, it))
            if not ok:
                resumen["ventas_omitidas"] += 1
                continue
            data = dict(v)
            data.pop("id", None)
            data["caja_id"] = caja_dst
            nueva_venta = _insertar_dict(dst, "ventas", data)
            if not nueva_venta:
                resumen["ventas_omitidas"] += 1
                continue
            for prod_dst, it in items_dst:
                _insertar_dict(
                    dst,
                    "venta_items",
                    {
                        "venta_id": nueva_venta,
                        "producto_id": prod_dst,
                        "cantidad": it["cantidad"],
                        "precio_unitario": it["precio_unitario"],
                        "subtotal": it["subtotal"],
                    },
                )
            huellas.add(huella)
            venta_map[int(vid)] = nueva_venta
            resumen["ventas_importadas"] += 1

        # ---------- movimientos de ventas importadas ----------
        if _tabla_existe(src, "movimientos_stock"):
            for m in _rows(src, "movimientos_stock"):
                if m.get("tipo") not in ("venta", "devolucion"):
                    continue
                ref = m.get("referencia_id")
                if ref is None or int(ref) not in venta_map:
                    continue
                prod_dst = prod_map.get(int(m["producto_id"]))
                if not prod_dst:
                    continue
                _insertar_dict(
                    dst,
                    "movimientos_stock",
                    {
                        "producto_id": prod_dst,
                        "tipo": m["tipo"],
                        "cantidad": m["cantidad"],
                        "stock_anterior": m["stock_anterior"],
                        "stock_nuevo": m["stock_nuevo"],
                        "fecha": m["fecha"],
                        "referencia_id": venta_map[int(ref)],
                        "observaciones": m.get("observaciones") or "",
                    },
                )
                resumen["movimientos_importados"] += 1

        # ---------- órdenes de compra ----------
        src_ordenes, src_orden_items = _ordenes_con_items(src)
        dst_ordenes, dst_orden_items = _ordenes_con_items(dst)
        huellas_orden = {
            _huella_orden(o, dst_orden_items.get(oid, []))
            for oid, o in dst_ordenes.items()
        }
        orden_map: dict[int, int] = {}
        for oid, o in src_ordenes.items():
            items = src_orden_items.get(oid, [])
            huella = _huella_orden(o, items)
            if huella in huellas_orden:
                resumen["ordenes_omitidas"] += 1
                continue
            items_dst = []
            ok = True
            for it in items:
                prod_dst = prod_map.get(int(it["producto_id"]))
                if not prod_dst:
                    ok = False
                    break
                prov = it.get("proveedor_id")
                items_dst.append((prod_dst, prov_map.get(int(prov)) if prov else None, it))
            if not ok:
                resumen["ordenes_omitidas"] += 1
                continue
            data = dict(o)
            data.pop("id", None)
            nueva_orden = _insertar_dict(dst, "ordenes_compra", data)
            if not nueva_orden:
                resumen["ordenes_omitidas"] += 1
                continue
            for prod_dst, prov_dst, it in items_dst:
                _insertar_dict(
                    dst,
                    "orden_compra_items",
                    {
                        "orden_id": nueva_orden,
                        "producto_id": prod_dst,
                        "proveedor_id": prov_dst,
                        "cantidad": it["cantidad"],
                        "precio_costo": it["precio_costo"],
                        "subtotal": it["subtotal"],
                    },
                )
            huellas_orden.add(huella)
            orden_map[int(oid)] = nueva_orden
            resumen["ordenes_importadas"] += 1

        # Movimientos de ingresos de las órdenes importadas (sin tocar stock).
        if _tabla_existe(src, "movimientos_stock"):
            for m in _rows(src, "movimientos_stock"):
                if m.get("tipo") != "ingreso":
                    continue
                ref = m.get("referencia_id")
                if ref is None or int(ref) not in orden_map:
                    continue
                prod_dst = prod_map.get(int(m["producto_id"]))
                if not prod_dst:
                    continue
                _insertar_dict(
                    dst,
                    "movimientos_stock",
                    {
                        "producto_id": prod_dst,
                        "tipo": "ingreso",
                        "cantidad": m["cantidad"],
                        "stock_anterior": m["stock_anterior"],
                        "stock_nuevo": m["stock_nuevo"],
                        "fecha": m["fecha"],
                        "referencia_id": orden_map[int(ref)],
                        "observaciones": m.get("observaciones") or "",
                    },
                )
                resumen["movimientos_importados"] += 1

        dst.commit()
    except Exception:
        dst.rollback()
        raise
    finally:
        src.close()
        dst.close()
    return resumen


def restaurar_backup(db_path: str | Path, backup_path: str | Path,
                     modo: str = "fusionar") -> dict:
    """Restaura un backup. `modo`: 'fusionar' (default) o 'reemplazar'.

    Siempre crea un backup de seguridad de la base actual antes de modificar.
    """
    validar_backup(backup_path)
    modo = (modo or "fusionar").strip().lower()
    if modo not in ("fusionar", "reemplazar"):
        raise ValueError("Modo inválido: use 'fusionar' o 'reemplazar'")
    seguridad = crear_backup_seguridad(db_path)
    if modo == "reemplazar":
        conteos = _restaurar_reemplazar(str(db_path), str(backup_path))
        return {
            "modo": modo,
            "seguridad": seguridad,
            "conteos": conteos,
        }
    resumen = _fusionar(str(db_path), str(backup_path))
    resumen["modo"] = modo
    resumen["seguridad"] = seguridad
    return resumen

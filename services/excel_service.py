"""Importación / exportación Excel — patrón Service.

Reglas:
- Columnas obligatorias: codigo, descripcion, precio_lista
- Opcionales: categoria, marca, precio_costo, stock_inicial|stock_actual, stock_minimo
- Validación fila por fila con reporte de errores (no frena todo el archivo).
- Exportación con timestamp y columnas estables.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Tuple

COLUMNAS_OBLIGATORIAS = ["codigo", "descripcion", "precio_lista"]
COLUMNAS_EXPORT = ["codigo", "descripcion", "categoria", "marca",
                   "precio_lista", "precio_costo", "stock_actual", "stock_minimo",
                   "proveedor_nombre"]


class ExcelService:
    @staticmethod
    def importar(file_path: str | Path, db) -> Tuple[int, int, list]:
        """Retorna (importados, omitidos, errores[:20])."""
        import pandas as pd

        df = pd.read_excel(str(file_path))
        df.columns = [str(c).strip().lower() for c in df.columns]
        faltan = [c for c in COLUMNAS_OBLIGATORIAS if c not in df.columns]
        if faltan:
            raise ValueError(f"Faltan columnas obligatorias: {', '.join(faltan)}")

        def texto(valor) -> str:
            if valor is None:
                return ""
            try:
                if pd.isna(valor):
                    return ""
            except (TypeError, ValueError):
                pass
            valor = str(valor).strip()
            return "" if valor.lower() in {"nan", "none", "nat"} else valor

        def numero(valor, defecto=0.0) -> float:
            try:
                if pd.isna(valor):
                    return defecto
                return float(valor)
            except (TypeError, ValueError):
                return defecto

        col_proveedor = next(
            (c for c in ("proveedor", "proveedor_nombre") if c in df.columns), None)

        importados, omitidos, errores = 0, 0, []
        for idx, row in df.iterrows():
            try:
                codigo = texto(row.get("codigo", ""))
                if not codigo:
                    omitidos += 1
                    continue
                producto = {
                    "codigo": codigo,
                    "descripcion": texto(row.get("descripcion", "")),
                    "categoria": texto(row.get("categoria", "")),
                    "marca": texto(row.get("marca", "")),
                    "precio_lista": numero(row.get("precio_lista", 0)),
                    "precio_costo": numero(row.get("precio_costo", 0)),
                    "stock_minimo": int(numero(row.get("stock_minimo", 5), 5)),
                }
                stock_val = row.get("stock_inicial", row.get("stock_actual", 0))
                producto["stock_inicial"] = int(numero(stock_val, 0))
                if col_proveedor:
                    nombre_prov = texto(row.get(col_proveedor, ""))
                    if nombre_prov:
                        pid = db.obtener_o_crear_proveedor(nombre_prov)
                        if pid:
                            producto["proveedor_id"] = pid
                if not producto["descripcion"]:
                    raise ValueError("descripcion vacía")
                if producto["precio_lista"] < 0:
                    raise ValueError("precio_lista negativo")
                rid = db.guardar_producto(producto)
                if rid:
                    importados += 1
                else:
                    omitidos += 1
            except Exception as e:  # noqa: BLE001
                omitidos += 1
                if len(errores) < 20:
                    errores.append(f"Fila {idx + 2}: {e}")
        return importados, omitidos, errores

    @staticmethod
    def exportar(destino: str | Path | None, db) -> str:
        import pandas as pd

        productos = db.buscar_productos("", "descripcion", limit=100000)
        if not productos:
            raise ValueError("No hay productos para exportar")
        df = pd.DataFrame(productos)
        for c in COLUMNAS_EXPORT:
            if c not in df.columns:
                df[c] = ""
        df = df[COLUMNAS_EXPORT]
        if destino is None:
            destino = f"productos_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
        df.to_excel(str(destino), index=False)
        return str(destino)


excel_service = ExcelService()

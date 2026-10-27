"""Aplica el icono de la app a la ventana del cliente Flet en ejecución."""
from __future__ import annotations

import os
import sys
from io import BytesIO
from pathlib import Path


def _raices_cliente() -> list[Path]:
    raices: list[Path] = []
    env = os.environ.get("FLET_VIEW_PATH", "").strip()
    if env:
        raices.append(Path(env))
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        raices.append(Path(meipass))
    try:
        from flet_desktop import ensure_client_cached

        raices.append(ensure_client_cached())
    except Exception:
        pass
    if not raices:
        raices.append(Path.home() / ".flet" / "client")
    return raices


def _destinos_icono() -> list[Path]:
    destinos: list[Path] = []
    vistos: set[Path] = set()
    for raiz in _raices_cliente():
        if raiz.is_file():
            raiz = raiz.parent
        if not raiz.exists():
            continue
        try:
            encontrados = list(raiz.rglob("app_icon.png"))
        except OSError:
            continue
        for destino in encontrados:
            if destino not in vistos:
                vistos.add(destino)
                destinos.append(destino)
    return destinos


def aplicar_icono_ventana(origen: str | Path, tamano: int = 256) -> list[Path]:
    """Copia el logo, redimensionado, sobre el icono del cliente Flet."""
    origen = Path(origen)
    if not origen.is_file():
        return []
    try:
        from PIL import Image
    except Exception:
        return []

    try:
        with Image.open(origen) as imagen:
            imagen = imagen.convert("RGBA")
            imagen.thumbnail((tamano, tamano), Image.Resampling.LANCZOS)
            lienzo = Image.new("RGBA", (tamano, tamano), (0, 0, 0, 0))
            lienzo.paste(imagen, ((tamano - imagen.width) // 2,
                                  (tamano - imagen.height) // 2), imagen)
            buffer = BytesIO()
            lienzo.save(buffer, format="PNG")
        datos = buffer.getvalue()
    except Exception:
        return []

    actualizados: list[Path] = []
    for destino in _destinos_icono():
        try:
            if destino.is_file() and destino.read_bytes() == datos:
                continue
            temporal = destino.with_name(destino.name + ".tmp")
            temporal.write_bytes(datos)
            os.replace(temporal, destino)
            actualizados.append(destino)
        except Exception:
            continue
    return actualizados

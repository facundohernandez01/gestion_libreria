"""Rutas portables: funciona igual con `python main.py` y con el .exe (frozen).

Portado del build (utils/paths.py): resuelve la DB junto al ejecutable
cuando la app corre congelada con PyInstaller.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def db_path(filename: str = "libreria.db") -> str:
    """Ruta de la DB: respeta DB_PATH del .env si está definida."""
    env = os.getenv("DB_PATH", "").strip()
    if env:
        p = Path(env)
        return str(p if p.is_absolute() else base_dir() / p)
    return str(base_dir() / filename)

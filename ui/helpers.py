"""Helpers UI reutilizables: snackbars, diálogos, validaciones, impresión multiplataforma."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import flet as ft


def snack(page: ft.Page, mensaje: str, ok: bool = True) -> None:
    """Muestra un SnackBar (Flet 1.x: vía show_dialog)."""
    bar = ft.SnackBar(
        content=ft.Text(mensaje, color=ft.Colors.WHITE),
        bgcolor=ft.Colors.GREEN_700 if ok else ft.Colors.RED_700,
    )
    try:
        page.show_dialog(bar)
    except Exception:
        # fallback legacy
        page.overlay.append(bar)
        bar.open = True
        page.update()


def abrir_dialogo(page: ft.Page, dialog) -> None:
    """Muestra un AlertDialog (compatible Flet 1.x)."""
    try:
        page.show_dialog(dialog)
    except Exception:
        page.overlay.append(dialog)
        dialog.open = True
        page.update()


def cerrar_dialogo(page: ft.Page) -> None:
    """Cierra el diálogo superior (compatible Flet 1.x)."""
    try:
        page.pop_dialog()
    except Exception:
        pass
    try:
        page.update()
    except Exception:
        pass


def parse_float(valor, default: float = 0.0) -> float:
    try:
        return float(str(valor).replace(",", "."))
    except (TypeError, ValueError, AttributeError):
        return default


def parse_int(valor, default: int = 0) -> int:
    try:
        return int(float(str(valor).replace(",", ".")))
    except (TypeError, ValueError, AttributeError):
        return default


def abrir_archivo(ruta: str | Path) -> tuple[bool, str]:
    """Abre un archivo con el visor predeterminado del sistema."""
    p = Path(ruta)
    if not p.exists():
        return False, f"No existe: {p}"
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(p))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(p)])
        else:
            subprocess.Popen(["xdg-open", str(p)])
        return True, ""
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def imprimir_archivo(ruta: str | Path) -> tuple[bool, str]:
    """Impresión multiplataforma (antes solo os.startfile -> solo Windows)."""
    p = Path(ruta)
    if not p.exists():
        return False, f"No existe: {p}"
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(p), "print")  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["lp", str(p)], check=False)
        else:
            # Linux: CUPS
            r = subprocess.run(["lp", str(p)], capture_output=True, text=True)
            if r.returncode != 0:
                return False, r.stderr.strip() or "lp falló"
        return True, "Enviado a impresora"
    except Exception as e:  # noqa: BLE001
        return False, str(e)

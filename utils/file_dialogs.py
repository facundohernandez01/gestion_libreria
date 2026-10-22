"""Diálogos de archivo/carpeta multiplataforma (Flet 1.x + fallback tkinter).

En Flet 1.x `FilePicker` es un `Service` (no va en `page.overlay`) y sus métodos
son asíncronos. Si el picker nativo falla (p. ej. Linux sin Zenity), se usa
tkinter (bloqueante) como fallback.
"""
from __future__ import annotations

from pathlib import Path

import flet as ft


def _extensiones(extensions) -> list[str]:
    return [str(e).lstrip(".").lower() for e in (extensions or []) if str(e).strip()]


def _registrar(page, picker: ft.FilePicker) -> None:
    """Registra el service si la auto-registración de Flet no lo hizo."""
    try:
        if not any(s is picker for s in page.services):
            page.services.append(picker)
            page.update()
    except Exception:
        pass


def _quitar(page, picker: ft.FilePicker) -> None:
    """Desregistra el picker de la vista y del registro interno de Flet."""
    try:
        page.services[:] = [s for s in page.services if s is not picker]
    except Exception:
        pass
    try:
        registro = getattr(page, "_services", None)
        lista = getattr(registro, "_services", None)
        if isinstance(lista, list):
            lista[:] = [s for s in lista if s is not picker]
    except Exception:
        pass
    try:
        page.update()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Fallbacks con tkinter (bloqueantes)
# ---------------------------------------------------------------------------
def _tk_pick_file(title: str, extensions: list[str], initial_directory: str | None) -> str | None:
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        tipos = [("Archivos", " ".join(f"*.{e}" for e in extensions))] if extensions else []
        tipos.append(("Todos", "*.*"))
        path = filedialog.askopenfilename(
            title=title, filetypes=tipos, initialdir=initial_directory or None
        )
        root.destroy()
        return path or None
    except Exception:
        return None


def _tk_save_file(title: str, file_name: str, extensions: list[str], initial_directory: str | None) -> str | None:
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        tipos = [("Archivos", " ".join(f"*.{e}" for e in extensions))] if extensions else []
        tipos.append(("Todos", "*.*"))
        path = filedialog.asksaveasfilename(
            title=title, initialfile=file_name, defaultextension=f".{extensions[0]}" if extensions else "",
            filetypes=tipos, initialdir=initial_directory or None,
        )
        root.destroy()
        return path or None
    except Exception:
        return None


def _tk_pick_folder(title: str, initial_directory: str | None) -> str | None:
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askdirectory(title=title, initialdir=initial_directory or None)
        root.destroy()
        return path or None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# API pública (asíncrona)
# ---------------------------------------------------------------------------
async def pick_file(page: ft.Page, title="Seleccionar archivo", extensions=None,
                    initial_directory: str | None = None) -> str | None:
    exts = _extensiones(extensions)
    picker = None
    try:
        picker = ft.FilePicker()
        _registrar(page, picker)
        files = await picker.pick_files(
            dialog_title=title,
            initial_directory=initial_directory,
            allow_multiple=False,
            file_type=ft.FilePickerFileType.CUSTOM if exts else ft.FilePickerFileType.ANY,
            allowed_extensions=exts or None,
        )
        if files:
            return files[0].path
        return None  # cancelado por el usuario
    except Exception:
        pass
    finally:
        if picker is not None:
            _quitar(page, picker)
    return _tk_pick_file(title, exts, initial_directory)


async def save_file(page: ft.Page, title="Guardar archivo", file_name="archivo.xlsx",
                    extensions=None, initial_directory: str | None = None) -> str | None:
    exts = _extensiones(extensions)
    picker = None
    try:
        picker = ft.FilePicker()
        _registrar(page, picker)
        path = await picker.save_file(
            dialog_title=title,
            file_name=file_name,
            initial_directory=initial_directory,
            file_type=ft.FilePickerFileType.CUSTOM if exts else ft.FilePickerFileType.ANY,
            allowed_extensions=exts or None,
        )
        return path or None
    except Exception:
        pass
    finally:
        if picker is not None:
            _quitar(page, picker)
    return _tk_save_file(title, file_name, exts, initial_directory)


async def pick_folder(page: ft.Page, title="Seleccionar carpeta",
                      initial_directory: str | None = None) -> str | None:
    picker = None
    try:
        picker = ft.FilePicker()
        _registrar(page, picker)
        path = await picker.get_directory_path(
            dialog_title=title, initial_directory=initial_directory
        )
        return path or None
    except Exception:
        pass
    finally:
        if picker is not None:
            _quitar(page, picker)
    return _tk_pick_folder(title, initial_directory)


def agregar_extension(ruta: str | None, extension: str) -> str | None:
    """Asegura que la ruta termine con la extensión indicada."""
    if not ruta:
        return ruta
    if Path(ruta).suffix:
        return ruta
    return f"{ruta}.{extension.lstrip('.')}"

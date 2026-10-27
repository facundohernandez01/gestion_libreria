"""Ventana de presentación (splash) independiente, sin marco ni barra de título.

Se ejecuta en un proceso aparte para poder mostrarse antes de que Flet abra la
ventana principal. La cierra el proceso principal creando el archivo indicado en
SPLASH_CLOSE_FILE (o sola al vencer SPLASH_MAX_MS).
"""
from __future__ import annotations

import os
import time
from pathlib import Path


def _segundos(nombre: str, defecto_ms: float) -> float:
    try:
        return max(0.0, float(os.getenv(nombre, str(defecto_ms))) / 1000.0)
    except ValueError:
        return defecto_ms / 1000.0


def mostrar_splash() -> None:
    ruta = Path(os.getenv("SPLASH_IMAGE", ""))
    if not ruta.is_file():
        ruta = Path(__file__).resolve().parent.parent / "img" / "kiosmico_splash.png"
    if not ruta.is_file():
        return
    try:
        import tkinter as tk
        from PIL import Image, ImageTk
    except Exception:
        return

    try:
        ancho = int(os.getenv("SPLASH_ANCHO", "640"))
        alto = int(os.getenv("SPLASH_ALTO", "360"))
    except ValueError:
        ancho, alto = 640, 360

    try:
        root = tk.Tk()
    except Exception:
        return

    try:
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        try:
            root.wm_attributes("-type", "splash")
        except Exception:
            pass
        root.configure(bg="black")

        pantalla_ancho = root.winfo_screenwidth()
        pantalla_alto = root.winfo_screenheight()
        izquierda = max(0, (pantalla_ancho - ancho) // 2)
        arriba = max(0, (pantalla_alto - alto) // 2)
        root.geometry(f"{ancho}x{alto}+{izquierda}+{arriba}")

        with Image.open(ruta) as imagen:
            imagen = imagen.convert("RGB").resize(
                (ancho, alto), getattr(Image, "Resampling", Image).LANCZOS
            )
            foto = ImageTk.PhotoImage(imagen)
        etiqueta = tk.Label(root, image=foto, bd=0, highlightthickness=0,
                            bg="black")
        etiqueta.pack(fill="both", expand=True)
        etiqueta.image = foto

        root.update_idletasks()
        root.update()
        try:
            root.lift()
        except Exception:
            pass

        cierre = os.getenv("SPLASH_CLOSE_FILE", "")
        minimo = _segundos("SPLASH_MIN_MS", 700)
        maximo = _segundos("SPLASH_MAX_MS", 30000 if cierre else 2500)
        inicio = time.monotonic()

        while True:
            root.update()
            transcurrido = time.monotonic() - inicio
            if cierre and Path(cierre).exists() and transcurrido >= minimo:
                break
            if transcurrido >= maximo:
                break
            time.sleep(0.05)
    except Exception:
        pass
    finally:
        try:
            root.destroy()
        except Exception:
            pass


if __name__ == "__main__":
    mostrar_splash()

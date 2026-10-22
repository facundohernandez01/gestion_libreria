"""Gestor de atajos de teclado — reconstruido del build (utils/shortcuts.py).

Los atajos se disparan con la tecla **Alt** presionada:
    Alt+Q -> nueva venta (teclado/descripción)
    Alt+W -> nueva venta (lector/pistola, modo código)
    Alt+C -> confirmar venta imprimiendo
    Alt+M -> cobrar con QR / Mercado Pago
    Alt+E -> confirmar sin imprimir
"""
from __future__ import annotations

import flet as ft


class ShortcutManager:
    def __init__(self, page: ft.Page):
        self.page = page
        self.shortcuts: dict = {}
        self.nav: dict = {}
        self.page.on_keyboard_event = self._handle_keypress

    @staticmethod
    def _norm_key(key: str) -> str:
        """Normaliza nombres de tecla: 'Arrow Down', 'ArrowDown' -> 'arrowdown'."""
        return (key or "").lower().replace(" ", "").replace("_", "")

    def _handle_keypress(self, e: ft.KeyboardEvent):
        key = (e.key or "").lower()
        if getattr(e, "alt", False):
            if key in self.shortcuts:
                func = self.shortcuts[key]
                try:
                    func(e)
                except TypeError:
                    func()
            return
        # Teclas de navegación (flechas) registradas por el modal activo.
        nav_key = self._norm_key(e.key)
        if nav_key in self.nav:
            func = self.nav[nav_key]
            try:
                func(e)
            except TypeError:
                func()

    def register(self, key: str, func) -> None:
        self.shortcuts[key.lower()] = func

    def register_nav(self, key: str, func) -> None:
        """Registra una tecla de navegación sin modificadores (p. ej. 'Arrow Down')."""
        self.nav[self._norm_key(key)] = func

    def unregister_nav(self, key: str) -> None:
        self.nav.pop(self._norm_key(key), None)

    def create_shortcut_button(self, text: str, key: str, on_click, icon=ft.Icons.SAVE):
        self.register(key, on_click)
        return ft.FilledButton(
            content=ft.Row([
                ft.Icon(icon, size=18),
                ft.Text(text),
                ft.Text(f"(Alt+{key.upper()})", size=10, color=ft.Colors.GREY_400),
            ], tight=True),
            on_click=lambda _: on_click(),
        )

    def unregister(self, key: str) -> None:
        """Elimina un atajo para que deje de escucharse."""
        key = key.lower()
        if key in self.shortcuts:
            del self.shortcuts[key]

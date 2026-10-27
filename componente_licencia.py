"""Pantalla de activación de licencia (bloquea el software hasta activar)."""
from __future__ import annotations

import flet as ft

from ui.paleta import N
from ui.helpers import snack
from utils.licencia import (activar_licencia, activar_demo, demo_disponible,
                            verificar_licencia, cargar_estado)


def LicenciaView(db_manager=None, page=None, on_activado=None, mensaje=None):
    license_field = ft.TextField(
        label="License key", width=360, autofocus=True,
        prefix_icon=ft.Icons.VPN_KEY)
    estado_text = ft.Text(mensaje or "", size=12, color=N.RED_400, visible=bool(mensaje))
    detalle_text = ft.Text("", size=11, color=N.GREY_400, visible=False)

    st = cargar_estado()
    if st.get("license_key"):
        license_field.value = st.get("license_key")

    def _set_estado(texto, ok=True):
        estado_text.value = texto
        estado_text.color = N.GREEN_400 if ok else N.RED_400
        estado_text.visible = True
        page.update()

    def activar(e=None):
        key = (license_field.value or "").strip()
        if not key:
            _set_estado("Ingresá la license key", ok=False)
            return
        estado_text.value = "⏳ Activando licencia..."
        estado_text.color = N.GREY_400
        estado_text.visible = True
        page.update()

        def worker():
            ok, msg, info = activar_licencia(key)
            if ok:
                _set_estado(msg or "Activación exitosa", ok=True)
                snack(page, msg or "Licencia activada", ok=True)
                if on_activado:
                    async def _finish():
                        try:
                            on_activado()
                        except Exception:
                            pass
                    try:
                        page.run_task(_finish)
                    except Exception:
                        try:
                            on_activado()
                        except Exception:
                            pass
            else:
                _set_estado(msg, ok=False)
                snack(page, msg, ok=False)

        import threading
        threading.Thread(target=worker, daemon=True).start()

    def verificar(e=None):
        key = (license_field.value or "").strip() or None
        estado_text.value = "⏳ Verificando licencia..."
        estado_text.color = N.GREY_400
        estado_text.visible = True
        page.update()

        def worker():
            valid, msg, info = verificar_licencia(key)
            if valid is None:
                _set_estado(msg, ok=False)
                return
            if valid:
                _set_estado(msg, ok=True)
                snack(page, msg, ok=True)
                if on_activado:
                    async def _finish():
                        try:
                            on_activado()
                        except Exception:
                            pass
                    try:
                        page.run_task(_finish)
                    except Exception:
                        try:
                            on_activado()
                        except Exception:
                            pass
            else:
                _set_estado(msg, ok=False)

        import threading
        threading.Thread(target=worker, daemon=True).start()

    def activar_demo_click(e=None):
        if not demo_disponible():
            _set_estado("El demo ya fue utilizado en este equipo", ok=False)
            snack(page, "El demo ya fue utilizado en este equipo", ok=False)
            return
        estado_text.value = "⏳ Activando demo..."
        estado_text.color = N.GREY_400
        estado_text.visible = True
        page.update()

        def worker():
            ok, msg = activar_demo()
            if ok:
                _set_estado(msg, ok=True)
                snack(page, msg, ok=True)
                if on_activado:
                    async def _finish():
                        try:
                            on_activado()
                        except Exception:
                            pass
                    try:
                        page.run_task(_finish)
                    except Exception:
                        try:
                            on_activado()
                        except Exception:
                            pass
            else:
                _set_estado(msg, ok=False)
                snack(page, msg, ok=False)

        import threading as _t
        _t.Thread(target=worker, daemon=True).start()

    tarjeta = ft.Container(
        content=ft.Column([
            ft.Icon(ft.Icons.LOCK, size=56, color=N.BLUE_300),
            ft.Text("ACTIVACIÓN DE LICENCIA", size=20, weight=ft.FontWeight.BOLD),
            ft.Text("Ingresá la license key para desbloquear el software.",
                    size=12, color=N.GREY_400, text_align=ft.TextAlign.CENTER),
            ft.Container(height=8),
            license_field,
            ft.Row([
                ft.FilledButton("ACTIVAR", icon=ft.Icons.CHECK, on_click=activar,
                                style=ft.ButtonStyle(bgcolor=N.GREEN_700,
                                                     color=ft.Colors.WHITE)),
                ft.OutlinedButton("VERIFICAR", icon=ft.Icons.REFRESH, on_click=verificar),
            ], spacing=10),
            ft.FilledButton("Probar demo (30 días)", icon=ft.Icons.HOURGLASS_TOP,
                            on_click=activar_demo_click,
                            disabled=not demo_disponible(),
                            style=ft.ButtonStyle(bgcolor=N.BLUE_700,
                                                color=ft.Colors.WHITE)),
            estado_text,
            detalle_text,
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
        padding=32, border_radius=14, width=420,
        bgcolor=ft.Colors.with_opacity(0.55, N.DEEP),
        border=ft.Border.all(1.5, ft.Colors.with_opacity(0.7, N.CYAN)),
    )

    return ft.Container(
        content=ft.Column([tarjeta], horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                          alignment=ft.MainAxisAlignment.CENTER, expand=True),
        padding=20, expand=True, alignment=ft.Alignment.CENTER,
    )
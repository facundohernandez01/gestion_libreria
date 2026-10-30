"""Muestra el QR estático + impresión multiplataforma."""
from pathlib import Path

import flet as ft
from ui.paleta import N

from ui.helpers import imprimir_archivo, snack


def mostrar_qr(page: ft.Page):
    qr_local = Path(__file__).parent / "img" / "qr.png"

    def imprimir_qr(e):
        ok, msg = imprimir_archivo(qr_local)
        snack(page, f"QR: {msg}", ok=ok)

    existe = qr_local.exists()
    qr_asignado = ""
    try:
        from adapters.mp_bindings import listar
        from core.terminal_identity import terminal_id
        qr_asignado = next((x["qr_url"] for x in listar()
                            if x["terminal_type"]=="caja" and x["terminal_id"]==terminal_id()), "")
    except Exception:
        pass
    return ft.Container(
        content=ft.Column(
            [
                ft.Image(src=qr_asignado or (str(qr_local) if existe else "img/qr.png"),
                         width=220, height=220, fit=ft.BoxFit.CONTAIN,
                         error_content=ft.Text("QR no descargado aún.\nVaya a Ajustes → Mercado Pago.",
                                               text_align=ft.TextAlign.CENTER)),
                ft.Text("Muestre este QR al cliente.\nEl monto se fija por venta (fixed_amount).",
                        size=12, color=N.GREY_400, text_align=ft.TextAlign.CENTER),
                ft.Text("QR exclusivo asignado a esta caja" if qr_asignado else "QR predeterminado",
                        size=11, color=N.GREEN_400 if qr_asignado else N.AMBER_400),
                ft.FilledButton("Imprimir QR", icon=ft.Icons.PRINT, on_click=imprimir_qr,
                                disabled=bool(qr_asignado)),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=16,
        ),
        padding=20, width=320, border_radius=10,
        bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.WHITE),
    )

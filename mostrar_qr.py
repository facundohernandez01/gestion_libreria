"""Muestra el QR estático + impresión multiplataforma."""
from pathlib import Path

import flet as ft

from ui.helpers import imprimir_archivo, snack


def mostrar_qr(page: ft.Page):
    qr_local = Path(__file__).parent / "img" / "qr.png"

    def imprimir_qr(e):
        ok, msg = imprimir_archivo(qr_local)
        snack(page, f"QR: {msg}", ok=ok)

    existe = qr_local.exists()
    return ft.Container(
        content=ft.Column(
            [
                ft.Image(src=str(qr_local) if existe else "img/qr.png",
                         width=220, height=220, fit=ft.BoxFit.CONTAIN,
                         error_content=ft.Text("QR no descargado aún.\nVaya a Ajustes → Mercado Pago.",
                                               text_align=ft.TextAlign.CENTER)),
                ft.Text("Muestre este QR al cliente.\nEl monto se fija por venta (fixed_amount).",
                        size=12, color=ft.Colors.GREY_400, text_align=ft.TextAlign.CENTER),
                ft.FilledButton("Imprimir QR", icon=ft.Icons.PRINT, on_click=imprimir_qr),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=16,
        ),
        padding=20, width=320, border_radius=10,
        bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.WHITE),
    )

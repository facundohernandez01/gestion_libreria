import os
import flet as ft

def mostrar_qr(page: ft.Page):
    def imprimir_qr(e):
        # Construye ruta absoluta al archivo
        base_dir = os.path.dirname(os.path.abspath(__file__))
        ruta_imagen = os.path.join(base_dir, "img", "qr.png")

        if not os.path.exists(ruta_imagen):
            print(f"⚠️ No se encontró la imagen: {ruta_imagen}")
            return

        try:
            os.startfile(ruta_imagen, "print")  # 🔹 imprime con impresora predeterminada
        except Exception as err:
            print(f"Error al imprimir: {err}")

    return ft.Container(
        content=ft.Column(
            [
                ft.Image(
                    src="img/qr.png",
                    width=200,
                    height=200,
                    fit=ft.ImageFit.CONTAIN,
                ),
                ft.ElevatedButton(
                    "Imprimir QR",
                    icon=ft.Icons.PRINT,
                    on_click=imprimir_qr,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=20,
        ),
        padding=20,
        width=300,
        height=320,
        bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.WHITE),
        border_radius=10,
    )

import flet as ft
from flet import Icons
from datetime import datetime

class AbrirCajaView(ft.Column):
    def __init__(self, db_manager, on_caja_abierta):
        super().__init__()
        self.db = db_manager
        self.on_caja_abierta = on_caja_abierta
        
    def build(self):
        self.fecha = ft.TextField(value=datetime.now().strftime("%Y-%m-%d %H:%M"), disabled=True)
        self.importe = ft.TextField(label="Importe inicial $", keyboard_type="number")
        self.obs = ft.TextField(label="Observaciones", multiline=True, height=80)

        def aceptar(e):
            # Aquí debería guardarse la caja en la DB; usamos stub
            caja_id = self.db.abrir_caja(float(self.importe.value or 0), self.obs.value or "")
            self.on_caja_abierta(caja_id)

        return ft.Container(
            ft.Column([
                ft.Text("Apertura de caja", size=20),
                self.fecha,
                self.importe,
                self.obs,
                ft.Row([
                    ft.ElevatedButton("Aceptar", on_click=aceptar, bgcolor=ft.Colors.GREEN),
                    ft.ElevatedButton("Salir", on_click=lambda e: self.page.window_destroy())
                ], alignment=ft.MainAxisAlignment.CENTER)
            ], tight=True),
            padding=20, alignment=ft.alignment.center, width=540, height=400
        )
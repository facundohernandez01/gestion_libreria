import flet as ft
from datetime import datetime

class CerrarCajaModal(ft.Container):
	def __init__(self, db_manager, caja_id, on_caja_cerrada):
		super().__init__()
		self.db = db_manager
		self.caja_id = caja_id
		self.on_caja_cerrada = on_caja_cerrada
		self.open = False

	def build(self):
		self.fecha = ft.Text(datetime.now().strftime("%Y-%m-%d %H:%M"))
		self.gastos = ft.TextField(label="Gastos $", keyboard_type="number")
		self.total = ft.TextField(label="Total caja $", keyboard_type="number")
		self.coment = ft.TextField(label="Comentarios", multiline=True, height=80)

		btn_confirm = ft.ElevatedButton("Confirmar cierre", bgcolor=ft.Colors.GREEN, on_click=self._confirm)
		btn_cancel = ft.ElevatedButton("Deshacer", bgcolor=ft.Colors.RED, on_click=self._cancel)

		return ft.Container(ft.Column([
			ft.Text("Cierre de caja"),
			self.fecha, self.gastos, self.total, self.coment,
			ft.Row([btn_cancel, btn_confirm], alignment=ft.MainAxisAlignment.END)
		], spacing=10), padding=20, width=520)

	def _confirm(self, e):
		# Guardar cierre en DB (stub)
		self.db.cerrar_caja(self.caja_id, float(self.total.value or 0), float(self.gastos.value or 0), self.coment.value or "")
		if self.on_caja_cerrada:
			self.on_caja_cerrada()
		self.open = False
		self.page.update()

	def _cancel(self, e):
		self.open = False
		self.page.update()

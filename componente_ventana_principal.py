# componente_ventana_principal.py
import flet as ft
from database_manager import DatabaseManager
from datetime import datetime

class VentanaPrincipal(ft.Column):
	def __init__(self, page, caja_actual, on_nueva_venta_teclado, on_nueva_venta_lector, on_gestion_articulos, on_cerrar_caja):
		self.page = page
		self.caja = caja_actual
		self.on_nueva_venta_teclado = on_nueva_venta_teclado
		self.on_nueva_venta_lector = on_nueva_venta_lector
		self.on_gestion_articulos = on_gestion_articulos
		self.on_cerrar_caja = on_cerrar_caja

		# Listado de ventas del día (ejemplo)
		ventas = [
			{"id": 1, "hora": "09:12", "total": 120.0, "items": [("Libro A", 1, 120.0)]},
			{"id": 2, "hora": "10:35", "total": 45.5, "items": [("Goma", 2, 10.0), ("Lápiz", 1, 25.5)]},
		]

		ventas_controls = []
		for v in ventas:
			# detalles ocultos inicialmente
			detalles = ft.Column([ft.Text(f"{it[0]} x{it[1]} ${it[2]}") for it in v["items"]], visible=False)

			# botón que alterna visibilidad de detalles y cambia icono
			def make_toggle(det_ctrl):
				def toggle(e):
					det_ctrl.visible = not det_ctrl.visible
					# cambiar icono del botón que disparó el evento
					e.control.icon = ft.Icons.EXPAND_LESS if det_ctrl.visible else ft.Icons.EXPAND_MORE
					# actualizar este control Column (heredado)
					self.update()
				return toggle

			toggle_btn = ft.IconButton(icon=ft.Icons.EXPAND_MORE, on_click=make_toggle(detalles))
			header = ft.Row([
				ft.Text(f"ID {v['id']} - {v['hora']} - ${v['total']}", expand=True),
				toggle_btn
			], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

			# Container envuelve la Column para permitir padding
			ventas_controls.append(
				ft.Container(
					ft.Column([header, detalles], spacing=4),
					padding=ft.padding.symmetric(vertical=6)
				)
			)

		total_hoy = sum(v["total"] for v in ventas)

		# Botones nueva venta: teclado y lector
		btn_teclado = ft.ElevatedButton("Nueva venta (teclado)", icon=ft.Icons.KEYBOARD, on_click=self.on_nueva_venta_teclado)
		btn_lector = ft.ElevatedButton("Nueva venta (lector)", icon=ft.Icons.QR_CODE, on_click=self.on_nueva_venta_lector)

		left_panel = ft.Container(
			ft.Column([
				ft.Text("Ventas de hoy", size=16),
				ft.Column(ventas_controls, spacing=6),
				ft.Container(ft.Text(f"Total vendido hoy: ${total_hoy:.2f}"), alignment=ft.alignment.center_right, padding=ft.padding.only(top=10))
			]),
			width=420, height=600, padding=10, border=ft.border.all(1, ft.Colors.GREY)
		)

		right_panel = ft.Container(
			ft.Column([
				ft.Text("Acciones", size=16),
				ft.Row([btn_teclado, btn_lector], alignment=ft.MainAxisAlignment.START),
				ft.ElevatedButton("Gestión Artículos", on_click=self.on_gestion_articulos),
				ft.ElevatedButton("Cerrar caja", on_click=self.on_cerrar_caja),
			], spacing=12),
			padding=10, expand=True
		)

		layout = ft.Row([left_panel, ft.VerticalDivider(), right_panel], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

		# responsive: si ancho < 800 usar columna
		if self.page.width and self.page.width < 800:
			controls = [ft.Column([layout], scroll=True)]
		else:
			controls = [layout]

		# Inicializar la Column padre con los controles construidos
		super().__init__(controls=controls)

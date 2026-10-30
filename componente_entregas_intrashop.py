"""Vista compacta de comandas para el POS Flet.

Los permisos se validan en la navegación principal; la base SQLite es
la fuente de verdad de los estados y del operador que entrega.
"""
import flet as ft
from adapters.entregas import EntregasAdapter
from ui.paleta import N


def panel_entregas(page, operador):
    adapter = EntregasAdapter()
    lista = ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO, expand=True)
    contador = ft.Text("Pedidos pendientes", size=17, weight=ft.FontWeight.BOLD)
    filtro = ft.Dropdown(label="Estado", value="activos", width=180, options=[
        ft.dropdown.Option("activos", "Activos"),
        ft.dropdown.Option("entregado", "Entregados"),
    ])

    def refresh(_=None):
        try:
            rows = adapter.listar()
            rows = [o for o in rows if (o["estado"] == "entregado") == (filtro.value == "entregado")]
            lista.controls.clear()
            for order in rows:
                state = order["estado"]
                label = {"pendiente": "Pendiente", "preparando": "Preparando",
                         "listo": "Listo para entregar", "entregado": "Entregado"}[state]
                next_state = {"pendiente": "preparando", "preparando": "listo",
                              "listo": "entregado"}.get(state)
                controls = [
                    ft.Row([
                        ft.Text(f"Pedido #{order['venta_id']}", weight=ft.FontWeight.BOLD, size=16),
                        ft.Text(label, color=N.GREEN_400 if state == "entregado" else N.AMBER_400),
                        ft.Text(f"$ {order['total']:,.2f}", weight=ft.FontWeight.BOLD),
                    ], spacing=16),
                    ft.Text(" · ".join(f"{i['cantidad']} × {i['descripcion']}" for i in order["items"]), size=12),
                ]
                if next_state:
                    controls.append(ft.FilledButton(
                        {"preparando": "Preparar", "listo": "Marcar listo", "entregado": "Confirmar entrega"}[next_state],
                        on_click=lambda e, oid=order["id"], target=next_state: change(oid, target),
                    ))
                lista.controls.append(ft.Container(
                    content=ft.Column(controls, spacing=8, tight=True),
                    padding=15, border_radius=12,
                    border=ft.Border.all(1, N.AMBER_400 if state == "pendiente" else N.BLUE_400),
                ))
            contador.value = f"Comandas IntraShop · {len(rows)}"
            if not rows:
                lista.controls.append(ft.Text("No hay pedidos para mostrar.", size=14))
        except Exception as exc:
            lista.controls = [ft.Text(f"No se pudieron consultar las comandas: {exc}", color=N.RED_400)]
        page.update()

    def change(order_id, target):
        try:
            adapter.cambiar(order_id, target, operador or "operador POS")
            refresh()
        except Exception as exc:
            from ui.helpers import snack
            snack(page, str(exc), ok=False)

    filtro.on_change = refresh
    vista = ft.Column([
        ft.Row([contador, filtro, ft.OutlinedButton("Actualizar", icon=ft.Icons.REFRESH, on_click=refresh)],
               alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        lista,
    ], expand=True)
    refresh()
    return vista

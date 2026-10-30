"""Vista compacta de comandas para el POS Flet.

Los permisos se validan en la navegación principal; la base SQLite es
la fuente de verdad de los estados y del operador que entrega.
"""
import flet as ft
import json
from database_manager import DatabaseManager
from adapters.entregas import EntregasAdapter
from ui.paleta import N


def panel_entregas(page, operador, puede_configurar=False):
    adapter = EntregasAdapter()
    prefs = DatabaseManager()
    try:
        seleccion = set(json.loads(prefs.get_config_value("INTRASHOP_TOTEMS_FILTRO") or "[]"))
    except (ValueError, TypeError):
        seleccion = set()
    totems = []
    filtro_info = ft.Text("Todos los tótems", color=N.BLUE_400, size=12)
    opciones_totems = ft.Column(spacing=4)
    todos = ft.Checkbox(label="Todos los tótems (incluye futuros)", value=not bool(seleccion))
    lista = ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO, expand=True)
    contador = ft.Text("Pedidos pendientes", size=17, weight=ft.FontWeight.BOLD)
    conexion = ft.Container(
        content=ft.Text("● Comprobando conexión con el servidor / tótem…", color=N.AMBER_400, size=12),
        padding=12, border_radius=10, bgcolor=N.GREY_800,
    )
    filtro = ft.Dropdown(label="Estado", value="activos", width=180, options=[
        ft.dropdown.Option("activos", "Activos"),
        ft.dropdown.Option("entregado", "Entregados"),
    ])

    def guardar_filtro(e=None):
        nonlocal seleccion
        nuevos = set() if todos.value else {cb.data for cb in opciones_totems.controls if cb.value}
        if not todos.value and not nuevos:
            filtro_info.value = "Seleccioná un tótem o activá Todos."
            filtro_info.color = N.RED_400
            page.update()
            return
        seleccion = nuevos
        prefs.set_config("INTRASHOP_TOTEMS_FILTRO", json.dumps(sorted(seleccion)))
        filtro_info.color = N.GREEN_400
        refresh()

    def refresh(_=None):
        try:
            rows = adapter.listar()
            totems = adapter.totems()
            opciones_totems.controls.clear()
            for t in totems:
                opciones_totems.controls.append(ft.Checkbox(
                    label=t["nombre"] + " · " + t["id"][:8],
                    value=t["id"] in seleccion, data=t["id"], disabled=bool(todos.value)))
            filtro_info.value = ("Todos los tótems" if not seleccion else
                "Atendiendo: " + ", ".join(t["nombre"] for t in totems if t["id"] in seleccion))
            if seleccion:
                rows = [o for o in rows if o.get("totem_id") in seleccion]
            conexion.content.value = "● Conectado al servidor POS · " + adapter.base_url
            conexion.content.color = N.GREEN_400
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
                if state == "pendiente":
                    controls.append(ft.FilledButton(
                        "Entregar ahora", icon=ft.Icons.CHECK_CIRCLE,
                        on_click=lambda e, oid=order["id"]: change(oid, "entregado"),
                    ))
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
            import httpx
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 404:
                detalle = "El servidor no expone el endpoint de entregas. Reiniciá el servicio POS y verificá /openapi.json."
            elif isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (401, 403):
                detalle = "Acceso denegado. Revisá la API key y los permisos del usuario."
            else:
                detalle = "No hay conexión con el servidor POS / tótem. Revisá la URL, red LAN y servicio."
            conexion.content.value = "● " + detalle
            conexion.content.color = N.RED_400
            lista.controls = [ft.Text(detalle, color=N.RED_400),
                              ft.OutlinedButton("Reintentar conexión", icon=ft.Icons.REFRESH, on_click=refresh)]
        page.update()

    def change(order_id, target):
        try:
            adapter.cambiar(order_id, target, operador or "operador POS")
            refresh()
        except Exception as exc:
            from ui.helpers import snack
            snack(page, str(exc), ok=False)

    filtro.on_change = refresh
    def cambiar_todos(e):
        for cb in opciones_totems.controls:
            cb.disabled = bool(todos.value)
        page.update()
    todos.on_change = cambiar_todos
    selector = ft.Column([ft.Text("Tótems asignados a esta caja", weight=ft.FontWeight.BOLD), filtro_info])
    if puede_configurar:
        selector.controls.extend([todos, opciones_totems,
            ft.FilledButton("Guardar filtro de esta caja", icon=ft.Icons.SAVE, on_click=guardar_filtro)])
    vista = ft.Column([
        conexion,
        selector,
        ft.Row([contador, filtro, ft.OutlinedButton("Actualizar", icon=ft.Icons.REFRESH, on_click=refresh)],
               alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        lista,
    ], expand=True)
    refresh()
    return vista

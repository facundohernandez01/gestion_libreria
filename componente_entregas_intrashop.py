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
    from core.terminal_identity import terminal_id
    this_terminal = terminal_id()
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
        cerrar_filtro()
        refresh()

    def cerrar_filtro(e=None):
        dialogo_filtro.open = False
        page.update()

    def abrir_filtro(e=None):
        refresh()
        dialogo_filtro.open = True
        page.update()

    def refresh(_=None):
        try:
            rows = adapter.listar()
            totems = adapter.totems()
            checked = {cb.data: cb.value for cb in opciones_totems.controls}
            opciones_totems.controls.clear()
            for t in totems:
                opciones_totems.controls.append(ft.Checkbox(
                    label=t["nombre"] + " · " + t["id"][:8] + " · visto " + str(t.get("ultimo_contacto","—")),
                    value=checked.get(t["id"], t["id"] in seleccion), data=t["id"], disabled=bool(todos.value)))
            filtro_info.value = ("Todos los tótems" if not seleccion else
                "Atendiendo: " + ", ".join(t["nombre"] for t in totems if t["id"] in seleccion))
            if seleccion:
                rows = [o for o in rows if o.get("totem_id") in seleccion]
            conexion.content.value = "● Conectado al servidor POS · " + adapter.base_url
            conexion.content.color = N.GREEN_400
            estado_conexion.color = N.GREEN_400
            estado_conexion.tooltip = conexion.content.value
            rows = [o for o in rows if (o["estado"] == "entregado") == (filtro.value == "entregado")]
            lista.controls.clear()
            for order in rows:
                state = order["estado"]
                label = {"pendiente": "Pendiente", "preparando": "Preparando",
                         "listo": "Listo para entregar", "entregado": "Entregado"}[state]
                next_state = {"pendiente": "preparando", "preparando": "listo",
                              "listo": "entregado"}.get(state)
                controls = [
                    ft.Text("Origen: " + (order.get("totem_nombre") or "Tótem sin identificar"), size=12, color=N.BLUE_400),
                    ft.Row([
                        ft.Text(f"Pedido #{order['venta_id']}", weight=ft.FontWeight.BOLD, size=16),
                        ft.Text(label, color=N.GREEN_400 if state == "entregado" else N.AMBER_400),
                        ft.Text(f"$ {order['total']:,.2f}", weight=ft.FontWeight.BOLD),
                    ], spacing=16),
                    ft.Text(" · ".join(f"{i['cantidad']} × {i['descripcion']}" for i in order["items"]), size=12),
                ]
                owner = order.get("tomado_por")
                mine = owner == operador and order.get("tomado_terminal") == this_terminal
                controls.append(ft.Text("Tomada por: " + owner if owner else "Disponible para tomar",
                    color=N.AMBER_400 if owner and not mine else N.GREEN_400, size=12))
                if not owner:
                    controls.append(ft.FilledButton("Tomar comanda", icon=ft.Icons.LOCK_OPEN,
                        on_click=lambda e, oid=order["id"]: claim(oid)))
                elif mine and state != "entregado":
                    controls.append(ft.OutlinedButton("Liberar comanda",
                        on_click=lambda e, oid=order["id"]: release(oid)))
                if state == "pendiente" and mine:
                    controls.append(ft.FilledButton(
                        "Entregar ahora", icon=ft.Icons.CHECK_CIRCLE,
                        on_click=lambda e, oid=order["id"]: change(oid, "entregado"),
                    ))
                if next_state and mine:
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
            estado_conexion.color = N.RED_400
            estado_conexion.tooltip = conexion.content.value
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

    def claim(order_id):
        try:
            adapter.tomar(order_id, operador)
        except Exception as exc:
            from ui.helpers import snack
            snack(page, "No se pudo tomar la comanda: " + str(exc), ok=False)
        refresh()

    def release(order_id):
        try:
            adapter.liberar(order_id, operador)
        except Exception as exc:
            from ui.helpers import snack
            snack(page, str(exc), ok=False)
        refresh()

    filtro.on_change = refresh
    def cambiar_todos(e):
        for cb in opciones_totems.controls:
            cb.disabled = bool(todos.value)
        page.update()
    todos.on_change = cambiar_todos
    dialogo_filtro = ft.AlertDialog(
        modal=True,
        title=ft.Text("Tótems atendidos por esta caja"),
        content=ft.Container(
            content=ft.Column([
                ft.Text("Seleccioná qué tótems reciben atención en este POS.", size=12),
                todos,
                ft.Container(content=ft.Column([opciones_totems], scroll=ft.ScrollMode.AUTO),
                             height=260, width=420),
            ], spacing=12, tight=True),
            width=440,
        ),
        actions=[
            ft.TextButton("Cancelar", on_click=cerrar_filtro),
            ft.FilledButton("Guardar", icon=ft.Icons.SAVE, on_click=guardar_filtro),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.overlay.append(dialogo_filtro)
    estado_conexion = ft.Icon(ft.Icons.CIRCLE, size=10, color=N.AMBER_400,
                              tooltip="Comprobando conexión")
    cabecera = [contador, filtro]
    if puede_configurar:
        cabecera.append(ft.OutlinedButton("Tótems", icon=ft.Icons.TUNE, on_click=abrir_filtro))
    cabecera.extend([ft.IconButton(icon=ft.Icons.REFRESH, tooltip="Actualizar", on_click=refresh),
                     estado_conexion])
    vista = ft.Column([
        ft.Row(cabecera, alignment=ft.MainAxisAlignment.SPACE_BETWEEN, wrap=True),
               alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        lista,
    ], expand=True)
    refresh()
    # Sondeo compartido: al tomar una comanda en otra caja, esta vista se actualiza.
    if hasattr(page, "run_task"):
        import asyncio
        async def auto_refresh():
            while True:
                await asyncio.sleep(5)
                if vista.page is None:
                    break
                refresh()
        page.run_task(auto_refresh)
    return vista

"""Vista compacta de comandas para el POS Flet.

Los permisos se validan en la navegación principal; la base SQLite es
la fuente de verdad de los estados y del operador que entrega.
"""
import sqlite3
import flet as ft
from core.settings import settings
from intrashop_entregas import ensure_schema
from ui.paleta import N


def panel_entregas(page, operador):
    lista = ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO, expand=True)
    contador = ft.Text("Pedidos pendientes", size=17, weight=ft.FontWeight.BOLD)
    filtro = ft.Dropdown(label="Estado", value="activos", width=180, options=[
        ft.dropdown.Option("activos", "Activos"),
        ft.dropdown.Option("entregado", "Entregados"),
    ])

    def refresh(_=None):
        try:
            with sqlite3.connect(settings.db_path, timeout=10) as conn:
                conn.row_factory = sqlite3.Row
                ensure_schema(conn)
                rows = conn.execute("""
                    SELECT e.id, e.venta_id, e.estado, e.fecha_creacion, v.total
                    FROM intrashop_entregas e JOIN ventas v ON v.id=e.venta_id
                    WHERE (?='activos' AND e.estado!='entregado') OR e.estado=?
                    ORDER BY e.fecha_creacion DESC LIMIT 150
                """, (filtro.value, filtro.value)).fetchall()
                lista.controls.clear()
                for order in rows:
                    items = conn.execute("""
                        SELECT p.descripcion, vi.cantidad FROM venta_items vi
                        JOIN productos p ON p.id=vi.producto_id WHERE vi.venta_id=?
                    """, (order["venta_id"],)).fetchall()
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
                        ft.Text(" · ".join(f"{i['cantidad']} × {i['descripcion']}" for i in items), size=12),
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
            with sqlite3.connect(settings.db_path, timeout=10) as conn:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute("SELECT estado FROM intrashop_entregas WHERE id=?", (order_id,)).fetchone()
                transitions = {"pendiente": "preparando", "preparando": "listo", "listo": "entregado"}
                if not row or transitions.get(row[0]) != target:
                    raise ValueError("El estado del pedido cambió. Actualizá la pantalla.")
                cur = conn.execute("""
                    UPDATE intrashop_entregas SET estado=?, fecha_actualizacion=CURRENT_TIMESTAMP,
                    entregado_por=CASE WHEN ?='entregado' THEN ? ELSE entregado_por END,
                    fecha_entrega=CASE WHEN ?='entregado' THEN CURRENT_TIMESTAMP ELSE fecha_entrega END
                    WHERE id=? AND estado=?
                """, (target, target, operador or "operador POS", target, order_id, row[0]))
                if cur.rowcount != 1:
                    raise ValueError("Pedido actualizado por otro operador")
                conn.commit()
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

"""Diálogo de recepción de una orden de compra (total o parcial).

Permite indicar cuántas unidades llegaron por ítem, número de remito y si se
cancelan las cantidades restantes. La lógica de stock vive en DatabaseManager.
"""
from __future__ import annotations

import flet as ft

from ui.helpers import abrir_dialogo, snack


def abrir_recepcion_compra(db_manager, page: ft.Page, orden: dict, on_done=None):
    detalle = db_manager.obtener_orden_compra(int(orden["id"]))
    if not detalle:
        snack(page, "No se encontró la orden", ok=False)
        return None
    pendientes = [it for it in detalle.get("items") or []
                  if int(it.get("cantidad_pendiente") or 0) > 0]
    if not pendientes:
        snack(page, "La orden no tiene cantidades pendientes", ok=False)
        return None

    campos: dict[int, ft.TextField] = {}
    filas = []
    for it in pendientes:
        campo = ft.TextField(
            value=str(int(it["cantidad_pendiente"])), width=90, dense=True,
            keyboard_type=ft.KeyboardType.NUMBER,
            text_align=ft.TextAlign.RIGHT)
        campos[int(it["id"])] = campo
        filas.append(ft.Container(
            content=ft.Row([
                ft.Column([
                    ft.Text(it.get("producto_nombre") or "", size=12,
                            weight=ft.FontWeight.BOLD),
                    ft.Text(f"{it.get('producto_codigo') or ''} · "
                            f"{it.get('proveedor_nombre') or 'Sin proveedor'}",
                            size=10, color=ft.Colors.GREY_500),
                ], spacing=1, expand=True),
                ft.Text(f"Pedido {it['cantidad']}", size=11,
                        color=ft.Colors.GREY_400, width=90),
                ft.Text(f"Recibido {it.get('cantidad_recibida') or 0}",
                        size=11, color=ft.Colors.GREEN_300, width=100),
                ft.Text(f"Pend. {it['cantidad_pendiente']}", size=11,
                        color=ft.Colors.AMBER_300, width=80),
                campo,
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=6),
            padding=6, border_radius=5,
            bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.WHITE),
        ))

    remito_field = ft.TextField(label="Nro de remito (opcional)", width=220,
                                dense=True)
    obs_field = ft.TextField(label="Observaciones", width=420, dense=True)
    cancelar_check = ft.Checkbox(
        label="Cancelar las cantidades restantes (no habrá otra entrega)",
        value=False)

    def _cerrar():
        try:
            dlg.open = False
            page.update()
        except Exception:
            pass

    def _recibir(_e=None):
        recepciones = {}
        for item_id, campo in campos.items():
            try:
                cant = int(float(str(campo.value or "0").replace(",", ".")))
            except (TypeError, ValueError):
                cant = 0
            if cant > 0:
                recepciones[item_id] = cant
        if not recepciones and not cancelar_check.value:
            snack(page, "Ingresá al menos una cantidad a recibir", ok=False)
            return
        ok, msg = db_manager.recibir_orden_compra(
            int(detalle["id"]), recepciones,
            remito=remito_field.value or "",
            observaciones=obs_field.value or "",
            cancelar_restante=bool(cancelar_check.value))
        _cerrar()
        snack(page, msg, ok=ok)
        if on_done:
            on_done()

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Row([
            ft.Icon(ft.Icons.INVENTORY, color=ft.Colors.GREEN_400),
            ft.Text(f"Recepcionar orden #{detalle['id']}"),
        ]),
        content=ft.Container(
            content=ft.Column([
                ft.Text("Indicá cuántas unidades llegaron de cada ítem. "
                        "Podés recepcionar solo una parte y dejar el resto "
                        "pendiente para otra entrega.",
                        size=11, color=ft.Colors.GREY_400),
                ft.Divider(height=8),
                ft.Column(filas, spacing=4, scroll=ft.ScrollMode.AUTO),
                ft.Divider(height=8),
                ft.Row([remito_field, obs_field], spacing=8, wrap=True),
                cancelar_check,
            ], spacing=8, scroll=ft.ScrollMode.AUTO),
            width=860, height=500,
        ),
        actions=[
            ft.TextButton("CANCELAR", on_click=lambda _e: _cerrar()),
            ft.FilledButton("RECEPCIONAR", icon=ft.Icons.CHECK,
                            on_click=_recibir,
                            style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN_700,
                                                 color=ft.Colors.WHITE)),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    abrir_dialogo(page, dlg)
    return dlg

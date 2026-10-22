"""Ingreso de stock por escaneo de código de barras.

Diseñado para recepcionar mercadería desde el local o desde un celular
(control responsive). Permite:
- Buscar el producto por código (lector o tipeo) y ver sus órdenes pendientes.
- Recepcionar contra una o varias órdenes de compra (con remito opcional).
- Si no se elige orden, registrar un ingreso directo de stock.
- Ver los últimos ingresos del día.
"""
from __future__ import annotations

from datetime import datetime

import flet as ft

from ui.helpers import parse_int, snack
from ui.theme import BTN_PRIMARIO


def IngresoStockView(db_manager, on_volver, page: ft.Page):
    estado = {"producto": None, "pendientes": [], "seleccion": {}}

    barcode_field = ft.TextField(
        label="Código de barras / código de producto",
        prefix_icon=ft.Icons.QR_CODE_SCANNER, autofocus=True,
        hint_text="Escaneá o escribí el código y presioná Enter",
        expand=True)
    cantidad_field = ft.TextField(
        label="Cantidad recibida", value="1", width=170,
        keyboard_type=ft.KeyboardType.NUMBER,
        text_align=ft.TextAlign.RIGHT)
    remito_field = ft.TextField(
        label="Nro de remito (opcional)", width=220, expand=True)
    buscar_btn = ft.FilledButton(
        "BUSCAR", icon=ft.Icons.SEARCH, height=44,
        on_click=lambda _e: buscar())
    recibir_btn = ft.FilledButton(
        "RECEPCIONAR", icon=ft.Icons.INVENTORY, height=46, disabled=True,
        style=BTN_PRIMARIO, on_click=lambda _e: recibir())

    producto_panel = ft.Container(visible=False)
    pendientes_panel = ft.Column(spacing=6)
    historial_panel = ft.Column(spacing=4)
    resumen_text = ft.Text("", size=12, color=ft.Colors.GREY_400)

    # ---------- producto / órdenes ----------
    def _producto_card(p: dict):
        stock = int(p.get("stock_actual") or 0)
        minimo = int(p.get("stock_minimo") or 0)
        color = (ft.Colors.RED_400 if stock <= 0 else
                 ft.Colors.ORANGE_400 if stock <= minimo else ft.Colors.GREEN_400)
        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.BOOK, color=ft.Colors.BLUE_300),
                    ft.Text(p.get("descripcion") or "", size=16,
                            weight=ft.FontWeight.BOLD, expand=True),
                    ft.Container(
                        content=ft.Text(f"Stock: {stock}", size=14,
                                        weight=ft.FontWeight.BOLD, color=color),
                        padding=8, border_radius=6,
                        bgcolor=ft.Colors.with_opacity(0.15, color)),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
                ft.Text(f"Código: {p.get('codigo') or '—'}  ·  "
                        f"Proveedor: {p.get('proveedor_nombre') or 'Sin proveedor'}  ·  "
                        f"Mínimo: {minimo}",
                        size=11, color=ft.Colors.GREY_400),
            ], spacing=6),
            padding=12, border_radius=8,
            bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.WHITE),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.3, ft.Colors.BLUE_GREY_700)),
        )

    def _toggle(item_id: int, valor: bool):
        estado["seleccion"][item_id] = bool(valor)

    def _fila_pendiente(pend: dict):
        item_id = int(pend["item_id"])
        cb = ft.Checkbox(
            value=bool(estado["seleccion"].get(item_id)),
            shape=ft.RoundedRectangleBorder(radius=20))
        cb.on_change = lambda _e, i=item_id, c=cb: _toggle(i, c.value)
        estado["seleccion"].setdefault(item_id, bool(cb.value))
        return ft.Container(
            content=ft.Row([
                cb,
                ft.Column([
                    ft.Text(f"Orden #{pend['orden_id']} · "
                            f"{pend.get('proveedor_nombre') or 'Sin proveedor'}",
                            size=12, weight=ft.FontWeight.BOLD),
                    ft.Text(f"Pedido {pend['cantidad']} · recibido "
                            f"{pend.get('cantidad_recibida') or 0} · "
                            f"pendiente {pend['pendiente']} · "
                            f"{str(pend.get('fecha_creacion') or '')[:10]}",
                            size=10, color=ft.Colors.GREY_500),
                ], spacing=1, expand=True),
                ft.Container(
                    content=ft.Text(f"Pend. {pend['pendiente']}", size=12,
                                    weight=ft.FontWeight.BOLD,
                                    color=ft.Colors.AMBER_300),
                    padding=6, border_radius=5,
                    bgcolor=ft.Colors.with_opacity(0.15, ft.Colors.AMBER_700)),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
            padding=8, border_radius=6,
            bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.WHITE),
        )

    def _render_pendientes():
        pendientes_panel.controls.clear()
        pendientes = estado["pendientes"]
        if not pendientes:
            pendientes_panel.controls.append(ft.Text(
                "Este producto no tiene órdenes de compra pendientes. "
                "El ingreso se registrará como stock directo.",
                size=11, italic=True, color=ft.Colors.GREY_500))
            return
        pendientes_panel.controls.append(ft.Text(
            f"ÓRDENES PENDIENTES ({len(pendientes)}) — marcá sobre cuál "
            "recepcionar (si no marcás ninguna, el ingreso es directo)",
            size=11, weight=ft.FontWeight.BOLD, color=ft.Colors.AMBER_300))
        for pend in pendientes:
            pendientes_panel.controls.append(_fila_pendiente(pend))

    def buscar(_e=None):
        codigo = (barcode_field.value or "").strip()
        if not codigo:
            return
        producto = db_manager.obtener_producto_por_codigo(codigo)
        if not producto:
            producto = db_manager.buscar_productos(codigo, "codigo", limit=1)
            producto = producto[0] if producto else None
        if not producto:
            snack(page, f"No se encontró el producto «{codigo}»", ok=False)
            barcode_field.select_all()
            page.update()
            return
        estado["producto"] = producto
        estado["pendientes"] = db_manager.buscar_ordenes_pendientes_producto(
            int(producto["id"]))
        estado["seleccion"] = {}
        producto_panel.content = _producto_card(producto)
        producto_panel.visible = True
        _render_pendientes()
        recibir_btn.disabled = False
        resumen_text.value = ""
        page.update()
        try:
            page.run_task(cantidad_field.focus)
        except Exception:
            pass

    # ---------- ingreso ----------
    def _cerrar_producto():
        estado.update(producto=None, pendientes=[], seleccion={})
        producto_panel.visible = False
        pendientes_panel.controls.clear()
        recibir_btn.disabled = True
        barcode_field.value = ""
        cantidad_field.value = "1"
        page.update()

    def recibir(_e=None):
        producto = estado["producto"]
        if not producto:
            snack(page, "Primero buscá un producto", ok=False)
            return
        cantidad = parse_int(cantidad_field.value, 0)
        if cantidad <= 0:
            snack(page, "Ingresá una cantidad mayor a cero", ok=False)
            return
        remito = (remito_field.value or "").strip()
        seleccionados = [
            pend for pend in estado["pendientes"]
            if estado["seleccion"].get(int(pend["item_id"]))
        ]
        if seleccionados:
            total_pend = sum(int(p["pendiente"]) for p in seleccionados)
            if cantidad > total_pend:
                snack(page, (f"La cantidad supera lo pendiente en las órdenes "
                             f"seleccionadas ({total_pend}). Desmarcá órdenes o "
                             "ajustá la cantidad."), ok=False)
                return
            resto = cantidad
            mensajes = []
            for pend in seleccionados:
                if resto <= 0:
                    break
                tomar = min(int(pend["pendiente"]), resto)
                ok, msg = db_manager.recibir_orden_compra(
                    int(pend["orden_id"]), {int(pend["item_id"]): tomar},
                    remito=remito,
                    observaciones="Recepción por escaneo de código")
                if ok:
                    mensajes.append(f"Orden #{pend['orden_id']}: +{tomar}")
                else:
                    mensajes.append(f"Orden #{pend['orden_id']}: {msg}")
                resto -= tomar
            snack(page, " · ".join(mensajes), ok=True)
        else:
            ok, msg = db_manager.ingresar_stock_directo(
                int(producto["id"]), cantidad, remito=remito,
                observaciones="Ingreso por escaneo (sin orden)")
            snack(page, msg, ok=ok)
        _cerrar_producto()
        cargar_historial()
        try:
            page.run_task(barcode_field.focus)
        except Exception:
            pass

    # ---------- historial del día ----------
    def cargar_historial():
        historial_panel.controls.clear()
        hoy = datetime.now().strftime("%Y-%m-%d")
        try:
            movs = db_manager.obtener_movimientos_stock_detallado(limit=80)
        except Exception:
            movs = []
        ingresos = [m for m in movs
                    if m.get("tipo") == "ingreso"
                    and str(m.get("fecha") or "").startswith(hoy)][:10]
        if not ingresos:
            historial_panel.controls.append(ft.Text(
                "Todavía no hay ingresos registrados hoy.", size=11,
                italic=True, color=ft.Colors.GREY_500))
            return
        for m in ingresos:
            referencia = (f"Orden #{m['referencia_id']}"
                          if m.get("referencia_id") else "Directo")
            historial_panel.controls.append(ft.Row([
                ft.Icon(ft.Icons.ARROW_UPWARD, size=13,
                        color=ft.Colors.GREEN_400),
                ft.Text(str(m.get("fecha") or "")[11:16], size=11, width=42,
                        color=ft.Colors.GREY_500),
                ft.Text(m.get("producto_codigo") or "", size=11, width=95,
                        color=ft.Colors.GREY_400),
                ft.Text(m.get("producto_nombre") or "", size=11, expand=True,
                        max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                ft.Text(m.get("usuario") or "—", size=10,
                        color=ft.Colors.CYAN_300, width=70),
                ft.Text(referencia, size=10, color=ft.Colors.AMBER_300, width=80),
                ft.Text(f"+{m.get('cantidad')}", size=12,
                        weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_300,
                        width=46, text_align=ft.TextAlign.RIGHT),
            ], spacing=6))

    barcode_field.on_submit = buscar
    cantidad_field.on_submit = lambda _e: recibir()
    remito_field.on_submit = lambda _e: recibir()
    cargar_historial()

    return ft.Container(
        content=ft.Column([
            ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.ADD_BOX, size=24, color=ft.Colors.CYAN_300),
                    ft.Text("INGRESO DE STOCK", size=20, weight=ft.FontWeight.BOLD),
                ], alignment=ft.MainAxisAlignment.CENTER, spacing=10),
                bgcolor=ft.Colors.BLUE_900, padding=8, alignment=ft.Alignment.CENTER),
            ft.Container(height=10),
            ft.Container(
                content=ft.Column([
                    ft.ResponsiveRow([
                        ft.Container(barcode_field, col={"xs": 12, "sm": 8, "md": 6},
                                     padding=0),
                        ft.Container(cantidad_field, col={"xs": 6, "sm": 4, "md": 2},
                                     padding=0),
                        ft.Container(remito_field, col={"xs": 6, "sm": 12, "md": 4},
                                     padding=0),
                    ], spacing=8, run_spacing=8),
                    ft.ResponsiveRow([
                        ft.Container(buscar_btn, col={"xs": 12, "sm": 6, "md": 3},
                                     padding=0),
                        ft.Container(recibir_btn, col={"xs": 12, "sm": 6, "md": 3},
                                     padding=0),
                        ft.Container(
                            content=ft.OutlinedButton(
                                "VOLVER", icon=ft.Icons.ARROW_BACK, height=46,
                                on_click=lambda _e: on_volver()),
                            col={"xs": 12, "sm": 6, "md": 3}, padding=0),
                    ], spacing=8, run_spacing=8),
                    resumen_text,
                ], spacing=10),
                padding=12, border_radius=8,
                border=ft.Border.all(1, ft.Colors.with_opacity(0.35,
                                                               ft.Colors.BLUE_GREY_700)),
                bgcolor=ft.Colors.with_opacity(0.04, ft.Colors.WHITE)),
            ft.Container(height=10),
            producto_panel,
            ft.Container(height=8),
            pendientes_panel,
            ft.Container(height=10),
            ft.Container(
                content=ft.Column([
                    ft.Text("ÚLTIMOS INGRESOS DE HOY", size=11,
                            weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_300),
                    historial_panel,
                ], spacing=6),
                padding=10, border_radius=8,
                bgcolor=ft.Colors.with_opacity(0.04, ft.Colors.WHITE)),
            ft.Container(height=6),
            ft.Text("Escaneá el código, indicá la cantidad y elegí la orden de "
                    "compra si corresponde. Pensado para usarse también desde el "
                    "celular en el depósito.", size=11, italic=True,
                    color=ft.Colors.GREY_500),
        ], scroll=ft.ScrollMode.AUTO, expand=True),
        padding=20, expand=True,
    )

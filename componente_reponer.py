"""Modal para armar una orden de compra / reposición de stock."""
from __future__ import annotations

import asyncio
from datetime import datetime

import flet as ft

from services.compra_service import exportar_orden_excel
from ui.helpers import cerrar_dialogo, snack
from utils.file_dialogs import agregar_extension, save_file


def ReponerModal(db_manager, page: ft.Page, on_creada=None, orden: dict | None = None):
    carrito: list[dict] = []
    if orden:
        for it in orden.get("items") or []:
            carrito.append({
                "producto_id": it["producto_id"],
                "codigo": it.get("producto_codigo") or "",
                "descripcion": it.get("producto_nombre") or "",
                "proveedor_id": it.get("proveedor_id"),
                "cantidad": int(it.get("cantidad") or 1),
                "precio_costo": float(it.get("precio_costo") or 0),
            })
    proveedores = db_manager.listar_proveedores("", 1000)
    opciones_prov = [ft.dropdown.Option("0", "Sin proveedor")] + [
        ft.dropdown.Option(str(p["id"]), p["nombre"]) for p in proveedores
    ]

    search_field = ft.TextField(
        label="Buscar producto para reponer", prefix_icon=ft.Icons.SEARCH,
        width=430, autofocus=True, ignore_up_down_keys=True,
        hint_text="Código o descripción…",
    )
    filtro = ft.Dropdown(width=150, value="descripcion", options=[
        ft.dropdown.Option("descripcion", "Descripción"),
        ft.dropdown.Option("codigo", "Código"),
    ])
    resultados = ft.ListView(height=150, spacing=4)
    carrito_list = ft.ListView(height=250, spacing=6)
    total_text = ft.Text("TOTAL: $0.00", size=18, weight=ft.FontWeight.BOLD,
                         color=ft.Colors.GREEN_300)
    grupos_text = ft.Text("", size=11, color=ft.Colors.GREY_400)
    observaciones = ft.TextField(
        label="Observaciones", multiline=True, min_lines=1, max_lines=2,
        width=620, hint_text="Ej.: pedido para reposición semanal",
        value=(orden or {}).get("observaciones") or "")

    # ---------- búsqueda ----------
    def _agregar(producto: dict):
        for item in carrito:
            if item["producto_id"] == producto["id"]:
                item["cantidad"] += 1
                _render_carrito()
                return
        carrito.append({
            "producto_id": producto["id"],
            "codigo": producto["codigo"],
            "descripcion": producto["descripcion"],
            "proveedor_id": producto.get("proveedor_id"),
            "cantidad": 1,
            "precio_costo": float(producto.get("precio_costo") or 0),
        })
        search_field.value = ""
        resultados.controls.clear()
        _render_carrito()
        _focus_busqueda()

    def _focus_busqueda():
        try:
            if hasattr(page, "run_task"):
                page.run_task(search_field.focus)
            else:
                search_field.focus()
        except Exception:
            pass

    def _tarjeta(p: dict):
        stock = int(p.get("stock_actual") or 0)
        minimo = int(p.get("stock_minimo") or 0)
        color = ft.Colors.RED_400 if stock <= 0 else (
            ft.Colors.ORANGE_400 if stock <= minimo else ft.Colors.GREEN_400)
        return ft.Container(
            content=ft.Row([
                ft.Column([
                    ft.Text(p["descripcion"], size=12, weight=ft.FontWeight.BOLD),
                    ft.Text(f"{p['codigo']} · {p.get('proveedor_nombre') or 'Sin proveedor'}",
                            size=10, color=ft.Colors.GREY_500),
                ], spacing=1, expand=True),
                ft.Text(f"Stock: {stock}", size=11, color=color),
                ft.IconButton(icon=ft.Icons.ADD_CIRCLE, icon_color=ft.Colors.GREEN_400,
                              tooltip="Agregar", on_click=lambda _e, prod=p: _agregar(prod)),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            bgcolor=ft.Colors.BLUE_GREY_900, padding=7, border_radius=5,
        )

    def _buscar(e=None):
        termino = (search_field.value or "").strip()
        resultados.controls.clear()
        if termino:
            encontrados = db_manager.buscar_productos(
                termino, filtro.value or "descripcion", limit=12)
            for p in encontrados:
                resultados.controls.append(_tarjeta(p))
        else:
            sugeridos = [p for p in db_manager.obtener_stock_productos()
                         if p.get("prioridad_stock", 3) < 3][:8]
            if sugeridos:
                resultados.controls.append(
                    ft.Text("Sugeridos (stock bajo o agotado)", size=10,
                            color=ft.Colors.ORANGE_300))
                for p in sugeridos:
                    resultados.controls.append(_tarjeta(p))
        page.update()

    # ---------- carrito ----------
    def _subtotal(item: dict) -> float:
        return round(float(item["cantidad"]) * float(item["precio_costo"]), 2)

    def _actualizar_totales():
        total = 0.0
        grupos: dict[str, float] = {}
        for it in carrito:
            subtotal = _subtotal(it)
            total += subtotal
            prov_id = it.get("proveedor_id")
            prov_nombre = next(
                (p["nombre"] for p in proveedores if int(p["id"]) == int(prov_id)),
                "Sin proveedor") if prov_id else "Sin proveedor"
            grupos[prov_nombre] = grupos.get(prov_nombre, 0.0) + subtotal
        total_text.value = f"TOTAL: ${total:.2f}"
        grupos_text.value = " · ".join(
            f"{nombre}: ${importe:.2f}" for nombre, importe in grupos.items()) if grupos else ""
        page.update()

    def _render_carrito():
        carrito_list.controls.clear()
        total = 0.0
        grupos: dict[str, float] = {}
        for item in carrito:
            subtotal = _subtotal(item)
            total += subtotal
            prov_id = item.get("proveedor_id")
            prov_nombre = next(
                (p["nombre"] for p in proveedores if int(p["id"]) == int(prov_id)),
                "Sin proveedor") if prov_id else "Sin proveedor"
            grupos[prov_nombre] = grupos.get(prov_nombre, 0.0) + subtotal

            def _cantidad(delta, it=item):
                nueva = int(it["cantidad"]) + delta
                if nueva < 1:
                    return
                it["cantidad"] = nueva
                _render_carrito()

            def _costo(e, it=item, subtotal_lbl=None):
                try:
                    it["precio_costo"] = max(0.0, float((e.control.value or "0").replace(",", ".")))
                except (TypeError, ValueError):
                    it["precio_costo"] = 0.0
                if subtotal_lbl is not None:
                    subtotal_lbl.value = f"${_subtotal(it):.2f}"
                _actualizar_totales()

            def _proveedor(e, it=item):
                valor = e.control.value
                it["proveedor_id"] = int(valor) if valor and valor != "0" else None
                _render_carrito()

            def _quitar(_e, it=item):
                carrito.remove(it)
                _render_carrito()

            subtotal_text = ft.Text(f"${subtotal:.2f}", size=13, width=90,
                                    weight=ft.FontWeight.BOLD,
                                    text_align=ft.TextAlign.RIGHT)
            costo_field = ft.TextField(
                value=f"{float(item['precio_costo']):.2f}", width=100, dense=True,
                prefix=ft.Text("$"), keyboard_type=ft.KeyboardType.NUMBER,
            )
            prov_dropdown = ft.Dropdown(value=str(prov_id) if prov_id else "0",
                                        options=opciones_prov, width=180, dense=True)
            prov_dropdown.on_change = _proveedor
            costo_field.on_change = lambda e, it=item, lbl=subtotal_text: _costo(e, it, lbl)
            carrito_list.controls.append(ft.Container(
                content=ft.Row([
                    ft.Column([
                        ft.Text(item["descripcion"], size=12, weight=ft.FontWeight.BOLD),
                        ft.Text(item["codigo"], size=10, color=ft.Colors.GREY_500),
                    ], spacing=1, width=260),
                    prov_dropdown,
                    ft.Row([
                        ft.IconButton(icon=ft.Icons.REMOVE, icon_size=16,
                                      on_click=lambda _e, f=_cantidad: f(-1)),
                        ft.Text(str(item["cantidad"]), size=14, width=28,
                                text_align=ft.TextAlign.CENTER),
                        ft.IconButton(icon=ft.Icons.ADD, icon_size=16,
                                      on_click=lambda _e, f=_cantidad: f(1)),
                    ], spacing=0),
                    costo_field,
                    subtotal_text,
                    ft.IconButton(icon=ft.Icons.DELETE_OUTLINE,
                                  icon_color=ft.Colors.RED_400, tooltip="Quitar",
                                  on_click=_quitar),
                ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.BLUE_GREY_700),
                padding=6, border_radius=5,
            ))
        if not carrito:
            carrito_list.controls.append(ft.Container(
                content=ft.Text("Agregá productos con el buscador",
                                italic=True, color=ft.Colors.GREY_500),
                padding=20, alignment=ft.Alignment.CENTER))
        total_text.value = f"TOTAL: ${total:.2f}"
        if grupos:
            grupos_text.value = " · ".join(
                f"{nombre}: ${importe:.2f}" for nombre, importe in grupos.items())
        else:
            grupos_text.value = ""
        page.update()

    # ---------- generar ----------
    def _cerrar_modal():
        # Cierre explícito: pop_dialog falla si hay un SnackBar encima.
        try:
            dialog.open = False
            page.update()
        except Exception:
            cerrar_dialogo(page)

    def _items_orden() -> list[dict]:
        return [{
            "producto_id": it["producto_id"],
            "cantidad": int(it["cantidad"]),
            "proveedor_id": it.get("proveedor_id"),
            "precio_costo": float(it["precio_costo"]),
        } for it in carrito]

    def _guardar_orden() -> int:
        if not carrito:
            snack(page, "Agregá al menos un producto", ok=False)
            return 0
        if orden:
            ok = db_manager.actualizar_orden_compra(
                int(orden["id"]), _items_orden(), observaciones.value or "")
            if not ok:
                snack(page, "No se pudo actualizar la orden (¿ya confirmada?)", ok=False)
                return 0
            return int(orden["id"])
        orden_id = db_manager.crear_orden_compra(
            _items_orden(), observaciones.value or "")
        if not orden_id:
            snack(page, "No se pudo crear la orden", ok=False)
            return 0
        return orden_id

    def _cerrar_y_avisar(orden_id: int, extra: str = ""):
        accion = "actualizada" if orden else "creada en proceso"
        # Cerrar primero: snack() abre un diálogo y cerrar después popea el
        # SnackBar, dejando el modal abierto.
        if on_creada:
            on_creada()
        _cerrar_modal()
        snack(page, f"Orden #{orden_id} {accion}. {extra}".strip(), ok=True)

    def generar(e=None):
        orden_id = _guardar_orden()
        if orden_id:
            _cerrar_y_avisar(orden_id)

    async def generar_y_exportar(e=None):
        orden_id = _guardar_orden()
        if not orden_id:
            return
        try:
            destino = await save_file(
                page, title="Guardar orden de compra",
                file_name=f"orden_compra_{orden_id}_{datetime.now():%Y%m%d_%H%M%S}.xlsx",
                extensions=["xlsx"])
            if not destino:
                _cerrar_y_avisar(orden_id)
                return
            ruta = await asyncio.to_thread(
                exportar_orden_excel, db_manager, orden_id,
                agregar_extension(destino, "xlsx"))
            _cerrar_y_avisar(orden_id, f"Excel: {ruta}")
        except Exception as ex:  # noqa: BLE001
            if on_creada:
                on_creada()
            _cerrar_modal()
            snack(page, f"Orden #{orden_id} guardada, pero falló el Excel: {ex}", ok=False)

    search_field.on_change = _buscar
    filtro.on_change = _buscar
    _buscar()
    _render_carrito()

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Row([
            ft.Icon(ft.Icons.SHOPPING_CART, color=ft.Colors.ORANGE_400),
            ft.Text(f"EDITAR ORDEN #{orden['id']}" if orden
                    else "REPONER STOCK — NUEVA ORDEN DE COMPRA", size=17,
                    weight=ft.FontWeight.BOLD),
        ], spacing=10),
        content=ft.Container(
            content=ft.Column([
                ft.Row([search_field, filtro], spacing=8),
                resultados,
                ft.Divider(height=8),
                ft.Row([
                    ft.Text("Artículos del pedido", weight=ft.FontWeight.BOLD,
                            color=ft.Colors.BLUE_300),
                    ft.Container(expand=True),
                    grupos_text,
                ], spacing=8),
                ft.Container(content=carrito_list, height=250,
                             border=ft.Border.all(1, ft.Colors.BLUE_GREY_700),
                             border_radius=6, padding=4),
                ft.Row([observaciones, ft.Container(expand=True),
                        ft.Column([total_text, grupos_text], spacing=2,
                                  horizontal_alignment=ft.CrossAxisAlignment.END)]),
            ], spacing=8, scroll=ft.ScrollMode.AUTO),
            width=920, height=590,
        ),
        actions=[
            ft.TextButton("CANCELAR", on_click=lambda _e: _cerrar_modal()),
            ft.FilledButton("GUARDAR CAMBIOS" if orden else "GENERAR ORDEN",
                            icon=ft.Icons.SAVE, on_click=generar,
                            style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700,
                                                 color=ft.Colors.WHITE)),
            ft.FilledButton("GUARDAR + EXCEL" if orden else "GENERAR + EXCEL",
                            icon=ft.Icons.TABLE_VIEW,
                            on_click=generar_y_exportar,
                            style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN_700,
                                                 color=ft.Colors.WHITE)),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
        open=True,
    )
    return dialog

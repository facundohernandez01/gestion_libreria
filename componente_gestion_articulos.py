"""Gestión de artículos con import/export Excel via ExcelService."""
import asyncio
from datetime import datetime
from pathlib import Path

import flet as ft
from ui.paleta import N

from core.permisos import tiene
from services.excel_service import excel_service
from ui.helpers import abrir_dialogo, snack
from ui.theme import BTN_PRIMARIO
from utils.file_dialogs import agregar_extension, pick_file, save_file


def GestionArticulosView(db_manager, on_volver, page, permisos=None,
                         es_admin=False):
    permisos = permisos or {}

    def puede(clave):
        return tiene(permisos, clave, es_admin)
    productos_table = ft.DataTable(
        columns=[ft.DataColumn(ft.Text("Código", size=12)),
                 ft.DataColumn(ft.Text("Descripción", size=12)),
                 ft.DataColumn(ft.Text("Marca", size=12)),
                 ft.DataColumn(ft.Text("Proveedor", size=12)),
                 ft.DataColumn(ft.Text("Precio", size=12)),
                 ft.DataColumn(ft.Text("Stock", size=12)),
                 ft.DataColumn(ft.Text("Acciones", size=12))],
        rows=[], column_spacing=26, heading_row_height=38,
        data_row_min_height=44, data_row_max_height=56,
    )
    contador_text = ft.Text("", size=12, color=N.GREY_400)
    search_field = ft.TextField(label="BUSCAR", prefix_icon=ft.Icons.SEARCH, width=350,
                                hint_text="Código, descripción o categoría…")
    filtro_dropdown = ft.Dropdown(width=150, value="descripcion", options=[
        ft.dropdown.Option("descripcion", "Descripción"),
        ft.dropdown.Option("categoria", "Categoría"),
        ft.dropdown.Option("codigo", "Código")])

    def cargar_productos(productos=None):
        if productos is None:
            productos = db_manager.buscar_productos("", "descripcion")
        productos_table.rows.clear()
        for producto in productos:
            stock_color = N.GREEN_700 if producto["stock_actual"] > producto["stock_minimo"] else N.RED_700

            def _h(p):
                return lambda _: editar_producto(p)

            def _hist(p):
                return lambda _: ver_historial(p)

            productos_table.rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(producto["codigo"], size=12, width=130)),
                ft.DataCell(ft.Text(producto["descripcion"], size=12, width=360,
                                    max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS)),
                ft.DataCell(ft.Text(producto.get("marca", "") or "", size=12,
                                    width=120)),
                ft.DataCell(ft.Text(producto.get("proveedor_nombre") or "—", size=12,
                                    width=170, max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS)),
                ft.DataCell(ft.Text(f"${producto['precio_lista']:,.2f}", size=12,
                                    width=100)),
                ft.DataCell(ft.Text(str(producto["stock_actual"]), color=stock_color,
                                    size=12, width=70)),
                ft.DataCell(ft.Row([
                    ft.IconButton(icon=ft.Icons.EDIT, icon_color=N.BLUE_400,
                                  tooltip="Editar", on_click=_h(producto)),
                    ft.IconButton(icon=ft.Icons.HISTORY, icon_color=N.CYAN_400,\n                                  tooltip="Movimientos de stock", on_click=_hist(producto)),\n                    ft.IconButton(icon=ft.Icons.STORE, icon_color=N.PURPLE_400,\n                                  tooltip="Disponible en IntraShop",\n                                  on_click=lambda _, p=producto: configurar_tienda(p)),\n                ], spacing=0)),
            ]))
        contador_text.value = f"{len(productos)} artículo(s)"
        page.update()

    def buscar_productos(e):
        cargar_productos(db_manager.buscar_productos(search_field.value or "", filtro_dropdown.value))

    def _abrir_modal(producto):
        from componente_producto import ProductoModal
        modal = ProductoModal(db_manager=db_manager, producto=producto,
                              on_guardado=lambda: cargar_productos(), page=page)
        abrir_dialogo(page, modal)

    def nuevo_producto(e): _abrir_modal(None)
    def editar_producto(p): _abrir_modal(p)

    def configurar_tienda(p):
        from componente_tienda_producto import ProductoTiendaModal
        abrir_dialogo(page, ProductoTiendaModal(db_manager, p, page,
                                                on_guardado=lambda: cargar_productos()))

    def ver_historial(p):
        from componente_movimientos_stock import MovimientosStockModal
        abrir_dialogo(page, MovimientosStockModal(db_manager, p, page))

    def abrir_proveedores(e=None):
        from componente_proveedores import ProveedoresModal
        modal = ProveedoresModal(db_manager, page, on_cerrar=lambda: cargar_productos())
        abrir_dialogo(page, modal)

    def abrir_reponer(e=None):
        from componente_reponer import ReponerModal
        modal = ReponerModal(db_manager=db_manager, page=page,
                             on_creada=lambda: cargar_productos())
        abrir_dialogo(page, modal)

    # ---- Excel ----
    async def importar_excel(e):
        try:
            ruta = await pick_file(page, title="Seleccionar Excel",
                                   extensions=["xlsx", "xls"])
            if not ruta:
                return
            imp, omi, errores = await asyncio.to_thread(
                excel_service.importar, ruta, db_manager)
            msg = f"Importados {imp} · omitidos {omi}"
            if errores:
                msg += " · " + " | ".join(errores[:3])
            snack(page, msg, ok=imp > 0)
            cargar_productos()
        except Exception as ex:  # noqa: BLE001
            snack(page, f"Error al importar: {ex}", ok=False)

    async def exportar_excel(e):
        try:
            destino = await save_file(
                page, title="Guardar catálogo",
                file_name=f"productos_{datetime.now():%Y%m%d_%H%M%S}.xlsx",
                extensions=["xlsx"])
            if not destino:
                return
            ruta = await asyncio.to_thread(
                excel_service.exportar, agregar_extension(destino, "xlsx"), db_manager)
            snack(page, f"Exportado: {ruta}", ok=True)
        except Exception as ex:  # noqa: BLE001
            snack(page, f"Error al exportar: {ex}", ok=False)

    def descargar_plantilla(e):
        try:
            import pandas as pd
            cols = ["codigo", "descripcion", "categoria", "marca",
                    "precio_lista", "precio_costo", "stock_inicial", "stock_minimo",
                    "proveedor"]
            ejemplo = [["7790001001234", "Cuaderno 84 hojas", "Libreria", "Rivadavia",
                        1500.0, 900.0, 50, 10, "Proveedor Ejemplo"]]
            p = Path("plantilla_productos.xlsx")
            pd.DataFrame(ejemplo, columns=cols).to_excel(p, index=False)
            snack(page, f"Plantilla: {p.resolve()}", ok=True)
        except Exception as ex:  # noqa: BLE001
            snack(page, f"Error: {ex}", ok=False)

    search_field.on_change = buscar_productos
    cargar_productos()

    botones_barra = [
        search_field, filtro_dropdown,
        ft.FilledButton("NUEVO PRODUCTO", icon=ft.Icons.ADD_CIRCLE,
                        on_click=nuevo_producto, style=BTN_PRIMARIO,
                        height=45),
    ]
    if puede("PROVEEDORES"):
        botones_barra.append(ft.OutlinedButton(
            "PROVEEDORES", icon=ft.Icons.LOCAL_SHIPPING,
            on_click=abrir_proveedores, height=45))
    if puede("COMPRAS"):
        botones_barra.append(ft.FilledButton(
            "REPONER", icon=ft.Icons.SHOPPING_CART,
            on_click=abrir_reponer, height=45,
            style=ft.ButtonStyle(bgcolor=N.ORANGE_800,
                                 color=ft.Colors.WHITE)))

    barra_busqueda = ft.Container(
        content=ft.Column([
            ft.Row(botones_barra, spacing=10, wrap=True,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ], spacing=6),
        padding=12, border_radius=8,
        border=ft.Border.all(1, ft.Colors.with_opacity(0.35, N.BLUE_GREY_700)),
        bgcolor=ft.Colors.with_opacity(0.04, ft.Colors.WHITE),
    )

    return ft.Container(
        content=ft.Column([
            ft.Container(content=ft.Text("GESTIÓN DE ARTÍCULOS", size=20,
                                         weight=ft.FontWeight.BOLD),
                         bgcolor=N.BLUE_900, padding=8,
                         alignment=ft.Alignment.CENTER),
            ft.Container(height=10),
            barra_busqueda,
            ft.Container(height=8),
            ft.Container(
                content=ft.Column([
                    ft.Row([contador_text, ft.Container(expand=True)]),
                    ft.Column([productos_table], scroll=ft.ScrollMode.AUTO,
                              expand=True),
                ], spacing=4, expand=True),
                expand=True, border=ft.Border.all(1, N.BLUE_GREY_700),
                border_radius=6, padding=10),
            ft.Container(height=8),
            ft.Container(
                content=ft.Row([
                    ft.FilledButton("IMPORTAR EXCEL", icon=ft.Icons.UPLOAD_FILE,
                                    on_click=importar_excel,
                                    style=ft.ButtonStyle(bgcolor=N.BLUE_700,
                                                         color=ft.Colors.WHITE)),
                    ft.FilledButton("EXPORTAR EXCEL", icon=ft.Icons.DOWNLOAD,
                                    on_click=exportar_excel),
                    ft.OutlinedButton("PLANTILLA", icon=ft.Icons.TABLE_VIEW,
                                      on_click=descargar_plantilla),
                    ft.FilledButton("VOLVER", icon=ft.Icons.ARROW_BACK,
                                    on_click=lambda _: on_volver()),
                ], alignment=ft.MainAxisAlignment.CENTER, spacing=10, wrap=True),
                padding=10, border_radius=8,
                border=ft.Border.all(1, ft.Colors.with_opacity(
                    0.35, N.BLUE_GREY_700)),
                bgcolor=ft.Colors.with_opacity(0.04, ft.Colors.WHITE),
            ),
            ft.Text("Excel: codigo, descripcion, precio_lista (obligatorias). "
                    "Opcionales: categoria, marca, precio_costo, stock_inicial, "
                    "stock_minimo, proveedor.",
                    size=11, italic=True, color=N.GREY_500,
                    text_align=ft.TextAlign.CENTER),
        ], expand=True),
        padding=20, expand=True,
    )

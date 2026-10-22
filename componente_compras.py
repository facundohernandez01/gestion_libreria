"""Compras: órdenes de reposición, recepciones (parciales) y Excel.

UI responsive: filtros en un contenedor propio, tabla a todo el ancho y
recepción de mercadería ítem por ítem con historial.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import flet as ft

from services.compra_service import exportar_orden_excel, exportar_ordenes_excel
from ui.helpers import abrir_dialogo, cerrar_dialogo, snack
from ui.theme import BTN_PRIMARIO
from utils.file_dialogs import agregar_extension, save_file

ESTADOS = {
    "en_proceso": ("EN PROCESO", ft.Colors.ORANGE_400),
    "parcial": ("PARCIAL", ft.Colors.AMBER_400),
    "confirmada": ("CONFIRMADA", ft.Colors.GREEN_400),
    "cancelada": ("CANCELADA", ft.Colors.RED_400),
}

COLUMNAS = [
    ("N°", "numero"), ("Fecha", "fecha"), ("Usuario", "usuario"),
    ("Estado", "estado"), ("Proveedores", "proveedores"), ("Ítems", "items"),
    ("Pedido", "unidades"), ("Recibido", "recibidas"), ("Pend.", "pendientes"),
    ("Total", "total"), ("Acciones", None),
]


def _fmt_fecha(d: datetime) -> str:
    return d.strftime("%d/%m/%Y")


def _iso(valor: str) -> str:
    try:
        return datetime.strptime((valor or "").strip(), "%d/%m/%Y").strftime("%Y-%m-%d")
    except ValueError:
        return ""


def ComprasView(db_manager, on_volver, page: ft.Page):
    hoy = datetime.now()
    orden_state = {"campo": "fecha", "asc": False}

    filtro = ft.Dropdown(
        width=170, value="todas", label="Estado", dense=True,
        options=[ft.dropdown.Option("todas", "Todas"),
                 ft.dropdown.Option("en_proceso", "En proceso"),
                 ft.dropdown.Option("parcial", "Parciales"),
                 ft.dropdown.Option("confirmada", "Confirmadas"),
                 ft.dropdown.Option("cancelada", "Canceladas")],
    )
    proveedor_field = ft.TextField(
        label="Proveedor", width=220, dense=True,
        prefix_icon=ft.Icons.LOCAL_SHIPPING,
        hint_text="Filtrar por proveedor…")
    desde_field = ft.TextField(label="Desde", width=135, dense=True,
                               read_only=True, prefix_icon=ft.Icons.CALENDAR_TODAY)
    hasta_field = ft.TextField(label="Hasta", width=135, dense=True,
                               read_only=True, prefix_icon=ft.Icons.CALENDAR_TODAY)
    desde_dp = ft.DatePicker(first_date=hoy - timedelta(days=365 * 5),
                             last_date=hoy + timedelta(days=365))
    hasta_dp = ft.DatePicker(first_date=hoy - timedelta(days=365 * 5),
                             last_date=hoy + timedelta(days=365))
    resumen_text = ft.Text("", size=12, color=ft.Colors.GREY_400)

    def _elegir(dp, campo):
        try:
            page.overlay.append(dp)
            dp.open = True
            page.update()
        except Exception:
            pass

    def _set_fecha(dp, campo):
        if dp.value:
            campo.value = _fmt_fecha(dp.value)
            cargar()

    desde_dp.on_change = lambda _e: _set_fecha(desde_dp, desde_field)
    hasta_dp.on_change = lambda _e: _set_fecha(hasta_dp, hasta_field)
    desde_field.on_click = lambda _e: _elegir(desde_dp, desde_field)
    hasta_field.on_click = lambda _e: _elegir(hasta_dp, hasta_field)

    def _sort_handler(campo):
        def _handler(_e):
            if orden_state["campo"] == campo:
                orden_state["asc"] = not orden_state["asc"]
            else:
                orden_state["campo"] = campo
                orden_state["asc"] = True
            tabla.sort_column_index = next(
                i for i, (_t, c) in enumerate(COLUMNAS) if c == campo)
            tabla.sort_ascending = orden_state["asc"]
            cargar()
        return _handler

    tabla = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text(titulo, size=12), on_sort=_sort_handler(campo))
            if campo else ft.DataColumn(ft.Text(titulo, size=12))
            for titulo, campo in COLUMNAS
        ],
        rows=[], column_spacing=14, heading_row_height=36,
        data_row_min_height=42, data_row_max_height=52,
        sort_column_index=1, sort_ascending=False,
    )

    def _estado_actual():
        return None if filtro.value == "todas" else filtro.value

    def _badge(estado: str):
        texto, color = ESTADOS.get(estado, (estado.upper(), ft.Colors.GREY_400))
        return ft.Container(
            content=ft.Text(texto, size=10, color=ft.Colors.WHITE,
                            weight=ft.FontWeight.BOLD),
            bgcolor=ft.Colors.with_opacity(0.25, color), padding=5, border_radius=4,
        )

    def _filtrar():
        return db_manager.listar_ordenes_compra(
            _estado_actual(), proveedor=proveedor_field.value or "",
            desde=_iso(desde_field.value), hasta=_iso(hasta_field.value),
            ordenar=orden_state["campo"], ascendente=orden_state["asc"])

    def cargar(e=None):
        ordenes = _filtrar()
        tabla.rows.clear()
        total = 0.0
        for o in ordenes:
            total += float(o.get("total") or 0)
            pendientes = int(o.get("pendientes") or 0)
            en_proceso = o.get("estado") == "en_proceso"
            abierta = o.get("estado") in ("en_proceso", "parcial")
            acciones = [ft.IconButton(
                icon=ft.Icons.VISIBILITY, icon_color=ft.Colors.BLUE_400,
                tooltip="Ver detalle",
                on_click=lambda _e, orden=o: ver_orden(orden))]
            if pendientes > 0 and abierta:
                acciones.append(ft.IconButton(
                    icon=ft.Icons.INVENTORY, icon_color=ft.Colors.AMBER_400,
                    tooltip="Recepcionar mercadería",
                    on_click=lambda _e, orden=o: abrir_recepcion(orden)))
            if en_proceso:
                acciones.append(ft.IconButton(
                    icon=ft.Icons.EDIT, icon_color=ft.Colors.CYAN_400,
                    tooltip="Editar",
                    on_click=lambda _e, orden=o: editar_orden(orden)))
            if abierta:
                acciones.append(ft.IconButton(
                    icon=ft.Icons.CANCEL, icon_color=ft.Colors.RED_400,
                    tooltip="Cancelar",
                    on_click=lambda _e, orden=o: preguntar_cancelar(orden)))
            acciones.append(ft.IconButton(
                icon=ft.Icons.DOWNLOAD, icon_color=ft.Colors.GREY_300,
                tooltip="Exportar Excel",
                on_click=_exportar_cb(o)))
            tabla.rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(f"#{o['id']}", size=12,
                                    weight=ft.FontWeight.BOLD)),
                ft.DataCell(ft.Text(str(o.get("fecha_creacion") or "")[:16], size=11)),
                ft.DataCell(ft.Text(o.get("usuario") or "—", size=11,
                                    color=ft.Colors.CYAN_300)),
                ft.DataCell(_badge(o.get("estado") or "")),
                ft.DataCell(ft.Text(o.get("proveedores") or "—", size=11)),
                ft.DataCell(ft.Text(str(o.get("items_count") or 0), size=11)),
                ft.DataCell(ft.Text(str(o.get("unidades") or 0), size=11)),
                ft.DataCell(ft.Text(str(o.get("unidades_recibidas") or 0), size=11,
                                    color=ft.Colors.GREEN_300)),
                ft.DataCell(ft.Text(str(pendientes), size=11,
                                    color=ft.Colors.AMBER_300 if pendientes else
                                    ft.Colors.GREY_500,
                                    weight=ft.FontWeight.BOLD if pendientes else None)),
                ft.DataCell(ft.Text(f"${float(o.get('total') or 0):,.2f}", size=11)),
                ft.DataCell(ft.Row(acciones, spacing=0)),
            ]))
        if not ordenes:
            tabla.rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text("No hay órdenes para este filtro", italic=True,
                                    color=ft.Colors.GREY_500, size=11)),
                *[ft.DataCell(ft.Text("")) for _ in range(len(COLUMNAS) - 1)],
            ]))
        resumen_text.value = (f"{len(ordenes)} orden(es) · total ${total:,.2f}")
        page.update()

    # ---------- acciones ----------
    def preguntar(titulo: str, mensaje: str, accion, color=ft.Colors.GREEN_700):
        def _ok(_e):
            cerrar_dialogo(page)
            accion()

        abrir_dialogo(page, ft.AlertDialog(
            modal=True,
            title=ft.Text(titulo),
            content=ft.Text(mensaje),
            actions=[
                ft.TextButton("CANCELAR", on_click=lambda _e: cerrar_dialogo(page)),
                ft.FilledButton("CONFIRMAR", on_click=_ok,
                                style=ft.ButtonStyle(bgcolor=color,
                                                     color=ft.Colors.WHITE)),
            ],
        ))

    def preguntar_cancelar(o):
        preguntar(
            f"Cancelar orden #{o['id']}",
            "La orden quedará cancelada y no modificará el stock. "
            "Las unidades ya recibidas se conservan.",
            lambda: _cancelar(o), color=ft.Colors.RED_700,
        )

    def _cancelar(o):
        ok = db_manager.cancelar_orden_compra(int(o["id"]))
        snack(page, "Orden cancelada" if ok else "No se pudo cancelar", ok=ok)
        cargar()

    def _cerrar_dialogo(dlg):
        try:
            dlg.open = False
            page.update()
        except Exception:
            cerrar_dialogo(page)

    def ver_orden(o):
        detalle = db_manager.obtener_orden_compra(int(o["id"]))
        if not detalle:
            snack(page, "No se encontró la orden", ok=False)
            return
        items = detalle.get("items") or []
        filas = []
        for it in items:
            pendiente = int(it.get("cantidad_pendiente") or 0)
            filas.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(it.get("producto_codigo") or "", size=11)),
                ft.DataCell(ft.Text(it.get("producto_nombre") or "", size=11)),
                ft.DataCell(ft.Text(it.get("proveedor_nombre") or "—", size=11)),
                ft.DataCell(ft.Text(str(it.get("cantidad") or 0), size=11)),
                ft.DataCell(ft.Text(str(it.get("cantidad_recibida") or 0), size=11,
                                    color=ft.Colors.GREEN_300)),
                ft.DataCell(ft.Text(str(pendiente), size=11,
                                    color=ft.Colors.AMBER_300 if pendiente else
                                    ft.Colors.GREY_500)),
                ft.DataCell(ft.Text(f"${float(it.get('precio_costo') or 0):.2f}",
                                    size=11)),
                ft.DataCell(ft.Text(f"${float(it.get('subtotal') or 0):.2f}",
                                    size=11)),
            ]))
        detalle_tabla = ft.DataTable(
            columns=[ft.DataColumn(ft.Text("Código")),
                     ft.DataColumn(ft.Text("Descripción")),
                     ft.DataColumn(ft.Text("Proveedor")),
                     ft.DataColumn(ft.Text("Pedido")),
                     ft.DataColumn(ft.Text("Recibido")),
                     ft.DataColumn(ft.Text("Pend.")),
                     ft.DataColumn(ft.Text("Costo")),
                     ft.DataColumn(ft.Text("Subtotal"))],
            rows=filas, column_spacing=12, heading_row_height=32,
        )
        total = sum(float(it.get("subtotal") or 0) for it in items)
        detalle_dialog = {"ctrl": None}

        def _cerrar_detalle():
            _cerrar_dialogo(detalle_dialog["ctrl"])

        def _editar_desde_detalle():
            _cerrar_detalle()
            editar_orden(detalle)

        def _recepcionar_desde_detalle():
            _cerrar_detalle()
            abrir_recepcion(detalle)

        pendientes = int(detalle.get("pendientes") or 0)
        acciones = [ft.TextButton("CERRAR", on_click=lambda _e: _cerrar_detalle())]
        if detalle.get("estado") == "en_proceso":
            acciones.append(ft.FilledButton(
                "EDITAR", icon=ft.Icons.EDIT,
                on_click=lambda _e: _editar_desde_detalle(),
                style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700,
                                     color=ft.Colors.WHITE)))
        if pendientes > 0 and detalle.get("estado") in ("en_proceso", "parcial"):
            acciones.append(ft.FilledButton(
                "RECEPCIONAR", icon=ft.Icons.INVENTORY,
                on_click=lambda _e: _recepcionar_desde_detalle(),
                style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN_700,
                                     color=ft.Colors.WHITE)))

        historial = detalle.get("recepciones") or []
        historial_controles: list = []
        if historial:
            historial_controles.append(ft.Divider(height=8))
            historial_controles.append(ft.Text(
                "HISTORIAL DE RECEPCIONES", size=11, weight=ft.FontWeight.BOLD,
                color=ft.Colors.AMBER_300))
            for rec in historial:
                detalle_items = ", ".join(
                    f"{i['producto_codigo'] or i['producto_nombre']} x{i['cantidad']}"
                    for i in rec.get("items") or []) or "Sin unidades (se canceló el resto)"
                historial_controles.append(ft.Container(
                    content=ft.Column([
                        ft.Row([
                            ft.Icon(ft.Icons.INVENTORY_2, size=14,
                                    color=ft.Colors.GREEN_300),
                            ft.Text(str(rec.get("fecha") or "")[:19], size=11,
                                    weight=ft.FontWeight.BOLD),
                            ft.Text(f"Remito: {rec.get('remito') or '—'}", size=11,
                                    color=ft.Colors.GREY_400),
                            ft.Text(f"Usuario: {rec.get('usuario') or '—'}", size=11,
                                    color=ft.Colors.CYAN_300),
                            ft.Container(expand=True),
                            ft.Text("CANCELÓ RESTANTE", size=9,
                                    color=ft.Colors.RED_300, visible=
                                    bool(rec.get("cancelo_restante"))),
                        ], spacing=8),
                        ft.Text(detalle_items, size=10, color=ft.Colors.GREY_400),
                    ], spacing=2),
                    padding=7, border_radius=5,
                    bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.WHITE),
                ))

        detalle_dialog["ctrl"] = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"Orden de compra #{detalle['id']}"),
            content=ft.Container(
                content=ft.Column([
                    ft.Row([_badge(detalle.get("estado") or ""),
                            ft.Text(f"Creada: {str(detalle.get('fecha_creacion') or '')[:19]}",
                                    size=11, color=ft.Colors.GREY_400),
                            ft.Text(f"Usuario: {detalle.get('usuario') or '—'}",
                                    size=11, color=ft.Colors.CYAN_300),
                            ft.Text(f"Confirmada: {str(detalle.get('fecha_confirmacion') or '—')[:19]}",
                                    size=11, color=ft.Colors.GREY_400)]),
                    ft.Text(f"Observaciones: {detalle.get('observaciones') or '—'}",
                            size=11, color=ft.Colors.GREY_300),
                    ft.Divider(height=8),
                    ft.Column([detalle_tabla], scroll=ft.ScrollMode.AUTO),
                    ft.Row([
                        ft.Text(f"Pendiente: {pendientes} unid.", size=12,
                                color=ft.Colors.AMBER_300),
                        ft.Container(expand=True),
                        ft.Text(f"TOTAL: ${total:,.2f}", size=16,
                                weight=ft.FontWeight.BOLD,
                                color=ft.Colors.GREEN_300)]),
                    *historial_controles,
                ], spacing=8, scroll=ft.ScrollMode.AUTO),
                width=860, height=500,
            ),
            actions=acciones,
            actions_alignment=ft.MainAxisAlignment.END,
        )
        abrir_dialogo(page, detalle_dialog["ctrl"])

    def abrir_recepcion(o):
        from componente_recepcion import abrir_recepcion_compra
        abrir_recepcion_compra(db_manager, page, o, on_done=cargar)

    def editar_orden(o):
        detalle = db_manager.obtener_orden_compra(int(o["id"]))
        if not detalle:
            snack(page, "No se encontró la orden", ok=False)
            return
        from componente_reponer import ReponerModal
        abrir_dialogo(page, ReponerModal(
            db_manager=db_manager, page=page, on_creada=cargar, orden=detalle))

    def nueva_orden(e=None):
        from componente_reponer import ReponerModal
        abrir_dialogo(page, ReponerModal(db_manager=db_manager, page=page,
                                         on_creada=cargar))

    def _exportar_cb(orden):
        async def _handler(_e=None):
            await _exportar(orden)
        return _handler

    async def _exportar(orden):
        try:
            destino = await save_file(
                page, title="Guardar orden de compra",
                file_name=f"orden_compra_{orden['id']}_{datetime.now():%Y%m%d_%H%M%S}.xlsx",
                extensions=["xlsx"])
            if not destino:
                return
            ruta = await asyncio.to_thread(
                exportar_orden_excel, db_manager, int(orden["id"]),
                agregar_extension(destino, "xlsx"))
            snack(page, f"Exportado: {ruta}", ok=True)
        except Exception as ex:  # noqa: BLE001
            snack(page, f"Error al exportar: {ex}", ok=False)

    async def exportar_listado(e=None):
        try:
            ordenes = _filtrar()
            if not ordenes:
                snack(page, "No hay órdenes para exportar", ok=False)
                return
            destino = await save_file(
                page, title="Guardar listado de órdenes",
                file_name=f"ordenes_compra_{datetime.now():%Y%m%d_%H%M%S}.xlsx",
                extensions=["xlsx"])
            if not destino:
                return
            ruta = await asyncio.to_thread(
                exportar_ordenes_excel, db_manager, ordenes,
                agregar_extension(destino, "xlsx"))
            snack(page, f"Exportado: {ruta}", ok=True)
        except Exception as ex:  # noqa: BLE001
            snack(page, f"Error al exportar: {ex}", ok=False)

    filtro.on_change = cargar
    proveedor_field.on_change = cargar
    cargar()

    contenedor_filtros = ft.Container(
        content=ft.Column([
            ft.Row([filtro, proveedor_field, desde_field, hasta_field],
                   spacing=10, wrap=True,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Row([
                resumen_text,
                ft.Container(expand=True),
                ft.FilledButton("NUEVA ORDEN", icon=ft.Icons.ADD,
                                on_click=nueva_orden, style=BTN_PRIMARIO, height=40),
                ft.OutlinedButton("EXPORTAR LISTADO", icon=ft.Icons.TABLE_VIEW,
                                  on_click=exportar_listado, height=40),
                ft.OutlinedButton("VOLVER", icon=ft.Icons.ARROW_BACK,
                                  on_click=lambda _e: on_volver(), height=40),
            ], spacing=10,
               vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ], spacing=8),
        padding=12, border_radius=8,
        border=ft.Border.all(1, ft.Colors.with_opacity(0.35, ft.Colors.BLUE_GREY_700)),
        bgcolor=ft.Colors.with_opacity(0.04, ft.Colors.WHITE),
    )

    return ft.Container(
        content=ft.Column([
            ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.SHOPPING_CART, size=24,
                            color=ft.Colors.ORANGE_300),
                    ft.Text("COMPRAS — ÓRDENES DE REPOSICIÓN", size=20,
                            weight=ft.FontWeight.BOLD),
                ], alignment=ft.MainAxisAlignment.CENTER, spacing=10),
                bgcolor=ft.Colors.BLUE_900, padding=8, alignment=ft.Alignment.CENTER),
            ft.Container(height=10),
            contenedor_filtros,
            ft.Container(height=8),
            ft.Container(
                content=ft.Column([
                    ft.Row([tabla], scroll=ft.ScrollMode.AUTO,
                           vertical_alignment=ft.CrossAxisAlignment.START),
                ], scroll=ft.ScrollMode.AUTO),
                expand=True, border=ft.Border.all(1, ft.Colors.BLUE_GREY_700),
                border_radius=6, padding=10),
            ft.Container(height=6),
            ft.Text("Al recepcionar podés ingresar cantidades parciales: la orden "
                    "queda «PARCIAL» y podés cancelar el resto o dejarlo pendiente. "
                    "Las órdenes confirmadas no se pueden editar.",
                    size=11, italic=True, color=ft.Colors.GREY_500),
        ], expand=True,
           horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
        padding=20, expand=True,
    )

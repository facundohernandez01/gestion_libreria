"""Trazabilidad de stock por producto (modal)."""
from __future__ import annotations

import flet as ft
from ui.paleta import N

from ui.helpers import cerrar_dialogo

COLORES_TIPO = {
    "venta": N.RED_400,
    "ingreso": N.GREEN_400,
    "ajuste": N.ORANGE_400,
    "devolucion": N.CYAN_400,
}
ETIQUETAS_TIPO = {
    "venta": "Venta",
    "ingreso": "Ingreso",
    "ajuste": "Ajuste",
    "devolucion": "Devolución",
}


def MovimientosStockModal(db_manager, producto: dict, page: ft.Page):
    movimientos = db_manager.obtener_movimientos_stock_detallado(producto["id"])
    resumen = db_manager.resumen_movimientos_producto(producto["id"]) or {}

    filtro = ft.Dropdown(
        label="Tipo", width=170, value="todos", dense=True,
        options=[ft.dropdown.Option("todos", "Todos"),
                 ft.dropdown.Option("venta", "Ventas"),
                 ft.dropdown.Option("ingreso", "Ingresos"),
                 ft.dropdown.Option("ajuste", "Ajustes"),
                 ft.dropdown.Option("devolucion", "Devoluciones")],
    )

    tabla = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Fecha")),
            ft.DataColumn(ft.Text("Tipo")),
            ft.DataColumn(ft.Text("Cant.")),
            ft.DataColumn(ft.Text("Antes")),
            ft.DataColumn(ft.Text("Después")),
            ft.DataColumn(ft.Text("Usuario")),
            ft.DataColumn(ft.Text("Referencia")),
            ft.DataColumn(ft.Text("Detalle")),
        ],
        rows=[], column_spacing=14, heading_row_height=34,
    )

    def _referencia(m: dict) -> str:
        tipo = m.get("tipo")
        ref = m.get("referencia_id")
        if tipo == "venta":
            extra = ""
            if m.get("venta_metodo_pago"):
                extra = f" · {m['venta_metodo_pago']}"
            return f"Venta #{ref}{extra}" if ref else "Venta"
        if tipo == "devolucion":
            return f"Venta #{ref}" if ref else "Devolución"
        if tipo == "ingreso" and ref:
            prov = m.get("orden_proveedores") or ""
            return f"Orden #{ref}" + (f" · {prov}" if prov and prov != "Sin proveedor" else "")
        return "—"

    def _detalle(m: dict) -> str:
        obs = (m.get("observaciones") or "").strip()
        if m.get("tipo") == "ingreso" and m.get("orden_estado"):
            estado = m["orden_estado"]
            if estado == "confirmada":
                obs = (obs + " · " if obs else "") + "Confirmada"
        return obs

    def _filas():
        tipo = filtro.value
        seleccion = [m for m in movimientos if tipo == "todos" or m.get("tipo") == tipo]
        tabla.rows.clear()
        for m in seleccion:
            fecha = str(m.get("fecha") or "")[:19]
            t = m.get("tipo") or ""
            color = COLORES_TIPO.get(t, N.GREY_400)
            tabla.rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(fecha, size=11)),
                ft.DataCell(ft.Container(
                    content=ft.Text(ETIQUETAS_TIPO.get(t, t), size=11,
                                    color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
                    bgcolor=ft.Colors.with_opacity(0.25, color), padding=4,
                    border_radius=4)),
                ft.DataCell(ft.Text(str(m.get("cantidad") or 0), size=11)),
                ft.DataCell(ft.Text(str(m.get("stock_anterior") or 0), size=11)),
                ft.DataCell(ft.Text(str(m.get("stock_nuevo") or 0), size=11,
                                    weight=ft.FontWeight.BOLD)),
                ft.DataCell(ft.Text(m.get("usuario") or "—", size=11,
                                    color=N.CYAN_300)),
                ft.DataCell(ft.Text(_referencia(m), size=11)),
                ft.DataCell(ft.Text(_detalle(m), size=11, color=N.GREY_400)),
            ]))
        if not seleccion:
            tabla.rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text("Sin movimientos para este filtro",
                                    italic=True, color=N.GREY_500, size=11)),
                *[ft.DataCell(ft.Text("")) for _ in range(7)],
            ]))
        page.update()

    def _card(titulo, valor, color):
        return ft.Container(
            content=ft.Column([
                ft.Text(titulo, size=10, color=N.GREY_400),
                ft.Text(str(valor), size=18, weight=ft.FontWeight.BOLD, color=color),
            ], spacing=1, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            width=120, padding=8, border_radius=6,
            bgcolor=ft.Colors.with_opacity(0.08, color),
        )

    filtro.on_change = lambda _e: _filas()
    _filas()

    return ft.AlertDialog(
        modal=True,
        title=ft.Row([
            ft.Icon(ft.Icons.HISTORY, color=N.BLUE_400),
            ft.Column([
                ft.Text(f"Movimientos — {producto['codigo']}", size=16,
                        weight=ft.FontWeight.BOLD),
                ft.Text(producto.get("descripcion") or "", size=11,
                        color=N.GREY_500),
            ], spacing=0),
        ], spacing=10),
        content=ft.Container(
            content=ft.Column([
                ft.Row([
                    _card("Stock actual", producto.get("stock_actual", 0),
                          N.BLUE_300),
                    _card("Ingresos", resumen.get("ingresos", 0), N.GREEN_400),
                    _card("Ventas", resumen.get("ventas", 0), N.RED_400),
                    _card("Ajuste neto", resumen.get("ajuste_neto", 0),
                          N.ORANGE_400),
                    _card("Devoluciones", resumen.get("devoluciones", 0),
                          N.CYAN_400),
                ], spacing=8, wrap=True),
                ft.Row([filtro], alignment=ft.MainAxisAlignment.END),
                ft.Container(content=ft.Column([tabla], scroll=ft.ScrollMode.AUTO),
                             height=330, border=ft.Border.all(1, N.BLUE_GREY_700),
                             border_radius=6, padding=8),
            ], spacing=10, scroll=ft.ScrollMode.AUTO),
            width=820, height=470,
        ),
        actions=[ft.TextButton("CERRAR", on_click=lambda _e: cerrar_dialogo(page))],
        actions_alignment=ft.MainAxisAlignment.END,
        open=True,
    )

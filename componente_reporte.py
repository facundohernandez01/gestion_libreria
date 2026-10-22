"""Modal de reportes de ventas.

- Filtro por rango de fechas (DatePicker) + atajos (Hoy, 7 días, Mes).
- Tab Resumen: tarjetas + ventas por día + detalle.
- Tab Productos: ranking de más vendidos (cantidad, nº ventas, monto).
- Tab Gráficos: exporta/abre HTML autocontenido con Apache ECharts.
"""
from datetime import datetime, timedelta

import flet as ft

from services.report_service import rango_iso, report_service
from ui.helpers import abrir_dialogo, cerrar_dialogo, snack


def _fmt_fecha(d: datetime) -> str:
    return d.strftime("%d/%m/%Y")


def mostrar_reporte_ventas(page: ft.Page, db_manager):
    hoy = datetime.now()
    desde_field = ft.TextField(label="Desde", value=_fmt_fecha(hoy), width=150,
                               read_only=True, prefix_icon=ft.Icons.CALENDAR_TODAY)
    hasta_field = ft.TextField(label="Hasta", value=_fmt_fecha(hoy), width=150,
                               read_only=True, prefix_icon=ft.Icons.CALENDAR_TODAY)

    desde_dp = ft.DatePicker(first_date=hoy - timedelta(days=365 * 3), last_date=hoy + timedelta(days=365))
    hasta_dp = ft.DatePicker(first_date=hoy - timedelta(days=365 * 3), last_date=hoy + timedelta(days=365))

    def _elegir(desde=True):
        dp = desde_dp if desde else hasta_dp
        try:
            page.overlay.append(dp)
            dp.open = True
            page.update()
        except Exception:
            pass

    def _on_change(dp, campo):
        def cb(e):
            if dp.value:
                campo.value = _fmt_fecha(dp.value)
                page.update()

        return cb

    desde_dp.on_change = _on_change(desde_dp, desde_field)
    hasta_dp.on_change = _on_change(hasta_dp, hasta_field)

    desde_field.on_click = lambda _: _elegir(True)
    hasta_field.on_click = lambda _: _elegir(False)

    # tarjetas resumen
    card_ventas = ft.Text("0", size=26, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_400)
    card_total = ft.Text("$0.00", size=26, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_400)
    card_promedio = ft.Text("$0.00", size=26, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_400)
    estado_text = ft.Text("Seleccione un rango de fechas y presione Filtrar",
                          size=12, italic=True, color=ft.Colors.GREY_500)

    ventas_tabla = ft.DataTable(
        columns=[ft.DataColumn(ft.Text("ID")), ft.DataColumn(ft.Text("Fecha")),
                 ft.DataColumn(ft.Text("Total")), ft.DataColumn(ft.Text("Medio")),
                 ft.DataColumn(ft.Text("Items"))],
        rows=[],
    )
    dia_tabla = ft.DataTable(
        columns=[ft.DataColumn(ft.Text("Día")), ft.DataColumn(ft.Text("Ventas")),
                 ft.DataColumn(ft.Text("Total"))],
        rows=[],
    )
    top_tabla = ft.DataTable(
        columns=[ft.DataColumn(ft.Text("#")), ft.DataColumn(ft.Text("Producto")),
                 ft.DataColumn(ft.Text("Cantidad")), ft.DataColumn(ft.Text("Nº ventas")),
                 ft.DataColumn(ft.Text("Monto"))],
        rows=[],
    )

    state: dict = {"ventas": [], "detalle": [], "top": [], "por_dia": [], "resumen": (0, 0.0)}

    def _cargar():
        try:
            desde_iso, hasta_iso = rango_iso(desde_field.value or "", hasta_field.value or "")
        except ValueError as ex:
            snack(page, str(ex), ok=False)
            return
        ventas = db_manager.obtener_ventas_por_fechas(desde_iso, hasta_iso)
        detalle = db_manager.obtener_detalle_ventas(desde_iso, hasta_iso)
        top = db_manager.obtener_top_productos(desde_iso, hasta_iso, 15)
        por_dia = db_manager.obtener_ventas_por_dia(desde_iso, hasta_iso)
        n, total = report_service.resumen(ventas)
        state.update(ventas=ventas, detalle=detalle, top=top, por_dia=por_dia, resumen=(n, total))

        card_ventas.value = str(n)
        card_total.value = f"${total:,.2f}"
        card_promedio.value = f"${(total / n if n else 0):,.2f}"
        estado_text.value = f"{n} ventas completadas entre {desde_field.value} y {hasta_field.value}"
        estado_text.color = ft.Colors.GREEN_400

        ventas_tabla.rows.clear()
        for v in ventas:
            ventas_tabla.rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(str(v["id"]), size=12)),
                ft.DataCell(ft.Text(str(v.get("fecha", ""))[:16], size=12)),
                ft.DataCell(ft.Text(f"${v.get('total', 0):,.2f}", size=12)),
                ft.DataCell(ft.Text(v.get("metodo_pago", ""), size=12)),
                ft.DataCell(ft.Text(str(v.get("items_count", 0)), size=12)),
            ]))
        dia_tabla.rows.clear()
        for d in por_dia:
            dia_tabla.rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(str(d.get("dia", "")), size=12)),
                ft.DataCell(ft.Text(str(d.get("cantidad", 0)), size=12)),
                ft.DataCell(ft.Text(f"${float(d.get('total', 0)):,.2f}", size=12)),
            ]))
        top_tabla.rows.clear()
        for i, p in enumerate(top):
            top_tabla.rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(str(i + 1), size=12)),
                ft.DataCell(ft.Text(str(p.get("descripcion", ""))[:40], size=12)),
                ft.DataCell(ft.Text(str(int(p.get("cantidad_total", 0))), size=12)),
                ft.DataCell(ft.Text(str(int(p.get("num_ventas", 0))), size=12)),
                ft.DataCell(ft.Text(f"${float(p.get('monto_total', 0)):,.2f}", size=12)),
            ]))
        page.update()

    def _rango_rapido(dias):
        h = hoy
        d = hoy - timedelta(days=dias)
        desde_field.value = _fmt_fecha(d)
        hasta_field.value = _fmt_fecha(h)
        _cargar()

    def _exportar_html(abrir=False):
        if not state["detalle"]:
            snack(page, "No hay datos para exportar (filtre primero)", ok=False)
            return None
        try:
            ruta = report_service.exportar_html(
                state["detalle"], state["top"], state["por_dia"], state["resumen"], abrir=abrir)
            snack(page, f"HTML generado: {ruta}", ok=True)
            return ruta
        except Exception as ex:  # noqa: BLE001
            snack(page, f"Error al exportar: {ex}", ok=False)
            return None

    # ---------- tabs ----------
    def _tab_content(controls):
        return ft.Container(
            content=ft.Column(controls, spacing=10, scroll=ft.ScrollMode.AUTO, expand=True),
            padding=4,
        )

    resumen_tab = _tab_content([
        ft.Row([
            ft.Container(content=ft.Column([ft.Text("VENTAS", size=11, color=ft.Colors.GREY_500), card_ventas]),
                         bgcolor=ft.Colors.BLUE_GREY_900, padding=12, border_radius=8),
            ft.Container(content=ft.Column([ft.Text("TOTAL", size=11, color=ft.Colors.GREY_500), card_total]),
                         bgcolor=ft.Colors.BLUE_GREY_900, padding=12, border_radius=8),
            ft.Container(content=ft.Column([ft.Text("PROMEDIO", size=11, color=ft.Colors.GREY_500), card_promedio]),
                         bgcolor=ft.Colors.BLUE_GREY_900, padding=12, border_radius=8),
        ], spacing=12),
        ft.Text("Ventas por día", size=13, weight=ft.FontWeight.BOLD),
        ft.Container(content=ft.Column([dia_tabla], scroll=ft.ScrollMode.AUTO),
                     border=ft.Border.all(1, ft.Colors.BLUE_GREY_700), border_radius=5,
                     padding=5, height=160),
        ft.Text("Detalle de ventas", size=13, weight=ft.FontWeight.BOLD),
        ft.Container(content=ft.Column([ventas_tabla], scroll=ft.ScrollMode.AUTO),
                     border=ft.Border.all(1, ft.Colors.BLUE_GREY_700), border_radius=5,
                     padding=5, height=240),
    ])
    top_tab = _tab_content([
        ft.Text("Productos más vendidos (top 15)", size=13, weight=ft.FontWeight.BOLD),
        ft.Container(content=ft.Column([top_tabla], scroll=ft.ScrollMode.AUTO),
                     border=ft.Border.all(1, ft.Colors.BLUE_GREY_700), border_radius=5,
                     padding=5, height=420),
    ])

    # ---------- stock ----------
    stock_filtro = ft.Dropdown(
        label="Filtro", width=220, value="todos", dense=True,
        options=[ft.dropdown.Option("todos", "Todos"),
                 ft.dropdown.Option("bajo", "Solo bajo mínimo / agotados"),
                 ft.dropdown.Option("agotado", "Agotados"),
                 ft.dropdown.Option("por_agotar", "Por agotar")])
    stock_orden = ft.Dropdown(
        label="Ordenar por", width=200, value="prioridad", dense=True,
        options=[ft.dropdown.Option("prioridad", "Prioridad de reposición"),
                 ft.dropdown.Option("stock_asc", "Stock (menor primero)"),
                 ft.dropdown.Option("descripcion", "Descripción"),
                 ft.dropdown.Option("proveedor", "Proveedor")])
    stock_resumen = ft.Text("", size=12, color=ft.Colors.GREY_400)
    stock_tabla = ft.DataTable(
        columns=[ft.DataColumn(ft.Text("Código")),
                 ft.DataColumn(ft.Text("Descripción")),
                 ft.DataColumn(ft.Text("Proveedor")),
                 ft.DataColumn(ft.Text("Stock")),
                 ft.DataColumn(ft.Text("Mínimo")),
                 ft.DataColumn(ft.Text("Estado"))],
        rows=[], column_spacing=18, heading_row_height=34,
    )
    stock_state = {"productos": [], "seleccion": []}
    ESTADOS_STOCK = {
        "agotado": ("AGOTADO", ft.Colors.RED_400),
        "bajo": ("BAJO MÍNIMO", ft.Colors.ORANGE_400),
        "por_agotar": ("POR AGOTAR", ft.Colors.YELLOW_400),
        "ok": ("OK", ft.Colors.GREEN_400),
    }

    def _stock_badge(estado: str):
        texto, color = ESTADOS_STOCK.get(estado, (estado, ft.Colors.GREY_400))
        return ft.Container(
            content=ft.Text(texto, size=10, color=ft.Colors.WHITE,
                            weight=ft.FontWeight.BOLD),
            bgcolor=ft.Colors.with_opacity(0.25, color), padding=4,
            border_radius=4,
        )

    def _cargar_stock(e=None):
        try:
            productos = db_manager.obtener_stock_productos()
        except Exception as ex:  # noqa: BLE001
            snack(page, f"No se pudo cargar el stock: {ex}", ok=False)
            return
        stock_state["productos"] = productos
        f = stock_filtro.value or "todos"
        if f == "bajo":
            seleccion = [p for p in productos if int(p.get("prioridad_stock", 3)) <= 1]
        elif f == "agotado":
            seleccion = [p for p in productos if int(p.get("prioridad_stock", 3)) == 0]
        elif f == "por_agotar":
            seleccion = [p for p in productos if int(p.get("prioridad_stock", 3)) == 2]
        else:
            seleccion = list(productos)

        o = stock_orden.value or "prioridad"
        if o == "stock_asc":
            seleccion.sort(key=lambda p: (int(p.get("stock_actual") or 0),
                                          str(p.get("descripcion") or "").lower()))
        elif o == "descripcion":
            seleccion.sort(key=lambda p: str(p.get("descripcion") or "").lower())
        elif o == "proveedor":
            seleccion.sort(key=lambda p: (str(p.get("proveedor_nombre") or "zzz").lower(),
                                          str(p.get("descripcion") or "").lower()))
        stock_state["seleccion"] = seleccion

        stock_tabla.rows.clear()
        for p in seleccion:
            estado = p.get("estado_stock") or "ok"
            color = ESTADOS_STOCK.get(estado, ("", ft.Colors.GREY_400))[1]
            stock_tabla.rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(p.get("codigo") or "", size=11)),
                ft.DataCell(ft.Text(str(p.get("descripcion") or "")[:48], size=11)),
                ft.DataCell(ft.Text(p.get("proveedor_nombre") or "—", size=11)),
                ft.DataCell(ft.Text(str(p.get("stock_actual") or 0), size=12,
                                    color=color, weight=ft.FontWeight.BOLD)),
                ft.DataCell(ft.Text(str(p.get("stock_minimo") or 0), size=11)),
                ft.DataCell(_stock_badge(estado)),
            ]))
        if not seleccion:
            stock_tabla.rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text("Sin productos para este filtro", italic=True,
                                    color=ft.Colors.GREY_500, size=11)),
                *[ft.DataCell(ft.Text("")) for _ in range(5)],
            ]))
        agotados = sum(1 for p in productos if int(p.get("prioridad_stock", 3)) == 0)
        bajos = sum(1 for p in productos if int(p.get("prioridad_stock", 3)) == 1)
        por_agotar = sum(1 for p in productos if int(p.get("prioridad_stock", 3)) == 2)
        stock_resumen.value = (
            f"{len(productos)} productos · {agotados} agotados · "
            f"{bajos} bajo mínimo · {por_agotar} por agotar")
        page.update()

    def _exportar_stock(e=None):
        if not stock_state["seleccion"]:
            snack(page, "No hay productos para exportar", ok=False)
            return
        try:
            ruta = report_service.exportar_stock_excel(stock_state["seleccion"])
            snack(page, f"Archivo exportado: {ruta}", ok=True)
        except Exception as ex:  # noqa: BLE001
            snack(page, f"Error al exportar: {ex}", ok=False)

    stock_filtro.on_change = _cargar_stock
    stock_orden.on_change = _cargar_stock
    stock_tab = _tab_content([
        ft.Text("Estado del stock", size=13, weight=ft.FontWeight.BOLD),
        ft.Row([stock_filtro, stock_orden, ft.Container(expand=True),
                ft.OutlinedButton("EXPORTAR STOCK", icon=ft.Icons.DOWNLOAD,
                                  on_click=_exportar_stock)], spacing=10),
        stock_resumen,
        ft.Container(content=ft.Column([stock_tabla], scroll=ft.ScrollMode.AUTO),
                     border=ft.Border.all(1, ft.Colors.BLUE_GREY_700), border_radius=5,
                     padding=5, height=380),
    ])

    graficos_tab = _tab_content([
        ft.Text("Gráficos y exportación", size=13, weight=ft.FontWeight.BOLD),
        ft.Text("Se genera un HTML autocontenido con gráficos Apache ECharts "
                "(barras y líneas) que puede abrirse en el navegador.",
                size=11, italic=True, color=ft.Colors.GREY_500),
        ft.FilledButton("📊 Ver gráficos en navegador", icon=ft.Icons.BAR_CHART,
                        on_click=lambda _: _exportar_html(abrir=True)),
        ft.FilledButton("💾 Exportar HTML", icon=ft.Icons.DOWNLOAD,
                        on_click=lambda _: _exportar_html(abrir=False)),
        ft.OutlinedButton("📄 Exportar Excel", icon=ft.Icons.GRID_ON,
                          on_click=lambda _: _exportar_excel()),
        ft.Text("", size=10),
    ])

    contenidos = [resumen_tab, top_tab, stock_tab, graficos_tab]
    etiquetas = ["📊 Resumen", "🏆 Productos", "📦 Stock", "📈 Gráficos"]
    botones_tab: list = []

    def _cambiar_tab(i):
        for j, b in enumerate(botones_tab):
            b.style = ft.ButtonStyle(
                bgcolor=ft.Colors.BLUE_700 if j == i else ft.Colors.GREY_800,
                color=ft.Colors.WHITE)
            b.icon = ft.Icons.CHECK if j == i else None
        contenedor_tabs.content.controls = [contenidos[i]]
        if i == 2:
            _cargar_stock()
        page.update()

    for i, label in enumerate(etiquetas):
        botones_tab.append(ft.FilledTonalButton(
            label, icon=(ft.Icons.CHECK if i == 0 else None),
            style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700 if i == 0 else ft.Colors.GREY_800,
                                 color=ft.Colors.WHITE),
            on_click=lambda e, i=i: _cambiar_tab(i)))
    contenedor_tabs = ft.Container(content=ft.Column([contenidos[0]], expand=True),
                                   height=440, expand=True)

    def _exportar_excel():
        if not state["detalle"]:
            snack(page, "No hay datos para exportar", ok=False)
            return
        try:
            ruta = report_service.exportar_excel(state["detalle"])
            snack(page, f"Archivo exportado: {ruta}", ok=True)
        except Exception as ex:  # noqa: BLE001
            snack(page, f"Error al exportar: {ex}", ok=False)

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Row([ft.Icon(ft.Icons.ASSESSMENT, color=ft.Colors.BLUE_400),
                      ft.Text("Reportes de Ventas", size=20, weight=ft.FontWeight.BOLD)]),
        content=ft.Container(
            content=ft.Column([
                ft.Row([
                    desde_field, hasta_field,
                    ft.FilledButton("Filtrar", icon=ft.Icons.SEARCH, on_click=lambda _: _cargar()),
                ], spacing=10, wrap=True),
                ft.Row([
                    ft.OutlinedButton("Hoy", on_click=lambda _: _rango_rapido(0)),
                    ft.OutlinedButton("7 días", on_click=lambda _: _rango_rapido(6)),
                    ft.OutlinedButton("30 días", on_click=lambda _: _rango_rapido(29)),
                    ft.OutlinedButton("Este mes", on_click=lambda _: _rango_rapido(hoy.day - 1)),
                ], spacing=8, wrap=True),
                estado_text,
                ft.Divider(height=8),
                ft.Row(botones_tab, spacing=6, wrap=True),
                contenedor_tabs,
            ], spacing=10),
            width=980,
        ),
        actions=[ft.TextButton("Cerrar", on_click=lambda _: cerrar_dialogo(page))],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    _cargar()
    _cargar_stock()
    abrir_dialogo(page, dialog)
    return dialog

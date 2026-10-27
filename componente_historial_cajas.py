"""Historial de cajas: apertura/cierre, totales y ventas de cada caja.

- Búsqueda por nro de caja y rango de fechas (DatePicker).
- Detalle con listado de ventas; si la venta tiene factura se puede ver el PDF
  o reimprimirlo desde el mismo diálogo.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import flet as ft
from ui.paleta import N

from ui.helpers import (abrir_archivo, abrir_dialogo, cerrar_dialogo,
                        imprimir_archivo, snack)

_ESTADOS = {
    "abierta": ("ABIERTA", N.GREEN_400),
    "cerrada": ("CERRADA", N.GREY_400),
}

_ANCHO_CONTENIDO = 940


def _fmt_fecha(d: datetime) -> str:
    return d.strftime("%d/%m/%Y")


def _iso(valor: str) -> str:
    try:
        return datetime.strptime((valor or "").strip(), "%d/%m/%Y").strftime("%Y-%m-%d")
    except ValueError:
        return ""


def _buscar_pdf(venta_id: int) -> Path | None:
    from core.settings import settings

    bases = [settings.tickets_path, "tickets"]
    for base in bases:
        carpeta = Path(base)
        if not carpeta.is_dir():
            continue
        pdfs = sorted(carpeta.glob(f"ticket_{venta_id}_*.pdf"),
                      key=lambda p: p.stat().st_mtime, reverse=True)
        if pdfs:
            return pdfs[0]
    return None


def _pdf_de_venta(db_manager, venta: dict) -> Path | None:
    """Devuelve el PDF del ticket; si no existe, lo regenera desde la venta."""
    pdf = _buscar_pdf(int(venta["id"]))
    if pdf:
        return pdf
    if not venta.get("numero_factura"):
        return None
    try:
        from facturacion_manager import FacturacionManager

        items = db_manager.obtener_items_venta(int(venta["id"]))
        carrito = [{
            "descripcion": i.get("producto_nombre") or "",
            "cantidad": int(i.get("cantidad") or 0),
            "precio_unitario": float(i.get("precio_unitario") or 0),
            "subtotal": float(i.get("subtotal") or 0),
        } for i in items]
        ruta = FacturacionManager(db_manager).generar_ticket_pdf(
            int(venta["id"]), carrito, venta.get("numero_factura"),
            venta.get("cae"), venta.get("vencimiento_cae"))
        return Path(ruta) if ruta else None
    except Exception:  # noqa: BLE001
        return None


def HistorialCajasView(db_manager, on_volver, page: ft.Page):
    hoy = datetime.now()
    busqueda_field = ft.TextField(
        label="Nro de caja o fecha", prefix_icon=ft.Icons.SEARCH, width=230,
        hint_text="Ej.: 12 o 2026-10-20")
    desde_field = ft.TextField(label="Desde", width=135, read_only=True,
                               prefix_icon=ft.Icons.CALENDAR_TODAY)
    hasta_field = ft.TextField(label="Hasta", width=135, read_only=True,
                               prefix_icon=ft.Icons.CALENDAR_TODAY)
    desde_dp = ft.DatePicker(first_date=hoy - timedelta(days=365 * 5),
                             last_date=hoy + timedelta(days=365))
    hasta_dp = ft.DatePicker(first_date=hoy - timedelta(days=365 * 5),
                             last_date=hoy + timedelta(days=365))
    resumen_text = ft.Text("", size=12, color=N.GREY_400)
    lista = ft.Column(spacing=6, scroll=ft.ScrollMode.AUTO)
    expandidas: set = set()

    def _badge(estado: str):
        texto, color = _ESTADOS.get(estado or "", (estado.upper(), N.GREY_400))
        return ft.Container(
            content=ft.Text(texto, size=10, color=ft.Colors.WHITE,
                            weight=ft.FontWeight.BOLD),
            bgcolor=ft.Colors.with_opacity(0.25, color), padding=5, border_radius=4,
        )

    def _elegir(dp):
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
    desde_field.on_click = lambda _e: _elegir(desde_dp)
    hasta_field.on_click = lambda _e: _elegir(hasta_dp)

    def _fila_caja(c: dict):
        apertura = str(c.get("fecha_apertura") or "")[:16]
        cierre = str(c.get("fecha_cierre") or "—")[:16]
        total_ventas = float(c.get("total_ventas") or 0)
        return ft.Container(
            content=ft.Row([
                ft.Text(f"#{c['id']}", size=14, weight=ft.FontWeight.BOLD,
                        color=N.BLUE_300, width=44),
                ft.Column([
                    ft.Text(f"Apertura: {apertura}", size=12),
                    ft.Text(f"Cierre: {cierre}", size=12, color=N.GREY_400),
                ], spacing=2, expand=True),
                ft.Column([
                    ft.Text("Usuario", size=10, color=N.GREY_500),
                    ft.Text(c.get("usuario_apertura") or "—", size=11,
                            color=N.CYAN_300),
                ], spacing=1, width=110),
                ft.Column([
                    ft.Text(f"Apertura ${float(c.get('importe_apertura') or 0):,.2f}",
                            size=11, color=N.GREY_400, text_align=ft.TextAlign.RIGHT),
                    ft.Text(f"Ventas ${total_ventas:,.2f}", size=12,
                            color=N.GREEN_300, weight=ft.FontWeight.BOLD,
                            text_align=ft.TextAlign.RIGHT),
                ], horizontal_alignment=ft.CrossAxisAlignment.END, spacing=2),
                _badge(c.get("estado") or ""),
                ft.Icon(ft.Icons.CHEVRON_RIGHT, color=N.GREY_500),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, spacing=8),
            padding=10, border_radius=6,
            bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.WHITE),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.3, N.BLUE_GREY_700)),
            on_click=lambda _e, cid=c["id"]: ver_caja(cid),
            ink=True,
        )

    def cargar(e=None):
        termino = (busqueda_field.value or "").strip()
        cajas = db_manager.listar_cajas(termino, _iso(desde_field.value),
                                        _iso(hasta_field.value))
        lista.controls.clear()
        for c in cajas:
            lista.controls.append(_fila_caja(c))
        if not cajas:
            lista.controls.append(ft.Text(
                "No se encontraron cajas para la búsqueda", italic=True,
                color=N.GREY_500))
        abiertas = sum(1 for c in cajas if c.get("estado") == "abierta")
        filtros = []
        if termino:
            filtros.append(f"«{termino}»")
        if desde_field.value or hasta_field.value:
            filtros.append(f"{desde_field.value or '…'} → {hasta_field.value or '…'}")
        resumen_text.value = (f"{len(cajas)} caja(s) · {abiertas} abierta(s)"
                              + (f" · filtro: {', '.join(filtros)}" if filtros else ""))
        page.update()

    def _toggle_venta(vid, caja_id, columnas, estado):
        if vid in expandidas:
            expandidas.discard(vid)
        else:
            expandidas.add(vid)
        cargar_ventas(caja_id, columnas, estado)

    def _fila_item(item):
        return ft.Row([
            ft.Container(width=8),
            ft.Text("•", size=12, color=N.BLUE_400),
            ft.Text(item["producto_nombre"], size=11, expand=True),
            ft.Text(f"x{item['cantidad']}", size=11, color=N.GREY_400,
                    width=34, text_align=ft.TextAlign.CENTER),
            ft.Text(f"${item['subtotal']:.2f}", size=11, width=76,
                    text_align=ft.TextAlign.RIGHT),
        ], spacing=6)

    def _acciones_factura(v: dict):
        tiene_factura = bool(v.get("numero_factura")) or (_buscar_pdf(int(v["id"])) is not None)
        if not tiene_factura:
            return ft.Container(width=76)

        def _ver(_e):
            pdf = _pdf_de_venta(db_manager, v)
            if not pdf:
                snack(page, "No se encontró el PDF del comprobante", ok=False)
                return
            ok, msg = abrir_archivo(pdf)
            if not ok:
                snack(page, f"No se pudo abrir el PDF: {msg}", ok=False)

        def _imprimir(_e):
            pdf = _pdf_de_venta(db_manager, v)
            if not pdf:
                snack(page, "No se encontró el PDF del comprobante", ok=False)
                return
            ok, msg = imprimir_archivo(pdf)
            snack(page, msg if ok else f"⚠️ {msg}", ok=ok)

        return ft.Row([
            ft.IconButton(icon=ft.Icons.SEARCH, icon_size=16,
                          icon_color=N.CYAN_300, tooltip="Ver PDF",
                          on_click=_ver),
            ft.IconButton(icon=ft.Icons.PRINT, icon_size=16,
                          icon_color=N.GREY_300, tooltip="Reimprimir",
                          on_click=_imprimir),
        ], spacing=0)

    def cargar_ventas(caja_id: int, columnas, estado):
        ventas = db_manager.obtener_ventas_por_caja(caja_id)
        columnas.controls.clear()
        for v in ventas:
            expandido = v["id"] in expandidas
            icono = ft.Icons.EXPAND_LESS if expandido else ft.Icons.EXPAND_MORE
            columnas.controls.append(ft.Container(
                content=ft.Row([
                    ft.IconButton(icon=icono, icon_size=14,
                                  icon_color=N.BLUE_300,
                                  on_click=lambda _e, vid=v["id"]:
                                      _toggle_venta(vid, caja_id, columnas, estado)),
                    ft.Text(f"Venta #{v['id']}", size=11, weight=ft.FontWeight.BOLD,
                            width=64),
                    ft.Text(str(v.get("fecha") or "")[:16], size=11, width=110),
                    ft.Text(v.get("usuario") or "—", size=11,
                            color=N.CYAN_300, width=80),
                    ft.Text(v.get("metodo_pago") or "", size=11, color=N.ORANGE_300,
                            width=110),
                    ft.Text(f"{v.get('items_count', 0)} ítems", size=11,
                            color=N.GREY_500, width=60),
                    ft.Text(f"${float(v.get('total') or 0):,.2f}", size=12,
                            weight=ft.FontWeight.BOLD, color=N.GREEN_300,
                            width=90, text_align=ft.TextAlign.RIGHT),
                    _acciones_factura(v),
                ], spacing=4),
                padding=4, border_radius=4,
            ))
            if expandido:
                for item in db_manager.obtener_items_venta(v["id"]):
                    columnas.controls.append(_fila_item(item))
        total = sum(float(v.get("total") or 0) for v in ventas)
        estado.value = (f"{len(ventas)} venta(s) · total ${total:,.2f}"
                        if ventas else "Sin ventas registradas en esta caja")
        page.update()

    def ver_caja(caja_id: int):
        caja = None
        for c in db_manager.listar_cajas(""):
            if c["id"] == caja_id:
                caja = c
                break
        if not caja:
            snack(page, "No se encontró la caja", ok=False)
            return
        expandidas.clear()
        columnas = ft.Column(spacing=2, scroll=ft.ScrollMode.AUTO)
        estado = ft.Text("", size=12, color=N.GREY_400)

        apertura = str(caja.get("fecha_apertura") or "")[:16]
        cierre = str(caja.get("fecha_cierre") or "—")[:16]
        cargar_ventas(caja_id, columnas, estado)
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row([
                ft.Icon(ft.Icons.ACCOUNT_BALANCE_WALLET, color=N.BLUE_400),
                ft.Text(f"CAJA #{caja['id']} — {caja.get('estado', '').upper()}"),
            ]),
            content=ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Text(f"Apertura: {apertura}", size=12),
                        ft.Text(f"Cierre: {cierre}", size=12,
                                color=N.GREY_400),
                        _badge(caja.get("estado") or ""),
                    ], spacing=10),
                    ft.Text(
                        f"Fondo inicial ${float(caja.get('importe_apertura') or 0):,.2f}"
                        + (f" → Cierre ${float(caja.get('importe_cierre') or 0):,.2f}"
                           if caja.get("importe_cierre") else ""),
                        size=12, color=N.GREEN_300),
                    ft.Text(
                        f"Apertura por: {caja.get('usuario_apertura') or '—'}"
                        + (f" · Cierre por: {caja.get('usuario_cierre') or '—'}"
                           if caja.get("usuario_cierre") else ""),
                        size=11, color=N.GREY_400),
                    ft.Divider(height=6),
                    ft.Text("VENTAS DE ESTA CAJA", size=11, weight=ft.FontWeight.BOLD,
                            color=N.BLUE_300),
                    columnas,
                    estado,
                ], spacing=6, scroll=ft.ScrollMode.AUTO),
                width=720, height=460,
            ),
            actions=[
                ft.TextButton("CERRAR", on_click=lambda _e: (setattr(dlg, "open", False),
                                                             page.update())),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        abrir_dialogo(page, dlg)

    busqueda_field.on_change = cargar
    cargar()

    contenedor_filtros = ft.Container(
        content=ft.Column([
            ft.Row([busqueda_field, desde_field, hasta_field,
                    ft.OutlinedButton("LIMPIAR", icon=ft.Icons.CLEAR,
                                      tooltip="Quitar fechas",
                                      on_click=lambda _e: _limpiar_fechas()),
                    resumen_text],
                   spacing=10, wrap=True,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Row([ft.Container(expand=True),
                    ft.OutlinedButton("VOLVER", icon=ft.Icons.ARROW_BACK,
                                      on_click=lambda _e: on_volver(), height=42)],
                   spacing=10),
        ], spacing=6),
        padding=12, border_radius=8, width=_ANCHO_CONTENIDO,
        border=ft.Border.all(1, ft.Colors.with_opacity(0.35, N.BLUE_GREY_700)),
        bgcolor=ft.Colors.with_opacity(0.04, ft.Colors.WHITE),
    )

    def _limpiar_fechas():
        desde_field.value = ""
        hasta_field.value = ""
        cargar()

    contenedor_lista = ft.Container(
        content=lista, height=470, width=_ANCHO_CONTENIDO,
        border=ft.Border.all(1, N.BLUE_GREY_700),
        border_radius=6, padding=8, alignment=ft.Alignment.TOP_LEFT)

    return ft.Container(
        content=ft.Column([
            ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.ACCOUNT_BALANCE_WALLET, size=24,
                            color=N.BLUE_300),
                    ft.Text("HISTORIAL DE CAJAS", size=20, weight=ft.FontWeight.BOLD),
                ], alignment=ft.MainAxisAlignment.CENTER, spacing=10),
                bgcolor=N.BLUE_900, padding=8, width=_ANCHO_CONTENIDO,
                alignment=ft.Alignment.CENTER),
            ft.Container(height=10),
            contenedor_filtros,
            ft.Container(height=8),
            contenedor_lista,
            ft.Container(height=6),
            ft.Text("Toque una caja para ver su listado de ventas. La lupa abre "
                    "el PDF del comprobante y el ícono de impresora lo reimprime.",
                    size=11, italic=True, color=N.GREY_500),
        ], scroll=ft.ScrollMode.AUTO, expand=True,
           horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        padding=20, expand=True,
    )

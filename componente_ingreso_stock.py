"""Ingreso de stock por escaneo (pensado para el celular, vía web /stock).

Flujo:
1. ESCANEAR CÓDIGO abre Binary Eye; al leer, vuelve a /stock?codigo=...
2. Confirmación: código y nombre del producto.
3. Recepción: órdenes de compra abiertas para elegir (con la cantidad pedida y
   pendiente de ese ítem) o ingreso directo sin orden. La cantidad viene
   precargada con lo pendiente, se puede bajar (recepción parcial) pero no
   superar lo pendiente. Lo que queda sin recibir sigue pendiente en la orden
   y cada ingreso queda en el historial de movimientos de stock.
"""
from __future__ import annotations

from datetime import datetime

import flet as ft
from ui.paleta import N

from ui.helpers import parse_int, snack
from ui.theme import BTN_PRIMARIO, GRADIENTE_NEON, sombra_neon
from utils import scan_relay


def IngresoStockView(db_manager, on_volver, page: ft.Page,
                     codigo_inicial: str | None = None,
                     mostrar_volver: bool = True):
    estado = {"producto": None, "pendientes": [], "opcion": None}
    montado = {"ok": False}  # evita page.update() antes de agregar la vista

    es_web = bool(getattr(page, "web", False))
    app_ok = es_web and scan_relay.es_android(page) and bool(scan_relay.origen(page))

    body = ft.Column(spacing=12)
    historial_panel = ft.Column(spacing=4)
    barcode_field = ft.TextField(
        label="Código de barras / código de producto",
        prefix_icon=ft.Icons.QR_CODE_SCANNER, expand=True,
        hint_text="Escribí o escaneá el código y presioná Enter")
    cantidad_field = ft.TextField(
        label="Cantidad a recibir", value="1", width=190,
        keyboard_type=ft.KeyboardType.NUMBER, text_align=ft.TextAlign.RIGHT)
    remito_field = ft.TextField(label="Nro de remito (opcional)", expand=True)

    def refrescar():
        if montado["ok"]:
            page.update()

    # ---------- piezas visuales ----------
    def _boton_escanear(texto="ESCANEAR CÓDIGO", altura=64, primario=True):
        url = ft.Url(scan_relay.url_app_escaner(page), target=ft.UrlTarget.SELF)
        if primario:
            return ft.FilledButton(texto, icon=ft.Icons.QR_CODE_SCANNER,
                                   height=altura, style=BTN_PRIMARIO, url=url)
        return ft.OutlinedButton(texto, icon=ft.Icons.QR_CODE_SCANNER,
                                 height=altura, url=url)

    def _tarjeta(contenido, brillo=N.CYAN):
        return ft.Container(
            content=contenido, padding=16, border_radius=14,
            bgcolor=ft.Colors.with_opacity(0.55, N.DEEP),
            border=ft.Border.all(1.5, ft.Colors.with_opacity(0.6, brillo)),
            shadow=sombra_neon(brillo, 26, 0.25))

    def _producto_card(p: dict, compacta=False):
        stock = int(p.get("stock_actual") or 0)
        minimo = int(p.get("stock_minimo") or 0)
        color = (N.RED_400 if stock <= 0 else
                 N.ORANGE_400 if stock <= minimo else N.GREEN_400)
        return _tarjeta(ft.Column([
            ft.Text(f"Código: {p.get('codigo') or '—'}", size=13,
                    color=N.CYAN, weight=ft.FontWeight.BOLD, selectable=True),
            ft.Text(p.get("descripcion") or "", size=18 if compacta else 22,
                    weight=ft.FontWeight.BOLD),
            ft.Row([
                ft.Container(
                    content=ft.Text(f"Stock: {stock}", size=13,
                                    weight=ft.FontWeight.BOLD, color=color),
                    padding=8, border_radius=6,
                    bgcolor=ft.Colors.with_opacity(0.15, color)),
                ft.Text(f"Mínimo {minimo}", size=12, color=N.GREY_400),
            ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Text(f"Proveedor: {p.get('proveedor_nombre') or 'Sin proveedor'}",
                    size=12, color=N.GREY_400),
        ], spacing=6))

    # ---------- pantallas ----------
    def mostrar_inicio():
        estado.update(producto=None, pendientes=[], opcion=None)
        barcode_field.value = ""
        manual = ft.Column([barcode_field], visible=not app_ok)

        def alternar(_e):
            manual.visible = not manual.visible
            page.update()

        piezas = []
        if app_ok:
            piezas += [
                _boton_escanear(),
                ft.Row([
                    ft.TextButton("Si no se abre, probar enlace directo", url=ft.Url(
                        scan_relay.url_app_escaner(page, intent=False),
                        target=ft.UrlTarget.SELF)),
                    ft.TextButton("Instalar Binary Eye", icon=ft.Icons.DOWNLOAD,
                                  url=ft.Url(scan_relay.URL_PLAY,
                                             target=ft.UrlTarget.BLANK)),
                ], wrap=True, spacing=4),
                ft.TextButton("Escribir código a mano", icon=ft.Icons.KEYBOARD,
                              on_click=alternar),
            ]
        else:
            piezas.append(ft.Text(
                "Escaneá con el lector de códigos o escribí el código y "
                "presioná Enter. Desde un celular Android, abrí esta pantalla "
                "en Chrome para escanear con la cámara.",
                size=12, color=N.GREY_400))
        piezas.append(manual)
        body.controls = [
            _tarjeta(ft.Column(piezas, spacing=10)),
            _tarjeta(ft.Column([
                ft.Text("ÚLTIMOS INGRESOS DE HOY", size=11,
                        weight=ft.FontWeight.BOLD, color=N.GREEN_300),
                historial_panel,
            ], spacing=6), brillo=N.VIOLET),
        ]
        cargar_historial()
        refrescar()

    def mostrar_confirmacion(codigo: str, producto: dict | None):
        if not producto:
            body.controls = [_tarjeta(ft.Column([
                ft.Icon(ft.Icons.ERROR_OUTLINE, size=44, color=N.RED_400),
                ft.Text("No se encontró el producto", size=18,
                        weight=ft.FontWeight.BOLD),
                ft.Text(f"Código leído: {codigo}", size=14, color=N.CYAN,
                        selectable=True),
                _boton_escanear("ESCANEAR OTRO", 52) if app_ok else
                ft.FilledButton("VOLVER", height=48, on_click=lambda _e:
                                mostrar_inicio()),
            ], spacing=10), brillo=N.RED_400)]
            refrescar()
            return
        estado["producto"] = producto
        estado["pendientes"] = db_manager.buscar_ordenes_pendientes_producto(
            int(producto["id"]))
        n = len(estado["pendientes"])
        aviso = (f"Tiene {n} orden{'es' if n != 1 else ''} de compra abierta"
                 f"{'s' if n != 1 else ''}." if n else
                 "No tiene órdenes de compra abiertas: se ingresa como stock directo.")
        body.controls = [
            ft.Text("¿Es este el producto?", size=14, color=N.GREY_400),
            _producto_card(producto),
            ft.Text(aviso, size=12, italic=True, color=N.AMBER_300 if n else N.GREY_400),
            ft.FilledButton("CONFIRMAR", icon=ft.Icons.CHECK, height=56,
                            style=BTN_PRIMARIO,
                            on_click=lambda _e: mostrar_recepcion()),
            _boton_escanear("ESCANEAR OTRO", 48, primario=False) if app_ok else
            ft.OutlinedButton("CANCELAR", height=48,
                              on_click=lambda _e: mostrar_inicio()),
        ]
        refrescar()

    def _maximo() -> int | None:
        op = estado["opcion"]
        return int(op["pendiente"]) if op else None

    def _validar_cantidad(_e=None) -> bool:
        maximo = _maximo()
        cant = parse_int(cantidad_field.value, 0)
        if cant <= 0:
            cantidad_field.error = "Ingresá una cantidad mayor a cero"
        elif maximo is not None and cant > maximo:
            cantidad_field.error = f"No puede superar lo pendiente ({maximo})"
        else:
            cantidad_field.error = None
        if _e is not None:
            page.update()
        return cantidad_field.error is None

    def _elegir(op: dict | None):
        estado["opcion"] = op
        cantidad_field.value = str(int(op["pendiente"])) if op else "1"
        cantidad_field.helper = (f"Máximo {int(op['pendiente'])} (pendiente de la orden)"
                                 if op else "Sin límite: ingreso directo")
        cantidad_field.error = None
        _dibujar_recepcion()
        refrescar()

    def _opcion_card(titulo, detalle, seleccionada, on_click, extra=None):
        color = N.CYAN if seleccionada else N.BLUE_GREY_600
        fila = [
            ft.Icon(ft.Icons.RADIO_BUTTON_CHECKED if seleccionada
                    else ft.Icons.RADIO_BUTTON_UNCHECKED, color=color),
            ft.Column([
                ft.Text(titulo, size=14, weight=ft.FontWeight.BOLD),
                ft.Text(detalle, size=11, color=N.GREY_400),
            ], spacing=1, expand=True),
        ]
        if extra:
            fila.append(extra)
        return ft.Container(
            content=ft.Row(fila, spacing=10,
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=12, border_radius=12, on_click=on_click,
            bgcolor=ft.Colors.with_opacity(0.18 if seleccionada else 0.05,
                                           N.CYAN if seleccionada else ft.Colors.WHITE),
            border=ft.Border.all(1.5 if seleccionada else 1,
                                 ft.Colors.with_opacity(0.9 if seleccionada else 0.4, color)),
            shadow=sombra_neon(N.CYAN, 18, 0.3) if seleccionada else None)

    def _dibujar_recepcion():
        producto = estado["producto"]
        opciones = []
        for pend in estado["pendientes"]:
            sel = estado["opcion"] is pend
            opciones.append(_opcion_card(
                f"Orden #{pend['orden_id']} · {pend.get('proveedor_nombre') or 'Sin proveedor'}",
                f"Pedido {pend['cantidad']} · recibido "
                f"{pend.get('cantidad_recibida') or 0} · "
                f"{str(pend.get('fecha_creacion') or '')[:10]}",
                sel, lambda _e, p=pend: _elegir(p),
                extra=ft.Container(
                    content=ft.Text(f"Pend. {pend['pendiente']}", size=12,
                                    weight=ft.FontWeight.BOLD, color=N.AMBER_300),
                    padding=6, border_radius=6,
                    bgcolor=ft.Colors.with_opacity(0.15, N.AMBER_700))))
        opciones.append(_opcion_card(
            "Ingreso directo (sin orden)",
            "Suma stock sin descontar de ninguna orden de compra",
            estado["opcion"] is None, lambda _e: _elegir(None)))
        body.controls = [
            _producto_card(producto, compacta=True),
            ft.Text("ELEGÍ DÓNDE RECEPCIONAR" if estado["pendientes"]
                    else "INGRESO DIRECTO", size=11, weight=ft.FontWeight.BOLD,
                    color=N.AMBER_300),
            *opciones,
            ft.Row([cantidad_field, remito_field], spacing=8,
                   vertical_alignment=ft.CrossAxisAlignment.START),
            ft.FilledButton("RECEPCIONAR", icon=ft.Icons.INVENTORY, height=56,
                            style=BTN_PRIMARIO, on_click=lambda _e: recibir()),
            _boton_escanear("CANCELAR Y ESCANEAR OTRO", 46, primario=False)
            if app_ok else ft.OutlinedButton(
                "CANCELAR", height=46, on_click=lambda _e: mostrar_inicio()),
        ]

    def mostrar_recepcion():
        if not estado["producto"]:
            return
        remito_field.value = ""
        # Preselecciona la orden más antigua: confirmar es un toque.
        _elegir(estado["pendientes"][0] if estado["pendientes"] else None)

    # ---------- acciones ----------
    def buscar_codigo(codigo: str):
        codigo = (codigo or "").strip()
        if not codigo:
            return
        producto = db_manager.obtener_producto_por_codigo(codigo)
        if not producto:
            hallados = db_manager.buscar_productos(codigo, "codigo", limit=1)
            producto = hallados[0] if hallados else None
        mostrar_confirmacion(codigo, producto)

    def recibir():
        producto, op = estado["producto"], estado["opcion"]
        if not producto or not _validar_cantidad(None):
            page.update()
            if producto:
                snack(page, cantidad_field.error or "Cantidad inválida", ok=False)
            return
        cantidad = parse_int(cantidad_field.value, 0)
        remito = (remito_field.value or "").strip()
        if op:
            ok, msg = db_manager.recibir_orden_compra(
                int(op["orden_id"]), {int(op["item_id"]): cantidad},
                remito=remito, observaciones="Recepción por escaneo de código")
            if ok:
                quedan = int(op["pendiente"]) - cantidad
                msg = (f"Orden #{op['orden_id']}: +{cantidad} recibidas. "
                       + (f"Quedan {quedan} pendientes en la orden."
                          if quedan > 0 else "Ítem completo."))
        else:
            ok, msg = db_manager.ingresar_stock_directo(
                int(producto["id"]), cantidad, remito=remito,
                observaciones="Ingreso por escaneo (sin orden)")
        snack(page, msg, ok=ok)
        if ok:
            mostrar_inicio()

    def cargar_historial():
        historial_panel.controls.clear()
        hoy = datetime.now().strftime("%Y-%m-%d")
        try:
            movs = db_manager.obtener_movimientos_stock_detallado(limit=80)
        except Exception:
            movs = []
        ingresos = [m for m in movs if m.get("tipo") == "ingreso"
                    and str(m.get("fecha") or "").startswith(hoy)][:10]
        if not ingresos:
            historial_panel.controls.append(ft.Text(
                "Todavía no hay ingresos registrados hoy.", size=11,
                italic=True, color=N.GREY_500))
            return
        for m in ingresos:
            ref = (f"Orden #{m['referencia_id']}" if m.get("referencia_id")
                   else "Directo")
            historial_panel.controls.append(ft.Row([
                ft.Text(str(m.get("fecha") or "")[11:16], size=11, width=40,
                        color=N.GREY_500),
                ft.Text(m.get("producto_nombre") or "", size=11, expand=True,
                        max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                ft.Text(ref, size=10, color=N.AMBER_300, width=72),
                ft.Text(f"+{m.get('cantidad')}", size=12, width=40,
                        weight=ft.FontWeight.BOLD, color=N.GREEN_300,
                        text_align=ft.TextAlign.RIGHT),
            ], spacing=6))

    barcode_field.on_submit = lambda _e: buscar_codigo(barcode_field.value)
    cantidad_field.on_change = _validar_cantidad
    cantidad_field.on_submit = lambda _e: recibir()
    remito_field.on_submit = lambda _e: recibir()

    # Estado inicial: con código de retorno va directo a la confirmación.
    if codigo_inicial:
        try:
            buscar_codigo(codigo_inicial)
        except Exception:
            mostrar_inicio()
    else:
        mostrar_inicio()
    montado["ok"] = True

    salir = ft.IconButton(
        ft.Icons.ARROW_BACK if mostrar_volver else ft.Icons.LOGOUT,
        tooltip="Volver" if mostrar_volver else "Cerrar sesión",
        icon_color=ft.Colors.WHITE, on_click=lambda _e: on_volver())
    return ft.Container(
        content=ft.Column([
            ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.ADD_BOX, size=24, color=ft.Colors.WHITE),
                    ft.Text("INGRESO DE STOCK", size=20,
                            weight=ft.FontWeight.BOLD, expand=True),
                    salir,
                ], spacing=10),
                gradient=GRADIENTE_NEON, padding=ft.Padding.symmetric(
                    horizontal=12, vertical=6), border_radius=12,
                shadow=sombra_neon(N.CYAN, 22, 0.35)),
            body,
        ], spacing=12, scroll=ft.ScrollMode.AUTO, expand=True),
        padding=12, expand=True)

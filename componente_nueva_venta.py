"""Modal de nueva venta: búsqueda predictiva, carrito, cobro efectivo/QR + facturación auto."""
import os
import platform
import subprocess

import flet as ft
from ui.paleta import N

from services.billing_service import billing_service
from services.mercadopago_service import mp_service
from ui.helpers import cerrar_dialogo, snack
from ui.theme import BTN_INFO, BTN_PRIMARIO
from utils.paths import base_dir

_FUENTE_DIGITAL = base_dir() / "assets" / "fonts" / "DSEG7Classic-Bold.ttf"
_VERDE_FLUOR = "#39FF14"


def abrir_pdf(filepath):
    """Abre el PDF generado según el sistema operativo (como el build)."""
    try:
        if platform.system() == "Windows":
            os.startfile(filepath)  # type: ignore[attr-defined]
        elif platform.system() == "Darwin":
            subprocess.run(["open", filepath], check=False)
        else:
            subprocess.run(["xdg-open", filepath], check=False)
    except Exception as e:  # noqa: BLE001
        print(f"Error abriendo PDF: {e}")



def _leer_recargo(db_manager, clave: str = "RECARGO") -> float:
    """Recargo % por medio de pago: .env/Config (solo RECARGO) > tabla config."""
    if clave == "RECARGO":
        try:
            from core.settings import settings

            if settings.recargo_porcentaje:
                return float(settings.recargo_porcentaje)
        except Exception:
            pass
    try:
        return float((db_manager.get_config_value(clave) or "0").replace(",", "."))
    except (TypeError, ValueError, AttributeError):
        return 0.0


def _cfg_bool(db_manager, key: str, default: bool = False) -> bool:
    """Lee un flag SI/NO de la tabla config (default NO)."""
    try:
        val = db_manager.get_config_value(key)
    except Exception:
        val = None
    if val in (None, ""):
        return default
    return str(val).strip().lower() in ("1", "true", "yes", "si", "sí", "on")


def _fmt_ars(valor: float) -> str:
    """Importe con separador de miles y 2 decimales, formato Argentina."""
    try:
        return f"{float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return "0,00"


def _leer_flags_facturacion(db_manager) -> dict:
    """Flags de facturación automática (Ajustes). Por defecto: NO."""
    return {
        "activa": _cfg_bool(db_manager, "FACTURACION_ACTIVA", True),
        "auto_qr": _cfg_bool(db_manager, "FACTURAR_AUTO_QR", False),
        "auto_efectivo": _cfg_bool(db_manager, "FACTURAR_AUTO_EFECTIVO", False),
    }



def _aplicar_recargo(items: list[dict], porcentaje: float) -> list[dict]:
    if not porcentaje:
        return items
    out = []
    for it in items:
        c = dict(it)
        c["subtotal"] = round(c["subtotal"] * (1 + porcentaje / 100), 2)
        c["precio_unitario"] = round(c["subtotal"] / c["cantidad"], 2) if c["cantidad"] else c["precio_unitario"]
        out.append(c)
    return out


def SeleccionMetodoPagoView(db_manager, page, on_metodo, on_cancelar=None, sm_manager=None):
    """Selector previo de medio de pago, navegable con flechas + Enter o mouse."""
    recargos = {
        "efectivo": 0.0,
        "tarjeta_debito": _leer_recargo(db_manager, "RECARGO_DEBITO"),
        "tarjeta_credito": _leer_recargo(db_manager, "RECARGO_CREDITO"),
        "mercadopago_qr": _leer_recargo(db_manager, "RECARGO"),
    }
    opciones = [{
        "clave": "efectivo", "label": "Efectivo",
        "detalle": "Sin recargo", "icon": ft.Icons.PAYMENTS,
        "color": N.GREEN_400,
    }]
    if _cfg_bool(db_manager, "TARJETA_DEBITO_ACTIVO", True):
        r = recargos["tarjeta_debito"]
        opciones.append({
            "clave": "tarjeta_debito", "label": "Débito",
            "detalle": f"Recargo +{r:g}%" if r else "Sin recargo",
            "icon": ft.Icons.CREDIT_CARD, "color": N.CYAN_400,
        })
    if _cfg_bool(db_manager, "TARJETA_CREDITO_ACTIVO", True):
        r = recargos["tarjeta_credito"]
        opciones.append({
            "clave": "tarjeta_credito", "label": "Crédito",
            "detalle": f"Recargo +{r:g}%" if r else "Sin recargo",
            "icon": ft.Icons.CREDIT_SCORE, "color": N.PURPLE_300,
        })
    if _cfg_bool(db_manager, "MP_ACTIVO", True):
        r = recargos["mercadopago_qr"]
        opciones.append({
            "clave": "mercadopago_qr", "label": "QR / Mercado Pago",
            "detalle": f"Recargo +{r:g}%" if r else "Sin recargo",
            "icon": ft.Icons.QR_CODE_2, "color": N.ORANGE_300,
        })

    seleccion = {"idx": 0}
    aceptado = {"valor": False}
    tarjetas: list[ft.Container] = []

    def _pintar():
        for i, tarjeta in enumerate(tarjetas):
            activa = (i == seleccion["idx"])
            tarjeta.bgcolor = (ft.Colors.with_opacity(0.18, N.GREEN)
                               if activa else ft.Colors.with_opacity(0.06, ft.Colors.WHITE))
            tarjeta.border = ft.Border.all(
                2, N.GREEN if activa else N.BLUE_GREY_700)
            tarjeta.shadow = (ft.BoxShadow(
                blur_radius=16, spread_radius=1,
                color=ft.Colors.with_opacity(0.35, N.GREEN))
                if activa else None)
            try:
                tarjeta.content.controls[2].visible = activa
            except Exception:
                pass
        try:
            page.update()
        except Exception:
            pass

    def _seleccionar(idx: int):
        seleccion["idx"] = idx % len(opciones)
        _pintar()

    def _mover(delta: int):
        _seleccionar(seleccion["idx"] + delta)

    def _cleanup(forzar: bool = False):
        if aceptado["valor"] and not forzar:
            return
        if sm_manager is not None:
            for k in ("arrow up", "arrow down", "arrow left", "arrow right", "enter"):
                try:
                    sm_manager.unregister_nav(k)
                except Exception:
                    pass

    def _aceptar(e=None):
        metodo = opciones[seleccion["idx"]]["clave"]
        aceptado["valor"] = True
        _cleanup(forzar=True)
        try:
            dialog.open = False
            page.update()
        except Exception:
            pass

        async def _abrir():
            import asyncio
            await asyncio.sleep(0.05)
            on_metodo(metodo)

        try:
            page.run_task(_abrir)
        except Exception:
            on_metodo(metodo)

    def _cancelar(e=None):
        _cleanup()
        try:
            dialog.open = False
            page.update()
        except Exception:
            cerrar_dialogo(page)
        if on_cancelar is not None:
            on_cancelar()

    for i, opcion in enumerate(opciones):
        color_icono = opcion["color"]
        tarjeta = ft.Container(
            content=ft.Row([
                ft.Container(
                    content=ft.Icon(opcion["icon"], size=30, color=color_icono),
                    width=54, height=54, alignment=ft.Alignment.CENTER,
                    bgcolor=ft.Colors.with_opacity(0.14, color_icono),
                    border_radius=10,
                ),
                ft.Column([
                    ft.Text(opcion["label"], size=16, weight=ft.FontWeight.BOLD),
                    ft.Text(opcion["detalle"], size=11, color=N.GREY_400),
                ], spacing=2, expand=True),
                ft.Icon(ft.Icons.CHECK_CIRCLE, color=N.GREEN, visible=False),
            ], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=14, border_radius=10, ink=True,
            border=ft.Border.all(2, N.BLUE_GREY_700),
            bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.WHITE),
            on_click=lambda _, idx=i: _seleccionar(idx),
            col={"xs": 12, "sm": 6},
        )
        tarjetas.append(tarjeta)

    dialog = ft.AlertDialog(
        modal=True,
        on_dismiss=lambda _: _cleanup(),
        title=ft.Row([
            ft.Icon(ft.Icons.POINT_OF_SALE, color=N.GREEN_700),
            ft.Text("¿Cómo se cobra?", size=20, weight=ft.FontWeight.BOLD),
        ]),
        content=ft.Container(
            content=ft.Column([
                ft.Text("Elegí con las flechas y Enter, o hacé clic y presioná Aceptar.",
                        size=12, color=N.GREY_400),
                ft.ResponsiveRow(tarjetas, spacing=10, run_spacing=10),
                ft.Row([
                    ft.TextButton("CANCELAR (Esc)", on_click=_cancelar),
                    ft.FilledButton("ACEPTAR (Enter)", icon=ft.Icons.CHECK,
                                    on_click=_aceptar, style=BTN_PRIMARIO),
                ], alignment=ft.MainAxisAlignment.END, spacing=8),
            ], spacing=14, tight=True),
            width=640,
        ),
        open=True,
    )

    if sm_manager is not None:
        sm_manager.register_nav("arrow up", lambda *_: _mover(-1))
        sm_manager.register_nav("arrow down", lambda *_: _mover(1))
        sm_manager.register_nav("arrow left", lambda *_: _mover(-1))
        sm_manager.register_nav("arrow right", lambda *_: _mover(1))
        sm_manager.register_nav("enter", lambda *_: _aceptar())

    _pintar()
    return dialog



def NuevaVentaView(db_manager, caja_id, on_confirmar, on_cerrar, filter_mode, page,
                   sm_manager=None, metodo_pago="efectivo"):
    # ---- estado ----
    carrito: list[dict] = []
    pagando_qr = {"activo": False, "cancelado": False}
    recargo_mp = _leer_recargo(db_manager, "RECARGO")
    recargo_debito = _leer_recargo(db_manager, "RECARGO_DEBITO")
    recargo_credito = _leer_recargo(db_manager, "RECARGO_CREDITO")
    mp_activo = _cfg_bool(db_manager, "MP_ACTIVO", True)
    debito_activo = _cfg_bool(db_manager, "TARJETA_DEBITO_ACTIVO", True)
    credito_activo = _cfg_bool(db_manager, "TARJETA_CREDITO_ACTIVO", True)
    vuelto_activo = _cfg_bool(db_manager, "VUELTO_ACTIVO", False)
    flags = _leer_flags_facturacion(db_manager)
    auto_qr = flags["activa"] and flags["auto_qr"]
    auto_efectivo = flags["activa"] and flags["auto_efectivo"]

    metodos = {
        "efectivo": ("Efectivo", ft.Icons.PAYMENTS, N.GREEN_400, 0.0),
        "tarjeta_debito": ("Débito", ft.Icons.CREDIT_CARD, N.CYAN_400, recargo_debito),
        "tarjeta_credito": ("Crédito", ft.Icons.CREDIT_SCORE, N.PURPLE_300, recargo_credito),
        "mercadopago_qr": ("QR / Mercado Pago", ft.Icons.QR_CODE_2, N.ORANGE_300, recargo_mp),
    }
    if metodo_pago not in metodos:
        metodo_pago = "efectivo"
    metodo_label, metodo_icon, metodo_color, recargo_metodo = metodos[metodo_pago]
    es_qr = (metodo_pago == "mercadopago_qr")
    es_efectivo = (metodo_pago == "efectivo")

    # Facturación AFIP (como el build); se instancia de forma perezosa/tolerante a fallos
    try:
        from facturacion_manager import FacturacionManager

        facturacion = FacturacionManager(db_manager)
    except Exception as ex:  # noqa: BLE001
        print(f"AFIP no disponible: {ex}")
        facturacion = None

    # ---- panel mensajes ----
    log_text = ft.Text("Listo para registrar una venta.", size=13, color=ft.Colors.WHITE)
    log_box = ft.Container(
        bgcolor=ft.Colors.with_opacity(0.15, N.BLUE_GREY_700),
        border_radius=6, padding=10, content=log_text,
        alignment=ft.Alignment.CENTER_LEFT, width=280,
    )
    col_izquierda = ft.Container(content=log_box, padding=10,
                                 bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.WHITE),
                                 border_radius=5, col={"xs": 12, "sm": 4})

    def mostrar_mensaje(mensaje: str, color) -> None:
        log_text.value = mensaje
        log_box.bgcolor = ft.Colors.with_opacity(0.2, color)
        try:
            page.update()
        except Exception:
            pass

    def mostrar_exito(m): mostrar_mensaje(f"✅ {m}", N.GREEN_700)
    def mostrar_error(m): mostrar_mensaje(f"⚠️ {m}", N.RED_700)
    def log_ui(m): mostrar_mensaje(f"ℹ️ {m}", N.BLUE_GREY_700)

    # ---- búsqueda ----
    search_field = ft.TextField(label="Buscar producto", prefix_icon=ft.Icons.SEARCH,
                                autofocus=True, ignore_up_down_keys=False,
                                col={"xs": 12, "sm": 8, "md": 9})
    filtro_dropdown = ft.Dropdown(value=filter_mode or "descripcion",
                                  col={"xs": 12, "sm": 4, "md": 3}, options=[
        ft.dropdown.Option("descripcion", "Descripción"),
        ft.dropdown.Option("codigo", "Código"),
    ])
    vw = float(getattr(page, "width", 0) or 1400)
    vh = float(getattr(page, "height", 0) or 900)
    ancho_dialogo = int(min(1240, max(560, vw - 40)))
    alto_dialogo = int(min(780, max(560, vh - 140)))
    alto_resultados = 180 if alto_dialogo >= 720 else 110
    alto_carrito = 220 if alto_dialogo >= 720 else 160
    resultados_list = ft.ListView(height=alto_resultados, spacing=4)
    carrito_list = ft.ListView(height=alto_carrito, spacing=4)

    familia_digital = "Courier New"
    if _FUENTE_DIGITAL.exists():
        try:
            page.fonts = {**(page.fonts or {}), "DSEG7": "fonts/DSEG7Classic-Bold.ttf"}
            familia_digital = "DSEG7"
        except Exception:
            pass

    total_text = ft.Text(value="0,00", size=38, font_family=familia_digital,
                         weight=ft.FontWeight.BOLD, color=_VERDE_FLUOR,
                         text_align=ft.TextAlign.RIGHT, no_wrap=True, width=270)
    total_panel = ft.Container(
        content=ft.Column([
            ft.Row([ft.Text("TOTAL", size=11, weight=ft.FontWeight.BOLD,
                            color=N.GREEN_400),
                    ft.Container(expand=True),
                    ft.Text("$", size=20, weight=ft.FontWeight.BOLD,
                            color=N.GREEN_400)],
                   spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            total_text,
        ], spacing=0, tight=True),
        bgcolor=N.BLACK,
        border=ft.Border.all(2, N.GREEN),
        border_radius=10,
        padding=ft.Padding.symmetric(horizontal=14, vertical=8),
        shadow=ft.BoxShadow(blur_radius=16, spread_radius=1,
                            color=ft.Colors.with_opacity(0.45, N.GREEN)),
        width=300,
        alignment=ft.Alignment.CENTER_RIGHT,
    )
    metodo_header = ft.Row([
        ft.Icon(metodo_icon, color=metodo_color, size=22),
        ft.Text(f"Método elegido: {metodo_label}", size=15,
                weight=ft.FontWeight.BOLD),
    ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)
    metodo_detalle_text = ft.Text("", size=11, color=N.GREY_400)
    total_efectivo_text = ft.Text(value="Efectivo: $0,00", size=12, color=N.BLUE_200)
    total_qr_text = ft.Text(value="QR/MP: $0,00", size=12, color=N.ORANGE_300)
    total_debito_text = ft.Text(value="Débito: $0,00", size=12, color=N.CYAN_300)
    total_credito_text = ft.Text(value="Crédito: $0,00", size=12, color=N.PURPLE_300)
    recibe_field = ft.TextField(label="Recibe $", width=110, height=44,
                               keyboard_type=ft.KeyboardType.NUMBER, text_align=ft.TextAlign.CENTER)
    vuelto_text = ft.Text(value="", size=13, weight=ft.FontWeight.BOLD)

    def _actualizar_vuelto(total_efectivo: float):
        if not vuelto_activo:
            return
        try:
            recibe = float((recibe_field.value or "0").replace(",", "."))
        except ValueError:
            vuelto_text.value = "Monto inválido"
            vuelto_text.color = N.RED_400
            try:
                page.update()
            except Exception:
                pass
            return
        diferencia = recibe - total_efectivo
        if diferencia >= 0:
            vuelto_text.value = f"Vuelto: ${_fmt_ars(diferencia)}"
            vuelto_text.color = N.GREEN_300
        else:
            vuelto_text.value = f"Faltan: ${_fmt_ars(-diferencia)}"
            vuelto_text.color = N.RED_400
        try:
            page.update()
        except Exception:
            pass

    resultados_actuales: list[dict] = []
    resultados_termino = {"valor": ""}
    indice_seleccionado = 0

    def _render_resultados():
        resultados_list.controls.clear()
        for i, producto in enumerate(resultados_actuales):
            seleccionado = (i == indice_seleccionado)
            stock_color = N.GREEN_700 if producto["stock_actual"] > producto["stock_minimo"] else N.RED_700
            resultados_list.controls.append(ft.Container(
                key=f"res_{i}",
                content=ft.Row([
                    ft.Column([ft.Text(producto["descripcion"], weight=ft.FontWeight.BOLD, size=13),
                               ft.Text(f"Código: {producto['codigo']}", size=10, color=N.GREY_500)],
                              spacing=2, expand=True),
                    ft.Column([ft.Text(f"${_fmt_ars(producto['precio_lista'])}", size=15, weight=ft.FontWeight.BOLD),
                               ft.Text(f"Stock: {producto['stock_actual']}", size=10, color=stock_color)],
                              horizontal_alignment=ft.CrossAxisAlignment.END, spacing=2),
                    ft.IconButton(icon=ft.Icons.ADD_SHOPPING_CART, icon_color=N.GREEN_700,
                                  icon_size=18, width=30, height=30, padding=0,
                                  tooltip="Agregar",
                                  on_click=lambda _, p=producto: agregar_al_carrito(p)),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                bgcolor=N.GREEN_900 if seleccionado else N.BLUE_GREY_900,
                border=ft.Border.all(2, N.GREEN_400) if seleccionado else None,
                padding=6, border_radius=5,
                on_click=lambda _, p=producto: agregar_al_carrito(p), ink=True,
            ))
        page.update()
        if resultados_actuales:
            try:
                if hasattr(page, "run_task"):
                    page.run_task(resultados_list.scroll_to,
                                  scroll_key=f"res_{indice_seleccionado}", duration=100)
                else:
                    resultados_list.scroll_to(scroll_key=f"res_{indice_seleccionado}", duration=100)
            except Exception:
                pass

    def buscar_producto(e=None):
        nonlocal indice_seleccionado
        termino = (search_field.value or "").strip()
        resultados_termino["valor"] = termino
        if not termino:
            resultados_actuales.clear()
            indice_seleccionado = 0
            resultados_list.controls.clear()
            page.update()
            return
        productos = db_manager.buscar_productos(termino, filtro_dropdown.value or "descripcion")
        resultados_actuales[:] = productos[:10]
        indice_seleccionado = 0
        _render_resultados()

    def _mover_seleccion(delta):
        nonlocal indice_seleccionado
        if not resultados_actuales:
            return
        indice_seleccionado = (indice_seleccionado + delta) % len(resultados_actuales)
        _render_resultados()

    def _nav_teclado(e):
        key = (getattr(e, "key", "") or "").lower()
        if key in ("arrow up", "arrowup", "up"):
            _mover_seleccion(-1)
        elif key in ("arrow down", "arrowdown", "down"):
            _mover_seleccion(1)
        else:
            return
        # Mantener el cursor al final del buscador (sin sacarle el foco).
        try:
            fin = len(search_field.value or "")
            search_field.selection = ft.TextSelection(base_offset=fin, extent_offset=fin)
            page.update()
        except Exception:
            pass

    def agregar_al_carrito(producto):
        nonlocal indice_seleccionado
        if producto["stock_actual"] <= 0:
            mostrar_error("Producto sin stock")
            return
        for item in carrito:
            if item["producto_id"] == producto["id"]:
                if item["cantidad"] < producto["stock_actual"]:
                    item["cantidad"] += 1
                    item["subtotal"] = round(item["cantidad"] * item["precio_unitario"], 2)
                else:
                    mostrar_error("No hay más stock disponible")
                    return
                break
        else:
            carrito.append({"producto_id": producto["id"], "descripcion": producto["descripcion"],
                            "precio_unitario": float(producto["precio_lista"]),
                            "cantidad": 1, "subtotal": float(producto["precio_lista"]),
                            "stock_disponible": producto["stock_actual"]})
        search_field.value = ""
        resultados_actuales.clear()
        resultados_termino["valor"] = ""
        indice_seleccionado = 0
        resultados_list.controls.clear()
        actualizar_carrito()
        try:
            # Flet 1.x: focus() es corrutina; usar run_task si está disponible
            if hasattr(page, "run_task"):
                page.run_task(search_field.focus)
            else:
                search_field.focus()
        except Exception:
            pass

    def actualizar_carrito():
        carrito_list.controls.clear()
        total = 0.0
        for i, item in enumerate(carrito):
            total += item["subtotal"]
            carrito_list.controls.append(ft.Container(
                content=ft.Row([
                    ft.Text(item["descripcion"], width=200, size=12),
                    ft.Row([
                        ft.IconButton(icon=ft.Icons.REMOVE, icon_size=14,
                                      width=28, height=28, padding=0,
                                      on_click=lambda _, idx=i: cambiar_cantidad(idx, -1)),
                        ft.Text(f"x{item['cantidad']}", width=30, text_align=ft.TextAlign.CENTER, size=12),
                        ft.IconButton(icon=ft.Icons.ADD, icon_size=14,
                                      width=28, height=28, padding=0,
                                      on_click=lambda _, idx=i: cambiar_cantidad(idx, 1)),
                    ], spacing=0),
                    ft.Text(f"${_fmt_ars(item['subtotal'])}", width=90, text_align=ft.TextAlign.RIGHT,
                            weight=ft.FontWeight.BOLD, size=12),
                    ft.IconButton(icon=ft.Icons.DELETE, icon_size=16, icon_color=N.RED_400,
                                  width=28, height=28, padding=0,
                                  on_click=lambda _, idx=i: eliminar_item(idx)),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                bgcolor=N.GREEN_900, padding=4, border_radius=5,
            ))
        def _total_metodo(porcentaje: float) -> float:
            if not porcentaje:
                return round(total, 2)
            return round(sum(i["subtotal"] for i in _aplicar_recargo(carrito, porcentaje)), 2)

        con_mp = _total_metodo(recargo_mp)
        con_debito = _total_metodo(recargo_debito)
        con_credito = _total_metodo(recargo_credito)
        total_metodo = {
            "efectivo": total,
            "tarjeta_debito": con_debito,
            "tarjeta_credito": con_credito,
            "mercadopago_qr": con_mp,
        }[metodo_pago]

        texto_total = _fmt_ars(total_metodo)
        total_text.value = texto_total
        total_text.size = 34 if len(texto_total) <= 9 else 30 if len(texto_total) <= 12 else 24
        metodo_detalle_text.value = (
            (f"Recargo +{recargo_metodo:g}% · Carrito: ${_fmt_ars(total)}"
             if recargo_metodo else f"Sin recargo · Carrito: ${_fmt_ars(total)}"))
        total_efectivo_text.value = f"Efectivo: ${_fmt_ars(total)}"
        total_qr_text.value = (f"QR/MP (+{recargo_mp:g}%): ${_fmt_ars(con_mp)}"
                               if recargo_mp else f"QR/MP: ${_fmt_ars(total)}")
        total_qr_text.visible = mp_activo
        total_debito_text.value = (f"Débito (+{recargo_debito:g}%): ${_fmt_ars(con_debito)}"
                                   if recargo_debito else f"Débito: ${_fmt_ars(total)}")
        total_debito_text.visible = debito_activo
        total_credito_text.value = (f"Crédito (+{recargo_credito:g}%): ${_fmt_ars(con_credito)}"
                                     if recargo_credito else f"Crédito: ${_fmt_ars(total)}")
        total_credito_text.visible = credito_activo
        for clave, txt in (
            ("efectivo", total_efectivo_text),
            ("mercadopago_qr", total_qr_text),
            ("tarjeta_debito", total_debito_text),
            ("tarjeta_credito", total_credito_text),
        ):
            elegido = (clave == metodo_pago)
            txt.value = ("▶ " if elegido else "   ") + txt.value
            txt.weight = ft.FontWeight.BOLD if elegido else ft.FontWeight.NORMAL
        recibe_field.visible = vuelto_activo and es_efectivo
        vuelto_text.visible = vuelto_activo and es_efectivo
        if es_efectivo:
            _actualizar_vuelto(total)
        if not carrito:
            carrito_list.controls.append(ft.Text("Carrito vacío — busque y agregue productos",
                                                italic=True, text_align=ft.TextAlign.CENTER))
        page.update()

    def cambiar_cantidad(index, delta):
        if not (0 <= index < len(carrito)):
            return
        item = carrito[index]
        nueva = item["cantidad"] + delta
        if nueva <= 0:
            eliminar_item(index)
        elif nueva <= item["stock_disponible"]:
            item["cantidad"] = nueva
            item["subtotal"] = round(nueva * item["precio_unitario"], 2)
            actualizar_carrito()
        else:
            mostrar_error("No hay más stock disponible")

    def eliminar_item(index):
        if 0 <= index < len(carrito):
            carrito.pop(index)
            actualizar_carrito()

    # ---- confirmar ----
    def _cerrar_dialogo():
        # Cierre explícito del modal: pop_dialog() fallaría si hay un SnackBar encima
        try:
            dialog.open = False
            page.update()
        except Exception:
            cerrar_dialogo(page)

    def _unregister_shortcuts():
        if sm_manager is not None:
            for k in ("c", "m", "e", "d", "t"):
                try:
                    sm_manager.unregister(k)
                except Exception:
                    pass
            for k in ("arrow up", "arrow down"):
                try:
                    sm_manager.unregister_nav(k)
                except Exception:
                    pass

    def confirmar_venta(metodo_pago="efectivo", imprimir=False, emitir_factura=False):
        if pagando_qr["activo"]:
            mostrar_error("Hay un cobro QR en curso")
            return
        if not carrito:
            mostrar_error("El carrito está vacío")
            return
        items = list(carrito)
        if metodo_pago == "mercadopago_qr" and recargo_mp:
            items = _aplicar_recargo(items, recargo_mp)
        elif metodo_pago == "tarjeta_debito" and recargo_debito:
            items = _aplicar_recargo(items, recargo_debito)
        elif metodo_pago == "tarjeta_credito" and recargo_credito:
            items = _aplicar_recargo(items, recargo_credito)
        total = round(sum(i["subtotal"] for i in items), 2)
        log_ui("Registrando venta en la base de datos...")
        venta_id, exito = db_manager.crear_venta(caja_id, items, metodo_pago=metodo_pago)
        if not exito:
            mostrar_error("Error al registrar (verifique stock y caja abierta)")
            return
        mostrar_exito(f"Venta #{venta_id} registrada")

        # --- Facturación AFIP + ticket PDF en un paso (como el build) ---
        if emitir_factura and facturacion is not None:
            log_ui("Emitiendo factura electrónica AFIP...")

            def proceso_facturacion():
                try:
                    resultado = facturacion.emitir_y_generar_ticket(
                        venta_id, items, metodo_pago, generar_pdf=True
                    )
                    if resultado.get("success"):
                        pdf_path = resultado.get("pdf_path")
                        mostrar_exito(
                            f"Factura #{resultado.get('numero_factura')} · CAE {resultado.get('cae')}"
                        )
                        if pdf_path:
                            abrir_pdf(pdf_path)
                    else:
                        mostrar_error(resultado.get("message", "Error al facturar"))
                except Exception as ex:  # noqa: BLE001
                    mostrar_error(f"Error AFIP: {ex}")
                finally:
                    _unregister_shortcuts()
                    _cerrar_dialogo()
                    _done()

            page.run_thread(proceso_facturacion)
            return

        # --- Fallback: comprobante interno .txt (sin AFIP) ---
        comprobante = ""
        if billing_service.activa:
            try:
                comprobante = billing_service.generar_comprobante(venta_id, items, total, metodo_pago)
            except Exception as ex:  # no bloquea la venta
                print(f"facturación: {ex}")
        if imprimir and comprobante:
            from ui.helpers import imprimir_archivo
            ok, msg = imprimir_archivo(comprobante)
            mostrar_exito(f"Venta #{venta_id} OK · {msg}" if ok else f"Venta #{venta_id} OK · {comprobante}")
        else:
            mostrar_exito(f"Venta #{venta_id} registrada ({metodo_pago})" + (f" · {comprobante}" if comprobante else ""))
        detalle_pago = f"Venta #{venta_id} · ${_fmt_ars(total)} · {metodo_pago}"
        if vuelto_activo and metodo_pago == "efectivo":
            try:
                recibido = float((recibe_field.value or "0").replace(",", "."))
                detalle_pago += f" · vuelto ${_fmt_ars(recibido - total)}"
            except ValueError:
                pass
        snack(page, detalle_pago, ok=True)
        _unregister_shortcuts()
        _cerrar_dialogo()
        _done()

    def _done():
        import time as _t
        _t.sleep(0.3)
        on_confirmar()

    def abortar(e=None):
        pagando_qr["cancelado"] = True
        pagando_qr["activo"] = False
        _unregister_shortcuts()
        _cerrar_dialogo()

        def _done():
            import time as _t
            _t.sleep(0.2)
            on_cerrar()
        page.run_thread(_done)

    def on_search_submit(e):
        termino = (search_field.value or "").strip()
        if not termino:
            return
        # Enter agrega el resultado resaltado (por defecto el primero).
        if resultados_termino["valor"] != termino or not resultados_actuales:
            buscar_producto()
        if not resultados_actuales:
            mostrar_error("Producto no encontrado")
            return
        if filtro_dropdown.value == "codigo":
            exactos = [p for p in resultados_actuales if p["codigo"] == termino]
            if len(exactos) == 1:
                agregar_al_carrito(exactos[0])
                return
        agregar_al_carrito(resultados_actuales[indice_seleccionado])

    search_field.on_change = buscar_producto
    search_field.on_submit = on_search_submit

    if vuelto_activo:
        def _on_recibe_change(_e=None):
            try:
                _actualizar_vuelto(round(sum(i["subtotal"] for i in carrito), 2))
            except Exception:
                pass
        recibe_field.on_change = _on_recibe_change

    # Flechas arriba/abajo mueven la selección sin quitar el foco del buscador.
    if sm_manager is not None:
        try:
            sm_manager.register_nav("arrow up", _nav_teclado)
            sm_manager.register_nav("arrow down", _nav_teclado)
        except Exception:
            pass

    # ---- pago QR ----
    qr_estado = ft.Text("", size=12, color=N.GREY_400)
    qr_spin = ft.ProgressRing(width=18, height=18, visible=False)

    def pagar_con_qr(e):
        if pagando_qr["activo"]:
            return
        if not carrito:
            mostrar_error("El carrito está vacío")
            return
        token, _, store_ext, pos_ext = mp_service.credenciales()
        if not (token and store_ext and pos_ext):
            mostrar_error("MP sin configurar: complete .env o Ajustes → Mercado Pago")
            return
        items_qr = _aplicar_recargo(carrito, recargo_mp) if recargo_mp else carrito
        total = round(sum(i["subtotal"] for i in items_qr), 2)
        pagando_qr.update(activo=True, cancelado=False)
        qr_spin.visible = True
        qr_estado.value = (f"Creando orden por ${_fmt_ars(total)} (incluye recargo {recargo_mp:g}%)… "
                           if recargo_mp else
                           f"Creando orden por ${_fmt_ars(total)}… El cliente debe escanear el QR estático.")
        col_izquierda.content = ft.Container(
            content=ft.Column([qr_spin, qr_estado,
                               ft.TextButton("CANCELAR COBRO QR", icon=ft.Icons.CANCEL,
                                             on_click=lambda _: cancelar_qr())],
                              horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            padding=10, border_radius=8)
        page.update()

        def proceso():
            ok = mp_service.crear_orden(total, cb=lambda m: _set_qr(m),
                                        pos_ext=pos_ext, store_ext=store_ext)
            if not ok:
                _fin_qr("Error al crear la orden en Mercado Pago")
                return
            ok = mp_service.verificar_estado(cb=lambda m: _set_qr(m),
                                             cancelar=lambda: pagando_qr["cancelado"],
                                             pos_ext=pos_ext)
            if ok and not pagando_qr["cancelado"]:
                pagando_qr["activo"] = False
                col_izquierda.content = log_box
                page.update()
                confirmar_venta(metodo_pago="mercadopago_qr", emitir_factura=auto_qr)
            elif not pagando_qr["cancelado"]:
                _fin_qr("Tiempo agotado o pago no detectado")

        def _set_qr(m):
            qr_estado.value = m
            try:
                page.update()
            except Exception:
                pass

        def _fin_qr(m):
            pagando_qr["activo"] = False
            col_izquierda.content = log_box
            page.update()
            mostrar_error(m)

        def cancelar_qr():
            pagando_qr["cancelado"] = True
            pagando_qr["activo"] = False
            col_izquierda.content = log_box
            qr_spin.visible = False
            page.update()
            mostrar_error("Pago QR cancelado")

        # exponer cancelar para el botón creado arriba
        pagar_con_qr._cancelar = cancelar_qr  # type: ignore
        page.run_thread(proceso)

    acciones = [ft.TextButton("ABORTAR", on_click=abortar, height=44)]
    if es_qr:
        acciones.append(ft.FilledButton(
            "COBRAR QR (Alt+M)", icon=ft.Icons.QR_CODE_2, height=44,
            on_click=pagar_con_qr, style=BTN_INFO))
    else:
        acciones.append(ft.FilledButton(
            "IMPRIMIR (Alt+C)", icon=ft.Icons.PRINT, height=44,
            on_click=lambda _: confirmar_venta(metodo_pago, imprimir=True,
                                               emitir_factura=auto_efectivo),
            style=BTN_PRIMARIO))
        acciones.append(ft.FilledButton(
            "COBRAR (Alt+E)", icon=ft.Icons.CHECK, height=44,
            on_click=lambda _: confirmar_venta(metodo_pago, imprimir=False,
                                               emitir_factura=auto_efectivo),
            style=BTN_PRIMARIO))

    def _celda_accion(boton):
        return ft.Container(
            content=boton, padding=0,
            col={"xs": 6, "sm": 6, "md": 4, "lg": 4, "xl": 4, "xxl": 4},
        )

    acciones_grid = ft.ResponsiveRow(
        [_celda_accion(b) for b in acciones], spacing=8, run_spacing=8,
    )

    dialog = ft.AlertDialog(
        modal=True,
        on_dismiss=lambda _: _unregister_shortcuts(),
        title=ft.Row([
            ft.Icon(ft.Icons.SHOPPING_CART, color=N.GREEN_700),
            ft.Text("Nueva Venta", size=20, weight=ft.FontWeight.BOLD),
            ft.Container(
                content=ft.Text(metodo_label, size=11, weight=ft.FontWeight.BOLD,
                                color=metodo_color),
                padding=ft.Padding.symmetric(horizontal=8, vertical=2),
                border_radius=20,
                bgcolor=ft.Colors.with_opacity(0.15, metodo_color),
                border=ft.Border.all(1, metodo_color),
            ),
            ft.Container(expand=True),
            ft.Text(f"Modo: {filtro_dropdown.value}", size=12, color=N.GREY_500),
        ]),
        content=ft.Container(
            content=ft.Column([
                ft.Column([
                    ft.Container(height=6),
                    ft.ResponsiveRow([search_field, filtro_dropdown],
                                     spacing=8, run_spacing=8),
                    ft.Text("Resultados (click o Enter para agregar):", size=11, italic=True,
                            color=N.GREY_500),
                    ft.Container(content=resultados_list, border=ft.Border.all(1, N.BLUE_GREY_700),
                                 border_radius=5, padding=5),
                    ft.Divider(),
                    ft.ResponsiveRow([
                        col_izquierda,
                        ft.Column([
                            ft.Row([ft.Icon(ft.Icons.SHOPPING_CART, color=N.GREEN_700, size=20),
                                    ft.Text("CARRITO", size=15, weight=ft.FontWeight.BOLD)]),
                            ft.Container(content=carrito_list,
                                         border=ft.Border.all(1, N.GREEN_700),
                                         border_radius=5, padding=5),
                        ], col={"xs": 12, "sm": 8}, spacing=8),
                    ], spacing=16, run_spacing=12),
                ], scroll=ft.ScrollMode.AUTO, spacing=8, expand=True),
                ft.Divider(height=1),
                ft.ResponsiveRow([
                    ft.Container(
                        content=ft.Column([
                            metodo_header,
                            metodo_detalle_text,
                            ft.Divider(height=1),
                            total_efectivo_text, total_qr_text,
                            total_debito_text, total_credito_text,
                            ft.Row([recibe_field, ft.Container(width=6),
                                    vuelto_text], spacing=4,
                                   vertical_alignment=ft.CrossAxisAlignment.CENTER)],
                            spacing=3, tight=True),
                        col={"xs": 12, "sm": 7}, padding=6),
                    ft.Container(total_panel, col={"xs": 12, "sm": 5},
                                 alignment=ft.Alignment.CENTER_RIGHT),
                ], spacing=12, run_spacing=8),
                acciones_grid,
            ], spacing=8, expand=True),
            height=alto_dialogo, width=ancho_dialogo,
        ),
        inset_padding=12,
        content_padding=ft.Padding.symmetric(horizontal=12, vertical=4),
        open=True,
    )

    # Atajos del modal: Alt+C confirmar imprimiendo, Alt+M cobrar QR,
    # Alt+E confirmar sin imprimir, Alt+D débito, Alt+T crédito
    if sm_manager is not None:
        if es_qr:
            sm_manager.register("m", lambda *_: pagar_con_qr(None))
        else:
            sm_manager.register("c", lambda *_: confirmar_venta(
                metodo_pago, imprimir=True, emitir_factura=auto_efectivo))
            sm_manager.register("e", lambda *_: confirmar_venta(
                metodo_pago, imprimir=False, emitir_factura=auto_efectivo))

    actualizar_carrito()
    return dialog

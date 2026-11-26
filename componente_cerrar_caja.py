"""Arqueo de caja profesional: efectivo esperado vs contado, medios de pago y gastos.

UI para DatabaseManager y ApiClient. La venta y el cierre real se realizan
en el repositorio/servidor, no se calculan a partir de ventas del calendario.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re
from datetime import datetime

import flet as ft
from ui.paleta import N
from ui.helpers import snack as _snack


def _importe(value: str) -> Decimal:
    """Admite $ 1.234,56 (AR), 1234.56 o 1234,56; nunca NaN/Inf."""
    raw = (value or "").strip().replace("$", "").replace(" ", "")
    if not raw:
        raise ValueError("Ingresá el efectivo contado.")
    if not re.fullmatch(r"[0-9.,]+", raw):
        raise ValueError("Ingresá un importe numérico válido.")
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".") if raw.rfind(",") > raw.rfind(".") else raw.replace(",", "")
    elif "," in raw:
        raw = raw.replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", raw):
        raw = raw.replace(".", "")
    try:
        number = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError("El importe contado no es válido.") from exc
    if not number.is_finite() or number < 0:
        raise ValueError("El efectivo contado debe ser mayor o igual a cero.")
    if number.as_tuple().exponent < -2:
        raise ValueError("Ingresá como máximo dos decimales.")
    return number.quantize(Decimal("0.01"))


def _dinero(value) -> str:
    text = f"{float(value):,.2f}"
    return "$ " + text.replace(",", "#").replace(".", ",").replace("#", ".")


def CerrarCajaModal(db_manager, caja_id, on_caja_cerrada, page):
    """Un cierre de caja sin bloqueos silenciosos ni sumas de tarjetas como efectivo."""
    current = {"resumen": None, "busy": False, "cargando": False}

    titulo_fecha = ft.Text(datetime.now().strftime("%d/%m/%Y · %H:%M"),
                           size=12, color=N.GREY_400)
    mensaje = ft.Text("", size=12, color=N.RED_300, visible=False)
    spinner = ft.ProgressRing(width=18, height=18, visible=True)
    resumen_esperado = ft.Text("—", size=30, weight=ft.FontWeight.BOLD, color=N.GREEN_300)
    apertura_txt = ft.Text("—", size=15, weight=ft.FontWeight.BOLD, color=N.TEXT)
    efectivo_txt = ft.Text("—", size=15, weight=ft.FontWeight.BOLD, color=N.TEXT)
    gastos_txt = ft.Text("—", size=15, weight=ft.FontWeight.BOLD, color=N.TEXT)
    ventas_txt = ft.Text("—", size=13, weight=ft.FontWeight.BOLD, color=N.TEXT)
    otras_txt = ft.Text("—", size=13, weight=ft.FontWeight.BOLD, color=N.TEXT)
    nro_ventas_txt = ft.Text("—", size=12, color=N.GREY_400)
    medios = ft.Column(spacing=6, controls=[
        ft.Text("Consultando los medios de pago…", color=N.GREY_400, size=12)
    ])
    gastos_detalle = ft.Column(spacing=6, controls=[
        ft.Text("Consultando gastos…", color=N.GREY_400, size=12)
    ])
    pendientes = ft.Text("", size=12, color=N.ORANGE_300, visible=False)

    contado_field = ft.TextField(
        label="Efectivo contado en el cajón",
        hint_text="Ej.: 1.234,50",
        prefix=ft.Text("$", color=N.GREEN_300),
        keyboard_type=ft.KeyboardType.NUMBER,
        width=310, color=N.TEXT, border_color=N.GREY_700,
        text_size=18,
    )
    diferencia_txt = ft.Text("Ingresá el importe contado", size=14,
                             weight=ft.FontWeight.BOLD, color=N.GREY_400)
    observaciones = ft.TextField(
        label="Observaciones del cierre",
        hint_text="Obligatorias si hay sobrante o faltante",
        multiline=True, min_lines=2, max_lines=3,
        color=N.TEXT, border_color=N.GREY_700, width=650,
    )
    concepto_gasto = ft.TextField(
        label="Concepto", hint_text="Ej.: Retiro de efectivo",
        expand=True, color=N.TEXT, border_color=N.GREY_700,
    )
    monto_gasto = ft.TextField(
        label="Monto", hint_text="0,00", width=130,
        prefix=ft.Text("$", color=N.RED_300),
        keyboard_type=ft.KeyboardType.NUMBER,
        color=N.TEXT, border_color=N.GREY_700,
    )
    formulario_gasto = ft.Container(visible=False, padding=12,
                                    bgcolor=N.BLUE_GREY_800, border_radius=8)
    cerrar_btn = ft.FilledButton(
        "Confirmar cierre de caja", icon=ft.Icons.LOCK,
        disabled=True, height=46,
        style=ft.ButtonStyle(bgcolor=N.RED_700, color=ft.Colors.WHITE),
    )
    actualizar_btn = ft.TextButton("Actualizar", icon=ft.Icons.REFRESH)
    cancelar_btn = ft.TextButton("Volver, sin cerrar")

    def _update():
        try:
            page.update()
        except Exception:
            pass

    def _aviso(texto: str, color: str = N.RED_300):
        mensaje.value = texto
        mensaje.color = color
        mensaje.visible = bool(texto)
        _update()

    def _linea(nombre, valor, color=N.GREY_300):
        return ft.Row([
            ft.Text(nombre, size=12, expand=True, color=N.GREY_300),
            ft.Text(valor, size=12, weight=ft.FontWeight.BOLD, color=color),
        ], spacing=10)

    def _tarjeta(etiqueta, valor, color=N.TEXT):
        return ft.Container(
            content=ft.Column([
                ft.Text(etiqueta, size=11, color=N.GREY_400),
                valor,
            ], spacing=4, tight=True),
            bgcolor=N.BLUE_GREY_800,
            border_radius=10, padding=14, width=210,
        )

    def _snapshot():
        data = current["resumen"]
        return {key: data[key] for key in
                ("efectivo_esperado", "total_ventas", "total_gastos")}

    def actualizar_diferencia(e=None):
        data = current["resumen"]
        valido = False
        if data and not current["busy"] and not current["cargando"]:
            try:
                contado = _importe(contado_field.value or "")
                dif = contado - Decimal(str(data["efectivo_esperado"]))
                if dif == 0:
                    diferencia_txt.value = "Sin diferencia · arqueo correcto"
                    diferencia_txt.color = N.GREEN_300
                elif dif > 0:
                    diferencia_txt.value = "Sobrante: " + _dinero(dif)
                    diferencia_txt.color = N.ORANGE_300
                else:
                    diferencia_txt.value = "Faltante: " + _dinero(abs(dif))
                    diferencia_txt.color = N.RED_300
                valido = (dif == 0 or bool((observaciones.value or "").strip()))
            except ValueError as exc:
                diferencia_txt.value = str(exc)
                diferencia_txt.color = N.GREY_400
        cerrar_btn.disabled = (not valido or bool(data and data["cobros_pendientes"])
                              or current["cargando"] or current["busy"])
        _update()

    contado_field.on_change = actualizar_diferencia
    observaciones.on_change = actualizar_diferencia

    def _mostrar_resumen(data):
        current["resumen"] = data
        apertura_txt.value = _dinero(data["importe_apertura"])
        efectivo_txt.value = _dinero(data["ventas_efectivo"])
        gastos_txt.value = "− " + _dinero(data["total_gastos"])
        resumen_esperado.value = _dinero(data["efectivo_esperado"])
        ventas_txt.value = _dinero(data["total_ventas"])
        otras_txt.value = _dinero(data["ventas_otros_medios"])
        nro_ventas_txt.value = (
            str(data["cantidad_ventas"]) + " ventas de este turno · abierto " +
            str(data["fecha_apertura"])[:16]
        )
        nombres = {
            "efectivo": "Efectivo",
            "mercadopago_qr": "Mercado Pago QR",
            "tarjeta_credito": "Tarjeta de crédito",
            "tarjeta_debito": "Tarjeta de débito",
        }
        medios.controls = [
            _linea(nombres.get(row["metodo_pago"], row["metodo_pago"]),
                   _dinero(row["total"]))
            for row in data.get("ventas_por_medio", [])
        ] or [ft.Text("Todavía no hay ventas en esta caja", color=N.GREY_400, size=12)]
        gastos_detalle.controls = [
            _linea(str(row.get("concepto", "Gasto"))[:65], "− " + _dinero(row["monto"]), N.RED_300)
            for row in data.get("gastos", [])
        ] or [ft.Text("Sin gastos registrados", size=12, color=N.GREY_400)]
        n = int(data["cobros_pendientes"])
        pendientes.visible = n > 0
        pendientes.value = (
            f"Hay {n} cobro(s) IntraShop sin resolver. "
            "La caja no puede cerrarse hasta completarlos o conciliarlos."
            if n else ""
        )
        actualizar_diferencia()

    def cargar_resumen(e=None):
        if current["busy"] or current["cargando"]:
            return
        current["cargando"] = True
        spinner.visible = True
        actualizar_btn.disabled = True
        cerrar_btn.disabled = True
        _aviso("")
        _update()

        def worker():
            try:
                data = db_manager.obtener_resumen_caja(caja_id)
                _mostrar_resumen(data)
            except Exception as exc:
                current["resumen"] = None
                _aviso("No se pudo obtener el arqueo: " + str(exc))
            finally:
                current["cargando"] = False
                spinner.visible = False
                actualizar_btn.disabled = False
                actualizar_diferencia()
                _update()

        page.run_thread(worker)

    def cerrar_modal(e=None):
        if current["busy"]:
            return
        dialog.open = False
        _update()

    def guardar_gasto(e=None):
        if current["busy"] or current["cargando"]:
            return
        concepto = (concepto_gasto.value or "").strip()
        try:
            monto = _importe(monto_gasto.value or "")
            if not concepto or monto <= 0:
                raise ValueError("Indicá concepto e importe mayor a cero.")
        except ValueError as exc:
            _aviso(str(exc))
            return
        current["busy"] = True
        _aviso("")
        guardar_gasto_btn.disabled = True
        cerrar_btn.disabled = True
        _update()

        def worker():
            try:
                result = db_manager.agregar_gasto(caja_id, float(monto), concepto)
                if not result:
                    raise ValueError("No se pudo registrar el gasto.")
                concepto_gasto.value = ""
                monto_gasto.value = ""
                formulario_gasto.visible = False
                current["busy"] = False
                _snack(page, "Gasto registrado en esta caja.", ok=True)
                cargar_resumen()
            except Exception as exc:
                _aviso("No se pudo registrar el gasto: " + str(exc))
            finally:
                current["busy"] = False
                guardar_gasto_btn.disabled = False
                actualizar_diferencia()

        page.run_thread(worker)

    def confirmar_cierre(e=None):
        if current["busy"] or current["cargando"] or not current["resumen"]:
            return
        try:
            contado = _importe(contado_field.value or "")
            diferencia = contado - Decimal(str(current["resumen"]["efectivo_esperado"]))
            obs = (observaciones.value or "").strip()
            if current["resumen"]["cobros_pendientes"]:
                raise ValueError("Hay cobros QR pendientes de resolver en esta caja.")
            if diferencia and not obs:
                raise ValueError("Explicá el faltante o sobrante en Observaciones.")
        except ValueError as exc:
            _aviso(str(exc))
            return

        snapshot = _snapshot()
        current["busy"] = True
        cerrar_btn.disabled = True
        cancelar_btn.disabled = True
        spinner.visible = True
        _aviso("Validando movimientos y cerrando la caja…", N.GREY_300)
        _update()

        def worker():
            try:
                result = db_manager.cerrar_caja_arqueo(
                    caja_id, float(contado), obs, snapshot=snapshot,
                )
                if not result or not result.get("ok"):
                    raise RuntimeError("POS Server no confirmó el cierre.")
                dialog.open = False
                _update()
                _snack(page, "Caja #" + str(caja_id) + " cerrada. Diferencia: " +
                       _dinero(result["diferencia_arqueo"]), ok=True)
                on_caja_cerrada()
            except Exception as exc:
                _aviso("No se pudo cerrar la caja: " + str(exc))
                if "movimientos mientras contabas" in str(exc).lower():
                    current["busy"] = False
                    cargar_resumen()
            finally:
                current["busy"] = False
                spinner.visible = False
                cancelar_btn.disabled = False
                actualizar_diferencia()
                _update()

        page.run_thread(worker)

    def mostrar_form_gasto(e=None):
        formulario_gasto.visible = not formulario_gasto.visible
        _update()

    guardar_gasto_btn = ft.FilledButton("Guardar gasto", on_click=guardar_gasto)
    formulario_gasto.content = ft.Column([
        ft.Row([concepto_gasto, monto_gasto], wrap=True, spacing=12),
        ft.Row([ft.TextButton("Cancelar", on_click=lambda _: mostrar_form_gasto()),
                guardar_gasto_btn],
               alignment=ft.MainAxisAlignment.END),
    ], spacing=8, tight=True)

    actualizar_btn.on_click = cargar_resumen
    cancelar_btn.on_click = cerrar_modal
    cerrar_btn.on_click = confirmar_cierre

    cabecera = ft.Row([
        ft.Column([
            ft.Text("Arqueo y cierre de caja", size=21,
                    weight=ft.FontWeight.BOLD, color=N.TEXT),
            ft.Text("Caja #" + str(caja_id) + " · " +
                    "Contabilizá el efectivo antes de finalizar el turno.",
                    size=12, color=N.GREY_400),
        ], spacing=3, expand=True),
        titulo_fecha,
    ], spacing=10, wrap=True)

    panel_esperado = ft.Container(
        content=ft.Column([
            ft.Text("EFECTIVO ESPERADO EN CAJA", size=11, color=N.GREY_400,
                    weight=ft.FontWeight.BOLD),
            resumen_esperado,
            nro_ventas_txt,
        ], spacing=6, tight=True),
        bgcolor=N.BLUE_GREY_900, padding=18, border_radius=12,
        border=ft.Border.all(1, N.BLUE_GREY_600),
    )
    cuenta = ft.Row([
        _tarjeta("Fondo inicial", apertura_txt),
        _tarjeta("Ventas en efectivo", efectivo_txt),
        _tarjeta("Gastos / retiros", gastos_txt),
    ], spacing=8, wrap=True)

    separador = lambda: ft.Divider(color=N.BLUE_GREY_700, height=8)
    body = ft.Column([
        cabecera,
        ft.Row([spinner, actualizar_btn], spacing=12,
               alignment=ft.MainAxisAlignment.END),
        pendientes,
        panel_esperado,
        cuenta,
        separador(),
        ft.Text("Ventas de este turno", size=14, weight=ft.FontWeight.BOLD, color=N.TEXT),
        ft.Row([
            ft.Text("Total de ventas (todos los medios)", size=12,
                    color=N.GREY_300, expand=True),
            ventas_txt,
        ], spacing=10),
        ft.Row([
            ft.Text("Medios electrónicos (no entran al cajón)", size=12,
                    color=N.GREY_300, expand=True),
            otras_txt,
        ], spacing=10),
        medios,
        separador(),
        ft.Row([
            ft.Text("Gastos registrados", size=14,
                    weight=ft.FontWeight.BOLD, color=N.TEXT, expand=True),
            ft.TextButton("Agregar gasto", icon=ft.Icons.ADD_CIRCLE,
                          on_click=mostrar_form_gasto),
        ], spacing=8),
        gastos_detalle,
        formulario_gasto,
        separador(),
        ft.Text("Conteo físico", size=14, weight=ft.FontWeight.BOLD, color=N.TEXT),
        ft.Row([contado_field, ft.Container(
            content=diferencia_txt, padding=10, expand=True,
        )], spacing=12, wrap=True),
        observaciones,
        mensaje,
    ], spacing=12, scroll=ft.ScrollMode.AUTO)

    viewport_width = float(getattr(page, "width", 0) or 1000)
    viewport_height = float(getattr(page, "height", 0) or 850)
    dialog = ft.AlertDialog(
        modal=True,
        content=ft.Container(
            content=body, width=min(740, max(310, viewport_width - 70)),
            height=min(690, max(320, viewport_height - 170)),
            padding=8,
        ),
        actions=[cancelar_btn, cerrar_btn],
        actions_alignment=ft.MainAxisAlignment.END,
        open=True,
    )
    page.run_thread(cargar_resumen)
    return dialog

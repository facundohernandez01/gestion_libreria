"""Asistente de primer uso (stepper) para cargar los datos de Ajustes."""
from __future__ import annotations

import threading

import flet as ft
from ui.paleta import N

from core.settings import settings
from ui.helpers import snack
from utils.file_dialogs import pick_folder

PASOS = ["Negocio", "Facturación", "Mercado Pago", "Carpetas", "Listo"]


def _marcar_primer_uso(db_manager, activo: bool) -> None:
    try:
        db_manager.marcar_primer_uso(activo)
    except AttributeError:
        db_manager.set_config("PRIMER_USO", "SI" if activo else "NO")


def PrimerUsoView(db_manager, on_finish, page: ft.Page):
    estado = {"paso": 0}

    # ---------- paso 1: negocio ----------
    nombre_field = ft.TextField(
        label="Nombre del negocio *", width=420,
        value=settings.nombre_negocio or db_manager.get_config_value("NOMBRE_NEGOCIO") or "")
    direccion_field = ft.TextField(
        label="Dirección", width=420,
        value=settings.direccion_negocio or db_manager.get_config_value("DIRECCION") or "")
    cuit_field = ft.TextField(
        label="CUIT", width=200,
        value=(db_manager.get_config_value("CUIT") or settings.cuit
               or db_manager.get_config_value("AFIP_CUIT") or settings.afip_cuit or ""))
    telefono_field = ft.TextField(
        label="Teléfono", width=200,
        value=db_manager.get_config_value("TELEFONO") or "")
    recargo_field = ft.TextField(
        label="Recargo % (QR/tarjeta)", width=200,
        value=str(settings.recargo_porcentaje or
                  (db_manager.get_config_value("RECARGO") or "0")),
        keyboard_type=ft.KeyboardType.NUMBER)

    # ---------- paso 2: facturación ----------
    afip_cuit_field = ft.TextField(
        label="CUIT AFIP", width=200,
        value=(db_manager.get_config_value("AFIP_CUIT") or settings.afip_cuit
               or cuit_field.value or ""))
    afip_pv_field = ft.TextField(
        label="Punto de venta", width=150,
        value=str(db_manager.get_config_value("AFIP_PUNTO_VENTA")
                  or settings.afip_punto_venta or 1),
        keyboard_type=ft.KeyboardType.NUMBER)
    afip_tipo_dropdown = ft.Dropdown(
        label="Tipo de factura", width=150,
        value=(db_manager.get_config_value("AFIP_TIPO_FACTURA")
               or settings.afip_tipo_factura or "C").upper(),
        options=[ft.dropdown.Option("A"), ft.dropdown.Option("B"), ft.dropdown.Option("C")])
    _modo_db = db_manager.get_config_value("AFIP_TESTING")
    _testing = (str(_modo_db).strip().lower() in ("1", "si", "sí", "true", "yes", "on")
                if _modo_db not in (None, "") else bool(settings.afip_testing))
    afip_modo_dropdown = ft.Dropdown(
        label="Modo AFIP", width=200,
        value="Homologación" if _testing else "Producción",
        options=[ft.dropdown.Option("Homologación"), ft.dropdown.Option("Producción")])
    _opciones_iva = ["Responsable Inscripto", "Monotributo", "Exento", "Consumidor Final"]
    _cond_cfg = (db_manager.get_config_value("CONDICION_IVA")
                 or settings.condicion_iva or "Consumidor Final").strip()
    _cond_iva = next((o for o in _opciones_iva if o.lower() == _cond_cfg.lower()),
                     "Consumidor Final")
    condicion_iva_dropdown = ft.Dropdown(
        label="Condición frente al IVA", width=240, value=_cond_iva,
        options=[ft.dropdown.Option(o) for o in _opciones_iva])
    iibb_field = ft.TextField(
        label="Ingresos Brutos (Nº)", width=200,
        value=(db_manager.get_config_value("INGRESOS_BRUTOS")
               or settings.ingresos_brutos or ""))
    inicio_actividades_field = ft.TextField(
        label="Inicio de actividades (dd/mm/aaaa)", width=220,
        value=(db_manager.get_config_value("INICIO_ACTIVIDADES")
               or settings.inicio_actividades or ""))
    facturacion_switch = ft.Switch(
        label="Facturación AFIP activa",
        value=(db_manager.get_config_value("FACTURACION_ACTIVA") or "").strip().lower()
        in ("1", "si", "sí", "true", "yes", "on")
        if db_manager.get_config_value("FACTURACION_ACTIVA") not in (None, "")
        else bool(settings.facturacion_activa))

    # ---------- paso 3: mercado pago (opcional) ----------
    mp_token_field = ft.TextField(
        label="Access Token (Mercado Pago)", width=600, password=True,
        can_reveal_password=True,
        value=(db_manager.get_config_value("ACCESS_TOKEN")
               or db_manager.get_config_value("MP_ACCESS_TOKEN")
               or settings.mp_access_token or ""))
    mp_user_field = ft.TextField(
        label="User ID", width=180,
        value=(db_manager.get_config_value("USER_ID")
               or db_manager.get_config_value("MP_USER_ID")
               or settings.mp_user_id or ""))
    mp_store_ext_field = ft.TextField(
        label="Sucursal externa", width=200,
        value=(db_manager.get_config_value("EXTERNAL_STORE_ID")
               or settings.mp_external_store_id or ""))
    mp_pos_ext_field = ft.TextField(
        label="Caja / POS externo", width=200,
        value=(db_manager.get_config_value("EXTERNAL_POS_ID")
               or settings.mp_external_pos_id or ""))
    mp_estado_text = ft.Text("", size=11, color=N.GREY_400)
    mp_btn = ft.OutlinedButton(
        "Vincular y crear sucursal / caja", icon=ft.Icons.LINK,
        on_click=lambda e: _crear_mp())

    def _crear_mp(e=None):
        token = (mp_token_field.value or "").strip()
        uid = (mp_user_field.value or "").strip()
        nombre = (nombre_field.value or "").strip()
        if not token or not uid or not nombre:
            mp_estado_text.value = ("⚠️ Completá Access Token, User ID y "
                                    "nombre del negocio.")
            mp_estado_text.color = N.AMBER_400
            page.update()
            return
        mp_estado_text.value = "⏳ Creando sucursal y caja en Mercado Pago…"
        mp_estado_text.color = N.GREY_400
        mp_btn.disabled = True
        page.update()

        def worker():
            import os

            from services.mercadopago_service import mp_service

            try:
                os.environ["MP_ACCESS_TOKEN"] = token
                os.environ["MP_USER_ID"] = uid
                settings.reload(from_db=False)
                s_ext, p_ext, qr_url, error = mp_service.crear_store_y_pos(nombre)
                if error:
                    mp_estado_text.value = f"❌ {error}"
                    mp_estado_text.color = N.RED_400
                else:
                    mp_store_ext_field.value = s_ext
                    mp_pos_ext_field.value = p_ext
                    mp_estado_text.value = f"✅ Sucursal: {s_ext} · Caja: {p_ext}"
                    mp_estado_text.color = N.GREEN_400
                    try:
                        db_manager.set_config("ACCESS_TOKEN", token)
                        db_manager.set_config("USER_ID", uid)
                        db_manager.set_config("EXTERNAL_STORE_ID", s_ext)
                        db_manager.set_config("EXTERNAL_POS_ID", p_ext)
                        if qr_url:
                            db_manager.set_config("QR_URL", qr_url)
                    except Exception:
                        pass
            except Exception as ex:  # noqa: BLE001
                mp_estado_text.value = f"❌ {ex}"
                mp_estado_text.color = N.RED_400
            finally:
                mp_btn.disabled = False
                try:
                    page.update()
                except Exception:
                    pass

        threading.Thread(target=worker, daemon=True).start()

    # ---------- paso 4: carpetas ----------
    comprobantes_field = ft.TextField(
        label="Comprobantes .txt", width=420,
        value=(db_manager.get_config_value("COMPROBANTES_DIR")
               or settings.comprobantes_path or "comprobantes"))
    tickets_field = ft.TextField(
        label="Tickets PDF / facturas", width=420,
        value=(db_manager.get_config_value("TICKETS_DIR")
               or settings.tickets_path or "tickets"))

    async def _pick_comprobantes(e=None):
        ruta = await pick_folder(page, title="Carpeta de comprobantes .txt",
                                 initial_directory=comprobantes_field.value or None)
        if ruta:
            comprobantes_field.value = ruta
            page.update()

    async def _pick_tickets(e=None):
        ruta = await pick_folder(page, title="Carpeta de tickets / facturas",
                                 initial_directory=tickets_field.value or None)
        if ruta:
            tickets_field.value = ruta
            page.update()

    # ---------- cabecera del stepper ----------
    circulos: list[ft.Container] = []
    etiquetas: list[ft.Text] = []
    for i, nombre in enumerate(PASOS):
        circulos.append(ft.Container(
            content=ft.Text(str(i + 1), size=13, weight=ft.FontWeight.BOLD,
                            color=ft.Colors.WHITE),
            width=32, height=32, border_radius=16,
            bgcolor=N.BLUE_700 if i == 0 else N.GREY_700,
            alignment=ft.Alignment.CENTER,
        ))
        etiquetas.append(ft.Text(
            nombre, size=12,
            color=ft.Colors.WHITE if i == 0 else N.GREY_500,
            weight=ft.FontWeight.BOLD if i == 0 else ft.FontWeight.NORMAL,
        ))

    fila_pasos = ft.Row([], spacing=6, alignment=ft.MainAxisAlignment.CENTER)
    for i in range(len(PASOS)):
        if i:
            fila_pasos.controls.append(
                ft.Container(width=38, height=2, bgcolor=N.GREY_700))
        fila_pasos.controls.append(
            ft.Column([circulos[i], etiquetas[i]], spacing=4,
                      horizontal_alignment=ft.CrossAxisAlignment.CENTER))

    # ---------- contenidos ----------
    paso_negocio = ft.Column([
        ft.Text("Datos del negocio", size=18, weight=ft.FontWeight.BOLD,
                color=N.BLUE_400),
        ft.Text("Estos datos aparecen en tickets y reportes. Podés cambiarlos luego en Ajustes.",
                size=12, color=N.GREY_500),
        ft.Container(height=6),
        nombre_field, direccion_field,
        ft.Row([cuit_field, telefono_field], spacing=10),
        recargo_field,
    ], spacing=10, scroll=ft.ScrollMode.AUTO, expand=True)

    paso_facturacion = ft.Column([
        ft.Text("Facturación AFIP (opcional)", size=18, weight=ft.FontWeight.BOLD,
                color=N.CYAN_400),
        ft.Text("Si no facturás electrónicamente, podés dejar esto como está.",
                size=12, color=N.GREY_500),
        ft.Container(height=6),
        ft.Row([afip_cuit_field, afip_pv_field, afip_tipo_dropdown], spacing=10, wrap=True),
        ft.Row([condicion_iva_dropdown, iibb_field, inicio_actividades_field],
               spacing=10, wrap=True),
        afip_modo_dropdown,
        facturacion_switch,
    ], spacing=10, scroll=ft.ScrollMode.AUTO, expand=True)

    paso_mp = ft.Column([
        ft.Text("Mercado Pago QR (opcional)", size=18, weight=ft.FontWeight.BOLD,
                color=N.ORANGE_400),
        ft.Text("Si cobrás con QR, ingresá tus credenciales y creá la sucursal y caja. "
                "Si no, podés omitirlo y configurarlo luego en Ajustes.",
                size=12, color=N.GREY_500),
        ft.Container(height=6),
        mp_token_field,
        ft.Row([mp_user_field, mp_store_ext_field, mp_pos_ext_field],
               spacing=10, wrap=True),
        mp_btn,
        mp_estado_text,
    ], spacing=10, scroll=ft.ScrollMode.AUTO, expand=True)

    paso_carpetas = ft.Column([
        ft.Text("Carpetas de comprobantes", size=18, weight=ft.FontWeight.BOLD,
                color=N.ORANGE_400),
        ft.Text("Podés dejar las rutas por defecto y cambiarlas después.",
                size=12, color=N.GREY_500),
        ft.Container(height=6),
        ft.Row([comprobantes_field,
                ft.IconButton(icon=ft.Icons.FOLDER_OPEN, tooltip="Elegir carpeta",
                              on_click=_pick_comprobantes)], spacing=6),
        ft.Row([tickets_field,
                ft.IconButton(icon=ft.Icons.FOLDER_OPEN, tooltip="Elegir carpeta",
                              on_click=_pick_tickets)], spacing=6),
    ], spacing=10, scroll=ft.ScrollMode.AUTO, expand=True)

    resumen_text = ft.Text("", size=13, color=ft.Colors.WHITE)
    paso_listo = ft.Column([
        ft.Icon(ft.Icons.CHECK_CIRCLE, size=60, color=N.GREEN_400),
        ft.Text("¡Todo listo!", size=20, weight=ft.FontWeight.BOLD),
        ft.Text("Revisá el resumen y presioná Finalizar para comenzar a usar el sistema.",
                size=12, color=N.GREY_500, text_align=ft.TextAlign.CENTER),
        resumen_text,
    ], spacing=12, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        scroll=ft.ScrollMode.AUTO, expand=True)

    contenidos = [paso_negocio, paso_facturacion, paso_mp, paso_carpetas,
                  paso_listo]
    contenedor_paso = ft.Container(
        content=contenidos[0], height=330, padding=16,
        bgcolor=ft.Colors.with_opacity(0.05, N.BLUE_GREY_800),
        border_radius=10, border=ft.Border.all(1, N.BLUE_GREY_700),
    )

    btn_anterior = ft.OutlinedButton("Anterior", icon=ft.Icons.ARROW_BACK)
    btn_siguiente = ft.FilledButton("Siguiente", icon=ft.Icons.ARROW_FORWARD)
    btn_finalizar = ft.FilledButton("Finalizar", icon=ft.Icons.CHECK,
                                    style=ft.ButtonStyle(bgcolor=N.GREEN_700,
                                                         color=ft.Colors.WHITE),
                                    visible=False)

    def _actualizar_resumen():
        resumen_text.value = (
            f"Negocio: {nombre_field.value or '-'}\n"
            f"CUIT: {cuit_field.value or '-'}\n"
            f"Recargo: {recargo_field.value or '0'}%\n"
            f"AFIP: {'Homologación' if afip_modo_dropdown.value == 'Homologación' else 'Producción'} "
            f"- PV {afip_pv_field.value or '1'} - Factura {afip_tipo_dropdown.value or 'C'}\n"
            f"Mercado Pago: {'configurado' if (mp_token_field.value or '').strip() and (mp_user_field.value or '').strip() else 'omitido'}\n"
            f"Comprobantes: {comprobantes_field.value or '-'}\n"
            f"Tickets: {tickets_field.value or '-'}"
        )

    def _render():
        i = estado["paso"]
        for j in range(len(PASOS)):
            activo = j == i
            completado = j < i
            circulos[j].bgcolor = (N.GREEN_700 if completado else
                                   N.BLUE_700 if activo else N.GREY_700)
            circulos[j].content.value = "✓" if completado else str(j + 1)
            etiquetas[j].color = (N.GREEN_400 if completado else
                                  ft.Colors.WHITE if activo else N.GREY_500)
            etiquetas[j].weight = ft.FontWeight.BOLD if activo else ft.FontWeight.NORMAL
        contenedor_paso.content = contenidos[i]
        btn_anterior.visible = i > 0
        btn_siguiente.visible = i < len(PASOS) - 1
        btn_finalizar.visible = i == len(PASOS) - 1
        if i == len(PASOS) - 1:
            _actualizar_resumen()
        page.update()

    def _validar_negocio() -> bool:
        if not (nombre_field.value or "").strip():
            snack(page, "Ingresá el nombre del negocio", ok=False)
            return False
        return True

    def _siguiente(e=None):
        if estado["paso"] == 0 and not _validar_negocio():
            return
        if estado["paso"] < len(PASOS) - 1:
            estado["paso"] += 1
            _render()

    def _anterior(e=None):
        if estado["paso"] > 0:
            estado["paso"] -= 1
            _render()

    def _guardar(e=None):
        if not _validar_negocio():
            estado["paso"] = 0
            _render()
            return
        try:
            recargo = float((recargo_field.value or "0").replace(",", "."))
        except ValueError:
            recargo = 0.0
        db_manager.set_config("NOMBRE_NEGOCIO", nombre_field.value.strip())
        db_manager.set_config("DIRECCION", (direccion_field.value or "").strip())
        db_manager.set_config("CUIT", (cuit_field.value or "").strip())
        db_manager.set_config("TELEFONO", (telefono_field.value or "").strip())
        db_manager.set_config("RECARGO", str(recargo))
        db_manager.set_config("AFIP_CUIT", (afip_cuit_field.value or cuit_field.value or "").strip())
        db_manager.set_config("CONDICION_IVA", condicion_iva_dropdown.value or "Consumidor Final")
        db_manager.set_config("INGRESOS_BRUTOS", (iibb_field.value or "").strip())
        db_manager.set_config("INICIO_ACTIVIDADES", (inicio_actividades_field.value or "").strip())
        db_manager.set_config("AFIP_PUNTO_VENTA", (afip_pv_field.value or "1").strip())
        db_manager.set_config("AFIP_TIPO_FACTURA", (afip_tipo_dropdown.value or "C").upper())
        db_manager.set_config("AFIP_TESTING",
                              "SI" if afip_modo_dropdown.value == "Homologación" else "NO")
        db_manager.set_config("FACTURACION_ACTIVA", "SI" if facturacion_switch.value else "NO")
        mp_token = (mp_token_field.value or "").strip()
        mp_uid = (mp_user_field.value or "").strip()
        mp_store_ext = (mp_store_ext_field.value or "").strip()
        mp_pos_ext = (mp_pos_ext_field.value or "").strip()
        if any((mp_token, mp_uid, mp_store_ext, mp_pos_ext)):
            db_manager.set_config("ACCESS_TOKEN", mp_token)
            db_manager.set_config("USER_ID", mp_uid)
            db_manager.set_config("EXTERNAL_STORE_ID", mp_store_ext)
            db_manager.set_config("EXTERNAL_POS_ID", mp_pos_ext)
            if mp_token and mp_uid and mp_store_ext and mp_pos_ext:
                db_manager.set_config("MP_ACTIVO", "SI")
        db_manager.set_config("COMPROBANTES_DIR", (comprobantes_field.value or "").strip())
        db_manager.set_config("TICKETS_DIR", (tickets_field.value or "").strip())
        _marcar_primer_uso(db_manager, False)
        try:
            settings.reload()
        except Exception:
            pass
        snack(page, "Configuración inicial guardada", ok=True)
        on_finish()

    def _omitir(e=None):
        _marcar_primer_uso(db_manager, False)
        on_finish()

    btn_siguiente.on_click = _siguiente
    btn_anterior.on_click = _anterior
    btn_finalizar.on_click = _guardar

    contenido = ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Icon(ft.Icons.ROCKET_LAUNCH, size=30, color=N.GREEN_400),
                ft.Column([
                    ft.Text("CONFIGURACIÓN INICIAL", size=22, weight=ft.FontWeight.BOLD),
                    ft.Text("Completá estos datos para empezar", size=12,
                            color=N.GREY_500),
                ], spacing=2, expand=True),
            ], spacing=12),
            ft.Container(height=6),
            fila_pasos,
            ft.Container(height=6),
            contenedor_paso,
            ft.Row([
                btn_anterior,
                ft.Container(expand=True),
                ft.TextButton("Omitir por ahora", on_click=_omitir),
                btn_siguiente,
                btn_finalizar,
            ], spacing=10),
        ], spacing=12, scroll=ft.ScrollMode.AUTO, expand=True),
        width=780, padding=24,
        bgcolor=ft.Colors.with_opacity(0.03, N.BLUE_GREY_900),
        border_radius=12,
    )

    return ft.Container(
        content=contenido,
        alignment=ft.Alignment.CENTER,
        expand=True,
        padding=20,
    )

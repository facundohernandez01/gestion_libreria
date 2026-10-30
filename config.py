"""Ajustes: datos del negocio + Mercado Pago (layout por secciones del build).

- Secciones: Datos del Negocio / Credenciales MP / Configuración de Ventas /
  Gestión de POS / Resultado / Panel QR.
- Usa services.mercadopago_service + core.settings + ui.helpers.
- Impresión de QR multiplataforma.
"""
import asyncio
import os
import threading

import flet as ft
from ui.paleta import N

from core.settings import settings
from services.mercadopago_service import mp_service
from ui.helpers import cerrar_dialogo, imprimir_archivo, snack
from utils.file_dialogs import agregar_extension, pick_file, pick_folder, save_file


def ConfigModal(page: ft.Page):
    from database_manager import DatabaseManager

    db = DatabaseManager()
    mp_service.sincronizar_store_id()
    cfg = db.get_all_config()

    # ---------- campos ----------
    nombre_negocio_field = ft.TextField(
        label="Razón social / Nombre del negocio",
        value=settings.nombre_negocio or cfg.get("NOMBRE_NEGOCIO", ""), width=400)
    direccion_field = ft.TextField(
        label="Domicilio comercial",
        value=settings.direccion_negocio or cfg.get("DIRECCION", ""), width=400)
    token_field = ft.TextField(
        label="Access Token (MP)",
        value=settings.mp_access_token or cfg.get("ACCESS_TOKEN", ""),
        width=400, password=True, can_reveal_password=True)
    user_field = ft.TextField(
        label="User ID (MP)",
        value=settings.mp_user_id or cfg.get("USER_ID", ""), width=400)
    # ---------- campos ----------
    def _cfg_bool(key: str, attr: str, default: bool = False) -> bool:
        val = cfg.get(key)
        if val not in (None, ""):
            return str(val).strip().lower() in ("1", "true", "yes", "si", "sí", "on")
        return bool(getattr(settings, attr, default))

    recargo_field = ft.TextField(
        label="Recargo Mercado Pago / QR (%)",
        value=str(settings.recargo_porcentaje if settings.recargo_porcentaje
                  else (cfg.get("RECARGO", "0") or "0")),
        width=400, keyboard_type=ft.KeyboardType.NUMBER)
    recargo_debito_field = ft.TextField(
        label="Recargo tarjeta de débito (%)",
        value=str(settings.recargo_debito if settings.recargo_debito
                  else (cfg.get("RECARGO_DEBITO", "0") or "0")),
        width=400, keyboard_type=ft.KeyboardType.NUMBER)
    recargo_credito_field = ft.TextField(
        label="Recargo tarjeta de crédito (%)",
        value=str(settings.recargo_credito if settings.recargo_credito
                  else (cfg.get("RECARGO_CREDITO", "0") or "0")),
        width=400, keyboard_type=ft.KeyboardType.NUMBER)
    mp_activo_switch = ft.Switch(
        label="Mercado Pago (QR) activo",
        value=_cfg_bool("MP_ACTIVO", "mp_activo", True))
    debito_activo_switch = ft.Switch(
        label="Tarjeta de débito activa",
        value=_cfg_bool("TARJETA_DEBITO_ACTIVO", "tarjeta_debito_activo", True))
    credito_activo_switch = ft.Switch(
        label="Tarjeta de crédito activa",
        value=_cfg_bool("TARJETA_CREDITO_ACTIVO", "tarjeta_credito_activo", True))
    vuelto_switch = ft.Switch(
        label="Vuelto: pedir con cuánto paga y mostrar el vuelto",
        value=_cfg_bool("VUELTO_ACTIVO", "vuelto_activo", False))
    login_user_field = ft.TextField(
        label="Usuario de acceso", width=220,
        value=cfg.get("LOGIN_USUARIO") or "admin")
    login_pass_field = ft.TextField(
        label="Clave de acceso", width=220, password=True,
        can_reveal_password=True, value=cfg.get("LOGIN_CLAVE") or "admin")
    resultado_text = ft.Text("", size=12, color=N.GREEN_400)

    # ---------- campos AFIP ----------
    afip_cuit_field = ft.TextField(
        label="CUIT del emisor", width=200,
        value=cfg.get("AFIP_CUIT") or settings.afip_cuit or settings.cuit or "")
    afip_pv_field = ft.TextField(
        label="Punto de Venta", width=160,
        value=str(cfg.get("AFIP_PUNTO_VENTA") or settings.afip_punto_venta or 1),
        keyboard_type=ft.KeyboardType.NUMBER)
    afip_tipo_dropdown = ft.Dropdown(
        width=160, label="Tipo factura",
        value=(cfg.get("AFIP_TIPO_FACTURA") or settings.afip_tipo_factura or "C").upper(),
        options=[ft.dropdown.Option("A"), ft.dropdown.Option("B"), ft.dropdown.Option("C")])
    afip_modo_dropdown = ft.Dropdown(
        width=220, label="Modo AFIP",
        value="Homologación" if _cfg_bool("AFIP_TESTING", "afip_testing", True) else "Producción",
        options=[ft.dropdown.Option("Homologación"), ft.dropdown.Option("Producción")])

    _opciones_iva = ["Responsable Inscripto", "Monotributo", "Exento", "Consumidor Final"]
    _cond_cfg = (settings.condicion_iva or cfg.get("CONDICION_IVA")
                 or "Consumidor Final").strip()
    _cond_iva = next((o for o in _opciones_iva if o.lower() == _cond_cfg.lower()),
                     "Consumidor Final")
    condicion_iva_dropdown = ft.Dropdown(
        width=260, label="Condición frente al IVA", value=_cond_iva,
        options=[ft.dropdown.Option(o) for o in _opciones_iva])
    iibb_field = ft.TextField(
        label="Ingresos Brutos (Nº)", width=220,
        value=settings.ingresos_brutos or cfg.get("INGRESOS_BRUTOS", ""))
    inicio_actividades_field = ft.TextField(
        label="Inicio de actividades (dd/mm/aaaa)", width=240,
        value=settings.inicio_actividades or cfg.get("INICIO_ACTIVIDADES", ""))
    import os as _os
    _default_cert = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "certificados", "wsaa.crt")
    _default_key = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "certificados", "wsaa.key")

    # Resolve defaults: DB > .env > default path
    _cert_val = cfg.get("AFIP_CERT_FILE") or settings.afip_cert_file or ""
    _key_val = cfg.get("AFIP_KEY_FILE") or settings.afip_key_file or ""
    if not _cert_val:
        _cert_val = _default_cert
    if not _key_val:
        _key_val = _default_key

    afip_cert_field = ft.TextField(
        label="Certificado (.crt)", width=340,
        value=_cert_val, read_only=False)
    afip_key_field = ft.TextField(
        label="Clave privada (.key)", width=340,
        value=_key_val, read_only=False)

    async def _pick_cert(e=None):
        picked = await pick_file(page, title="Seleccionar certificado (.crt)",
                                 extensions=["crt", "pem", "cer"])
        if picked:
            afip_cert_field.value = picked
            _actualizar_estado_cert()
            page.update()

    async def _pick_key(e=None):
        picked = await pick_file(page, title="Seleccionar clave privada (.key)",
                                 extensions=["key", "pem"])
        if picked:
            afip_key_field.value = picked
            page.update()

    cert_row = ft.Row([
        afip_cert_field,
        ft.IconButton(icon=ft.Icons.FOLDER_OPEN, tooltip="Seleccionar certificado",
                      on_click=_pick_cert),
    ], spacing=6)
    key_row = ft.Row([
        afip_key_field,
        ft.IconButton(icon=ft.Icons.FOLDER_OPEN, tooltip="Seleccionar clave",
                      on_click=_pick_key),
    ], spacing=6)
    # keep references for backward compat with sección (which uses cert_row/key_row)
    cert_row.visible = True
    key_row.visible = True

    afip_cert_status = ft.Text("", size=12, color=N.GREY_400)

    def _estado_certificado(ruta: str):
        import os as _os
        from datetime import datetime as _dt

        ruta = (ruta or "").strip()
        if not ruta or not _os.path.exists(ruta):
            return "Certificado: no encontrado", N.RED_400
        try:
            from cryptography import x509
            from cryptography.hazmat.backends import default_backend

            with open(ruta, "rb") as _f:
                cert = x509.load_pem_x509_certificate(_f.read(), default_backend())
            ahora = _dt.utcnow()
            nb = getattr(cert, "not_valid_before", None)
            na = getattr(cert, "not_valid_after", None)
            if nb is None or na is None:
                return "Certificado: no se pudo leer la vigencia", N.GREY_400
            if ahora < nb:
                return (f"Certificado: aún no vigente (desde "
                        f"{nb.strftime('%d/%m/%Y')})"), N.ORANGE_400
            if ahora > na:
                return (f"Certificado: VENCIDO el {na.strftime('%d/%m/%Y')}"), N.RED_400
            return (f"Certificado: VIGENTE, vence el {na.strftime('%d/%m/%Y')}"), N.GREEN_400
        except Exception as _ex:  # noqa: BLE001
            return f"Certificado: error al leer ({_ex})", N.RED_400

    def _actualizar_estado_cert(e=None):
        texto, color = _estado_certificado(afip_cert_field.value)
        afip_cert_status.value = texto
        afip_cert_status.color = color
        try:
            page.update()
        except Exception:
            pass

    _actualizar_estado_cert()
    afip_cert_field.on_change = lambda _e: _actualizar_estado_cert()

    facturacion_activa_switch = ft.Switch(
        label="Facturación AFIP activa", value=_cfg_bool("FACTURACION_ACTIVA", "facturacion_activa", True))
    facturar_qr_switch = ft.Switch(
        label="Facturar automáticamente en cobros QR", value=_cfg_bool("FACTURAR_AUTO_QR", "facturar_auto_qr", False))
    facturar_efectivo_switch = ft.Switch(
        label="Facturar automáticamente en ventas efectivo", value=_cfg_bool("FACTURAR_AUTO_EFECTIVO", "facturar_auto_efectivo", False))

    # ---------- campos RED / multi-usuario ----------
    _modo_cfg = (cfg.get("MODO_RED") or settings.modo_red or "local").strip().lower()
    if _modo_cfg not in ("local", "servidor", "cliente"):
        _modo_cfg = "local"
    red_modo_dropdown = ft.Dropdown(
        width=180, label="Modo de red", value=_modo_cfg,
        options=[ft.dropdown.Option("local", "Local"),
                 ft.dropdown.Option("servidor", "Servidor"),
                 ft.dropdown.Option("cliente", "Cliente")])
    red_url_field = ft.TextField(
        label="Dirección del servidor", width=340,
        value=cfg.get("SERVER_URL") or settings.server_url or "http://127.0.0.1:8000")
    red_estado_text = ft.Text("", size=12, color=N.GREEN_400)
    red_modo_activo = ft.Text("● Comprobando modo de conexión…", size=13, weight=ft.FontWeight.BOLD, color=N.AMBER_400)

    def comprobar_modo_activo(e=None):
        from core.db_factory import modo_actual, _server_url
        import httpx
        modo = modo_actual()
        if modo == "local":
            red_modo_activo.value = "● LOCAL ACTIVO · Base de datos de esta terminal"
            red_modo_activo.color = N.GREEN_400
        else:
            url = _server_url() if modo == "cliente" else "http://127.0.0.1:" + str(settings.api_port)
            try:
                respuesta = httpx.get(url.rstrip("/") + "/health", timeout=2.5)
                if respuesta.status_code == 200:
                    red_modo_activo.value = "● " + modo.upper() + " ACTIVO · " + url
                    red_modo_activo.color = N.GREEN_400
                else:
                    raise RuntimeError("HTTP " + str(respuesta.status_code))
            except Exception:
                red_modo_activo.value = "● " + modo.upper() + " CONFIGURADO · Sin conexión a " + url
                red_modo_activo.color = N.RED_400
        if red_modo_dropdown.value != modo:
            red_modo_activo.value += " · Cambios sin guardar"
        page.update()


    def _escanear_red(e=None):
        red_estado_text.value = "🔍 Escaneando la red…"
        page.update()

        def worker():
            from server_manager import escanear_servidor

            try:
                encontrados = escanear_servidor(puerto=int(cfg.get("API_PORT") or settings.api_port or 8000))
            except Exception as ex:  # noqa: BLE001
                encontrados = []
                red_estado_text.value = f"❌ {ex}"
            if encontrados:
                red_url_field.value = encontrados[0]
                red_estado_text.value = f"✅ Servidor detectado: {encontrados[0]}"
            else:
                red_estado_text.value = "⚠️ No se detectó ningún servidor. Ingrése la IP manualmente."
            page.update()

        threading.Thread(target=worker, daemon=True).start()

    def _info_servidor() -> dict:
        servicio_instalado = False
        servicio_corriendo = False
        try:
            import windows_service as wsp

            if wsp.is_windows():
                servicio_instalado = wsp.esta_instalado()
                if servicio_instalado:
                    servicio_corriendo = wsp.esta_corriendo()
        except Exception:
            pass
        en_proceso = False
        try:
            from server_manager import server_manager

            en_proceso = bool(server_manager.activo)
        except Exception:
            pass
        activo = servicio_corriendo or en_proceso
        if servicio_corriendo:
            descripcion = ("✅ Servicio Windows en ejecución "
                           "(sigue activo al cerrar la app).")
        elif en_proceso:
            try:
                descripcion = f"✅ Servidor activo en {server_manager.url()}"
            except Exception:
                descripcion = "✅ Servidor activo."
        elif servicio_instalado:
            descripcion = "⏸️ Servicio Windows instalado, detenido."
        else:
            descripcion = "Servidor detenido."
        return {
            "activo": activo,
            "servicio_instalado": servicio_instalado,
            "servicio_corriendo": servicio_corriendo,
            "en_proceso": en_proceso,
            "descripcion": descripcion,
        }

    def _actualizar_controles_servidor(mensaje: str | None = None) -> None:
        info = _info_servidor()
        red_estado_text.value = mensaje or info["descripcion"]
        btn_encender.visible = not info["activo"]
        btn_detener.visible = info["activo"]
        btn_quitar.visible = info["servicio_instalado"]
        if not info["activo"]:
            if info["servicio_instalado"]:
                btn_encender.content = "🖥️ Iniciar servicio"
            elif os.name == "nt":
                btn_encender.content = "🖥️ Instalar y encender servicio"
            else:
                btn_encender.content = "🖥️ Encender servidor"
        try:
            page.update()
        except Exception:
            pass

    def _encender_servidor(e=None):
        puerto = int(cfg.get("API_PORT") or settings.api_port or 8000)
        red_estado_text.value = "⏳ Iniciando servidor…"
        page.update()

        def worker():
            mensaje = None
            try:
                if os.name == "nt":
                    import windows_service as wsp

                    if wsp.esta_instalado():
                        if not wsp.esta_corriendo() and not wsp.iniciar_con_elevacion():
                            raise RuntimeError("El servicio no pudo iniciarse.")
                        mensaje = ("✅ Servicio Windows activo (inicio automático, "
                                   "sigue funcionando al cerrar la app).")
                    else:
                        if not wsp.instalar_con_elevacion():
                            raise RuntimeError("El servicio no quedó activo.")
                        mensaje = ("✅ Servicio Windows instalado y activo "
                                   "(inicio automático, sigue funcionando al cerrar la app).")
                else:
                    from server_manager import server_manager

                    url = server_manager.iniciar(host=settings.api_host, port=puerto)
                    mensaje = f"✅ Servidor activo en {url}"
            except Exception as ex:  # noqa: BLE001
                mensaje = f"❌ No se pudo activar el servidor: {ex}"
            _actualizar_controles_servidor(mensaje)

        threading.Thread(target=worker, daemon=True).start()

    def _detener_servidor(e=None):
        red_estado_text.value = "⏳ Deteniendo servidor…"
        page.update()

        def worker():
            detenido = False
            error = None
            try:
                import windows_service as wsp

                if wsp.is_windows() and wsp.esta_instalado():
                    if wsp.detener_con_elevacion():
                        detenido = True
                    else:
                        error = "el servicio no se detuvo"
            except Exception as ex:  # noqa: BLE001
                error = str(ex)
            try:
                from server_manager import server_manager

                if server_manager.activo:
                    server_manager.detener()
                    detenido = True
            except Exception:  # noqa: BLE001
                pass
            if error:
                mensaje = f"❌ No se pudo detener el servidor: {error}"
            else:
                mensaje = ("⏹️ Servidor detenido." if detenido
                           else "ℹ️ El servidor ya estaba detenido.")
            _actualizar_controles_servidor(mensaje)

        threading.Thread(target=worker, daemon=True).start()

    def _quitar_servicio(e=None):
        def worker():
            try:
                import windows_service as wsp

                if wsp.is_windows() and wsp.esta_instalado():
                    if wsp.desinstalar_con_elevacion():
                        mensaje = ("🗑️ Servicio desinstalado "
                                   "(no volverá a iniciar solo).")
                    else:
                        mensaje = "❌ No se pudo desinstalar el servicio."
                else:
                    mensaje = "ℹ️ No hay servicio instalado."
            except Exception as ex:  # noqa: BLE001
                mensaje = f"❌ Error: {ex}"
            _actualizar_controles_servidor(mensaje)

        threading.Thread(target=worker, daemon=True).start()

    # ---------- campos directorios de comprobantes ----------
    async def _pick_dir_comprobantes(e=None):
        picked = await pick_folder(page, title="Carpeta de comprobantes .txt",
                                   initial_directory=comprobantes_dir_field.value or None)
        if picked:
            comprobantes_dir_field.value = picked
            page.update()

    async def _pick_dir_tickets(e=None):
        picked = await pick_folder(page, title="Carpeta de tickets PDF / facturas",
                                   initial_directory=tickets_dir_field.value or None)
        if picked:
            tickets_dir_field.value = picked
            page.update()

    comprobantes_dir_field = ft.TextField(
        label="Guardar comprobantes .txt (ventas no facturadas)", width=340,
        value=cfg.get("COMPROBANTES_DIR") or settings.comprobantes_path)
    tickets_dir_field = ft.TextField(
        label="Guardar tickets PDF / facturas emitidas", width=340,
        value=cfg.get("TICKETS_DIR") or settings.tickets_path)

    comprobantes_dir_row = ft.Row([
        comprobantes_dir_field,
        ft.IconButton(icon=ft.Icons.FOLDER_OPEN, tooltip="Elegir carpeta de comprobantes .txt",
                      on_click=_pick_dir_comprobantes),
    ], spacing=6)
    tickets_dir_row = ft.Row([
        tickets_dir_field,
        ft.IconButton(icon=ft.Icons.FOLDER_OPEN, tooltip="Elegir carpeta de tickets PDF",
                      on_click=_pick_dir_tickets),
    ], spacing=6)

    def _guardar_afip_en_db():
        cuit_emisor = afip_cuit_field.value.strip()
        db.set_config("AFIP_CUIT", cuit_emisor)
        db.set_config("CUIT", cuit_emisor)
        db.set_config("CONDICION_IVA", condicion_iva_dropdown.value or "Consumidor Final")
        db.set_config("INGRESOS_BRUTOS", iibb_field.value.strip())
        db.set_config("INICIO_ACTIVIDADES", inicio_actividades_field.value.strip())
        db.set_config("AFIP_PUNTO_VENTA", afip_pv_field.value.strip() or "1")
        db.set_config("AFIP_TIPO_FACTURA", (afip_tipo_dropdown.value or "C").upper())
        db.set_config("AFIP_TESTING", "SI" if afip_modo_dropdown.value == "Homologación" else "NO")
        db.set_config("AFIP_CERT_FILE", afip_cert_field.value.strip())
        db.set_config("AFIP_KEY_FILE", afip_key_field.value.strip())
        db.set_config("FACTURACION_ACTIVA", "SI" if facturacion_activa_switch.value else "NO")
        db.set_config("FACTURAR_AUTO_QR", "SI" if facturar_qr_switch.value else "NO")
        db.set_config("FACTURAR_AUTO_EFECTIVO", "SI" if facturar_efectivo_switch.value else "NO")
        try:
            import configwsfe

            configwsfe.reload()
        except Exception:
            pass

    def _guardar_ventas_en_db():
        db.set_config("RECARGO", recargo_field.value.strip() or "0")
        db.set_config("RECARGO_DEBITO", recargo_debito_field.value.strip() or "0")
        db.set_config("RECARGO_CREDITO", recargo_credito_field.value.strip() or "0")
        db.set_config("MP_ACTIVO", "SI" if mp_activo_switch.value else "NO")
        db.set_config("TARJETA_DEBITO_ACTIVO", "SI" if debito_activo_switch.value else "NO")
        db.set_config("TARJETA_CREDITO_ACTIVO", "SI" if credito_activo_switch.value else "NO")
        db.set_config("VUELTO_ACTIVO", "SI" if vuelto_switch.value else "NO")

    def _guardar_seguridad_en_db():
        usuario = (login_user_field.value or "").strip() or "admin"
        clave = (login_pass_field.value or "").strip() or "admin"
        db.set_config("LOGIN_USUARIO", usuario)
        db.set_config("LOGIN_CLAVE", clave)
        # Mantener sincronizado el usuario ADMIN de la tabla usuarios.
        try:
            rol_admin = next((r for r in db.listar_roles() if r.get("es_admin")),
                             None)
            admin_user = next((u for u in db.listar_usuarios()
                               if u.get("es_admin")), None)
            if rol_admin:
                datos = {
                    "usuario": usuario, "clave": clave,
                    "nombre": (admin_user or {}).get("nombre") or "Administrador",
                    "rol_id": rol_admin["id"], "activo": True,
                }
                if admin_user:
                    datos["id"] = admin_user["id"]
                db.guardar_usuario(datos)
        except Exception:
            pass

    def _guardar_red_en_db():
        db.set_config("MODO_RED", (red_modo_dropdown.value or "local").lower())
        db.set_config("SERVER_URL", red_url_field.value.strip())
        db.set_config("COMPROBANTES_DIR", comprobantes_dir_field.value.strip())
        db.set_config("TICKETS_DIR", tickets_dir_field.value.strip())
        try:
            settings.reload()
        except Exception:
            pass


    qr_url_saved = settings.mp_qr_url or cfg.get("QR_URL", "")
    qr_image = ft.Image(src=qr_url_saved or None, width=140, height=140,
                        fit=ft.BoxFit.CONTAIN)
    pos_dropdown = ft.Dropdown(width=350)
    pos_list: list = []

    external_pos_id_saved = settings.mp_external_pos_id or cfg.get("EXTERNAL_POS_ID", "")
    external_store_id_saved = settings.mp_external_store_id or cfg.get("EXTERNAL_STORE_ID", "")
    needs_initial_setup = not external_store_id_saved

    # ---------- helpers ----------
    def _guardar_en_db(token, uid, nombre, p_ext, s_ext, qr=""):
        db.set_config("ACCESS_TOKEN", token)
        db.set_config("USER_ID", uid)
        db.set_config("NOMBRE_NEGOCIO", nombre)
        db.set_config("DIRECCION", direccion_field.value.strip())
        db.set_config("RECARGO", recargo_field.value.strip() or "0")
        db.set_config("EXTERNAL_POS_ID", p_ext)
        db.set_config("EXTERNAL_STORE_ID", s_ext)
        if qr:
            db.set_config("QR_URL", qr)

    def _aplicar_credenciales():
        import os
        os.environ["MP_ACCESS_TOKEN"] = token_field.value.strip()
        os.environ["MP_USER_ID"] = user_field.value.strip()
        # sin overlay de DB: usar el token recién ingresado
        settings.reload(from_db=False)

    # ---------- handlers ----------
    def crear_handler_initial(e=None):
        token, uid = token_field.value.strip(), user_field.value.strip()
        nombre = nombre_negocio_field.value.strip()
        if not token or not uid or not nombre:
            resultado_text.value = "❌ Complete token, user ID y nombre del negocio"
            page.update()
            return
        resultado_text.value = "⏳ Creando Store + POS (fixed_amount)…"
        page.update()

        def worker():
            _aplicar_credenciales()
            s_ext, p_ext, qr_url, error = mp_service.crear_store_y_pos(nombre)
            if error:
                resultado_text.value = f"❌ {error}"
            else:
                resultado_text.value = (f"✅ Store: {s_ext}\nPOS: {p_ext}\n"
                                        "Copie estos valores a su .env (MP_EXTERNAL_…)")
                qr_image.src = qr_url or None
                _guardar_en_db(token, uid, nombre, p_ext, s_ext, qr_url)
            page.update()

        threading.Thread(target=worker, daemon=True).start()

    def obtener_pos(e=None):
        token, uid = token_field.value.strip(), user_field.value.strip()
        if not token or not uid:
            resultado_text.value = "❌ Debes ingresar Access Token y User ID"
            page.update()
            return
        resultado_text.value = "⏳ Consultando POS…"
        page.update()
        _aplicar_credenciales()
        nonlocal pos_list
        pos_list = mp_service.listar_pos()
        if not pos_list:
            resultado_text.value = "⚠️ Sin POS o error de credenciales"
            page.update()
            return
        pos_dropdown.options = [
            ft.dropdown.Option(key=str(i), text=f"{p.get('name')} ({p.get('external_id', 'N/A')})")
            for i, p in enumerate(pos_list)
        ]
        resultado_text.value = f"✅ {len(pos_list)} POS. Seleccione uno."
        page.update()

    def seleccionar_pos(e=None):
        if pos_dropdown.value is None:
            return
        pos = pos_list[int(pos_dropdown.value)]
        p_ext = pos.get("external_id", "")
        qr_url = (pos.get("qr") or {}).get("image", "")
        s_ext = ""
        try:
            import requests
            store_id = pos.get("store_id")
            if store_id:
                r = requests.get(f"https://api.mercadopago.com/stores/{store_id}",
                                 headers={"Authorization": f"Bearer {token_field.value.strip()}"},
                                 timeout=15)
                if r.status_code == 200:
                    s_ext = r.json().get("external_id", "")
        except Exception:
            pass
        resultado_text.value = f"✅ POS: {p_ext}\nStore: {s_ext or '—'}\nCopie a su .env"
        qr_image.src = qr_url or None
        _guardar_en_db(token_field.value.strip(), user_field.value.strip(),
                       nombre_negocio_field.value.strip(), p_ext, s_ext, qr_url)
        page.update()

    def crear_pos_adicional(e=None):
        if not external_store_id_saved and not db.get_config_value("STORE_ID"):
            resultado_text.value = "❌ Faltan datos para crear el POS"
            page.update()
            return
        resultado_text.value = "⏳ Creando POS adicional…"
        page.update()

        def worker():
            _aplicar_credenciales()
            p_ext, qr_url, error = mp_service.crear_pos_adicional()
            if error:
                resultado_text.value = f"❌ {error}"
            else:
                resultado_text.value = f"✅ POS adicional: {p_ext}"
                qr_image.src = qr_url or qr_image.src
            page.update()

        threading.Thread(target=worker, daemon=True).start()

    def descargar_qr(e=None):
        src = qr_image.src or qr_url_saved or ""
        ok, msg = mp_service.descargar_qr(src or "img/qr.png")
        if not ok and src.startswith("http"):
            try:
                import requests
                from pathlib import Path
                r = requests.get(src, timeout=20)
                if r.status_code == 200:
                    p = Path("img/qr.png")
                    p.parent.mkdir(exist_ok=True)
                    p.write_bytes(r.content)
                    ok, msg = True, str(p)
            except Exception as ex:  # noqa: BLE001
                msg = str(ex)
        resultado_text.value = f"✅ QR: {msg}" if ok else f"❌ {msg}"
        page.update()

    def imprimir_qr_action(e=None):
        from pathlib import Path
        p = Path("img/qr.png")
        if not p.exists():
            resultado_text.value = "⚠️ No se encontró el QR para imprimir (descárguelo primero)"
            page.update()
            return
        ok, msg = imprimir_archivo(p)
        snack(page, msg if ok else f"⚠️ {msg}", ok=ok)

    def guardar_config(e=None):
        _guardar_en_db(token_field.value.strip(), user_field.value.strip(),
                       nombre_negocio_field.value.strip(),
                       pos_dropdown.value or external_pos_id_saved,
                       external_store_id_saved or db.get_config_value("EXTERNAL_STORE_ID") or "",
                       qr_image.src or "")
        _guardar_ventas_en_db()
        _guardar_afip_en_db()
        _guardar_red_en_db()
        _guardar_seguridad_en_db()
        if (red_modo_dropdown.value or "").lower() == "servidor":
            _encender_servidor()
        settings.reload()
        comprobar_modo_activo()
        snack(page, "✅ Configuración guardada. Reiniciá el POS para aplicar el modo de conexión.", ok=True)
        dialog.open = False
        page.update()

    # Asignaciones exclusivas: un QR MP por tótem o caja física.
    mp_terminal = ft.Dropdown(label="Dispositivo IntraShop / Caja", width=340)
    mp_asignado = ft.Dropdown(label="POS de Mercado Pago asignado", width=340)
    mp_bindings_info = ft.Text("Consultá dispositivos y POS disponibles.", size=12, color=N.GREY_500)
    mp_bindings_list = ft.Column(spacing=4)

    def cargar_asignaciones(e=None):
        try:
            from adapters.entregas import EntregasAdapter
            from adapters.mp_bindings import listar
            registrados = EntregasAdapter().totems()
            mp_terminal.options = [
                ft.dropdown.Option(key="totem:" + t["id"], text="Tótem · " + t["nombre"])
                for t in registrados
            ]
            # Caja física: identificación local, independiente del tótem.
            mp_terminal.options.append(ft.dropdown.Option(key="caja:principal", text="Caja POS principal"))
            bindings = listar()
            mp_bindings_list.controls = [
                ft.Text(x["nombre"] + " → " + x["pos_external_id"], size=12)
                for x in bindings
            ]
            mp_asignado.options = [
                ft.dropdown.Option(key=str(i), text=p.get("name","POS") + " · " + p.get("external_id",""))
                for i,p in enumerate(pos_list) if p.get("external_id")
            ]
            mp_bindings_info.value = str(len(registrados)) + " tótem(s) registrados · " + str(len(bindings)) + " asignaciones"
            mp_bindings_info.color = N.GREEN_400
        except Exception as exc:
            mp_bindings_info.value = "No se pudo consultar la configuración central: " + str(exc)
            mp_bindings_info.color = N.RED_400
        page.update()

    def guardar_asignacion(e=None):
        if not mp_terminal.value or mp_asignado.value is None:
            mp_bindings_info.value = "Seleccioná un dispositivo y un POS Mercado Pago."
            page.update()
            return
        try:
            from adapters.mp_bindings import asignar
            tipo, tid = mp_terminal.value.split(":",1)
            pos = pos_list[int(mp_asignado.value)]
            store_ext = settings.mp_external_store_id or db.get_config_value("EXTERNAL_STORE_ID") or ""
            if not store_ext:
                raise ValueError("Configurá el Store de Mercado Pago antes de asignar.")
            asignar(tid,tipo,pos["external_id"],store_ext,
                    (pos.get("qr") or {}).get("image",""),pos.get("name",""))
            cargar_asignaciones()
        except Exception as exc:
            mp_bindings_info.value = "No se pudo asignar: " + str(exc)
            mp_bindings_info.color = N.RED_400
            page.update()

    seccion_mp_terminales = ft.Container(
        content=ft.Column([
            ft.Text("Asignación de QR por dispositivo", size=14, weight=ft.FontWeight.BOLD, color=N.BLUE_400),
            ft.Text("Cada tótem debe tener un POS Mercado Pago distinto. Una misma asignación no se puede reutilizar.", size=12),
            ft.Row([ft.OutlinedButton("Detectar tótems y POS", icon=ft.Icons.SEARCH,
                on_click=lambda e: (obtener_pos(), cargar_asignaciones()))], wrap=True),
            mp_terminal, mp_asignado,
            ft.FilledButton("Asignar QR al dispositivo", icon=ft.Icons.CHECK, on_click=guardar_asignacion),
            mp_bindings_info, mp_bindings_list,
        ], spacing=8),
        padding=12, border_radius=8,
        bgcolor=ft.Colors.with_opacity(0.05,N.BLUE_GREY_800),
    )

    # ---------- secciones (layout del build) ----------
    seccion_negocio = ft.Container(
        content=ft.Column([
            ft.Text("📋 Datos del Negocio", size=14, weight=ft.FontWeight.BOLD,
                    color=N.BLUE_400),
            nombre_negocio_field,
            direccion_field,
            ft.Divider(height=8),
        ], spacing=8),
        padding=12, bgcolor=ft.Colors.with_opacity(0.05, N.BLUE_GREY_800),
        border_radius=8)

    seccion_mp = ft.Container(
        content=ft.Column([
            ft.Text("🔐 Credenciales Mercado Pago", size=14, weight=ft.FontWeight.BOLD,
                    color=N.BLUE_400),
            user_field,
            token_field,
            ft.Row([
                ft.FilledButton("Obtener POS", icon=ft.Icons.SEARCH, on_click=obtener_pos),
                pos_dropdown,
                ft.FilledButton("Seleccionar", icon=ft.Icons.CHECK, on_click=seleccionar_pos),
            ], spacing=8, wrap=True),
            ft.Text("Los secretos definitivos van en el archivo .env (no en la DB).",
                    size=11, italic=True, color=N.GREY_500),
            ft.Divider(height=8),
        ], spacing=8),
        padding=12, bgcolor=ft.Colors.with_opacity(0.05, N.BLUE_GREY_800),
        border_radius=8)

    seccion_ventas = ft.Container(
        content=ft.Column([
            ft.Text("💰 Configuración de Ventas", size=14, weight=ft.FontWeight.BOLD,
                    color=N.BLUE_400),
            recargo_field,
            recargo_debito_field,
            recargo_credito_field,
            ft.Divider(height=8),
            ft.Text("Medios de pago activos", size=12, weight=ft.FontWeight.BOLD,
                    color=N.BLUE_300),
            mp_activo_switch,
            debito_activo_switch,
            credito_activo_switch,
            ft.Divider(height=8),
            vuelto_switch,
            ft.Text("Si el vuelto está activo, al cobrar en efectivo se pide con cuánto "
                    "paga el cliente y se muestra el vuelto a entregar.",
                    size=11, italic=True, color=N.GREY_500),
        ], spacing=8),
        padding=12, bgcolor=ft.Colors.with_opacity(0.05, N.BLUE_GREY_800),
        border_radius=8)

    seccion_facturacion = ft.Container(
        content=ft.Column([
            ft.Text("🧾 Facturación AFIP", size=14, weight=ft.FontWeight.BOLD,
                    color=N.CYAN_400),
            ft.Row([afip_cuit_field, afip_pv_field, afip_tipo_dropdown], spacing=8, wrap=True),
            ft.Row([condicion_iva_dropdown, iibb_field, inicio_actividades_field],
                   spacing=8, wrap=True),
            ft.Text("Condición IVA, Ingresos Brutos e Inicio de actividades se imprimen "
                    "en la factura y el ticket.", size=11, italic=True,
                    color=N.GREY_500),
            ft.Row([afip_modo_dropdown], spacing=8, wrap=True),
            cert_row,
            key_row,
            afip_cert_status,
            ft.Text("Rutas por defecto: ./certificados/wsaa.crt y wsaa.key. Use el icono 📁 para cambiar.",
                    size=11, italic=True, color=N.GREY_500),
            ft.Divider(height=8),
            facturacion_activa_switch,
            facturar_qr_switch,
            facturar_efectivo_switch,
            ft.Text("Por defecto: facturación automática DESACTIVADA (NO).",
                    size=11, italic=True, color=N.GREY_500),
        ], spacing=8),
        padding=12, bgcolor=ft.Colors.with_opacity(0.05, N.BLUE_GREY_800),
        border_radius=8)

    seccion_seguridad = ft.Container(
        content=ft.Column([
            ft.Text("🔑 Acceso al sistema", size=14, weight=ft.FontWeight.BOLD,
                    color=N.AMBER_400),
            ft.Row([login_user_field, login_pass_field], spacing=8, wrap=True),
            ft.Text("Este campo actualiza el usuario ADMIN. Para crear otros "
                    "usuarios, roles y permisos usá ROLES Y USUARIOS. Las claves "
                    "se guardan en la base sin cifrado.",
                    size=11, italic=True, color=N.GREY_500),
        ], spacing=8),
        padding=12, bgcolor=ft.Colors.with_opacity(0.05, N.BLUE_GREY_800),
        border_radius=8)

    seccion_directorios = ft.Container(
        content=ft.Column([
            ft.Text("🖨️ Directorios de comprobantes", size=14, weight=ft.FontWeight.BOLD,
                    color=N.CYAN_400),
            comprobantes_dir_row,
            tickets_dir_row,
            ft.Text("Los comprobantes .txt van en la primera carpeta; los tickets PDF "
                    "y facturas emitidas en la segunda.",
                    size=11, italic=True, color=N.GREY_500),
        ], spacing=8),
        padding=12, bgcolor=ft.Colors.with_opacity(0.05, N.BLUE_GREY_800),
        border_radius=8)

    btn_encender = ft.FilledButton("🖥️ Encender servidor", icon=ft.Icons.PLAY_ARROW,
                                   on_click=_encender_servidor)
    btn_detener = ft.FilledButton("⏹️ Detener servidor", icon=ft.Icons.STOP,
                                  on_click=_detener_servidor)
    btn_quitar = ft.TextButton("🗑️ Quitar servicio", icon=ft.Icons.DELETE_OUTLINE,
                               on_click=_quitar_servicio)
    _actualizar_controles_servidor()
    comprobar_modo_activo()

    seccion_red = ft.Container(
        content=ft.Column([
            ft.Text("🌐 Red / Multi-usuario", size=14, weight=ft.FontWeight.BOLD,
                    color=N.INDIGO_400),
            ft.Row([red_modo_dropdown], spacing=8, wrap=True),
            red_url_field,
            red_modo_activo,
            ft.OutlinedButton("Verificar conexión activa", icon=ft.Icons.WIFI, on_click=comprobar_modo_activo),
            ft.Row([
                ft.FilledButton("🔍 Escanear red", icon=ft.Icons.WIFI_FIND,
                                on_click=_escanear_red),
                btn_encender,
                btn_detener,
                btn_quitar,
            ], spacing=8, wrap=True),
            red_estado_text,
            ft.Text("En Windows el servidor se instala como servicio con inicio automático "
                    "(no hace falta tener la app abierta). Requiere permisos de administrador.\n"
                    "Servidor: comparte la DB por HTTP (WAL + lock).\n"
                    "Cliente: conecta a otra PC de la red.\n"
                    f"Versión web en la LAN: iniciá con --web y abrí "
                    f"http://IP-del-servidor:{getattr(settings, 'web_port', 8550)}"
                    "/cliente (caja) o /stock (depósito).",
                    size=11, italic=True, color=N.GREY_500),
        ], spacing=8),
        padding=12, bgcolor=ft.Colors.with_opacity(0.05, N.BLUE_GREY_800),
        border_radius=8)

    seccion_crear_pos = ft.Container(
        content=ft.Column([
            ft.Text("🏪 Gestión de POS", size=14, weight=ft.FontWeight.BOLD,
                    color=N.ORANGE_400),
            ft.Row([
                ft.FilledButton("Crear Tienda+POS", icon=ft.Icons.STORE,
                                on_click=crear_handler_initial),
                ft.FilledButton("Crear POS Adicional", icon=ft.Icons.ADD,
                                on_click=crear_pos_adicional),
            ], spacing=8, wrap=True),
            ft.Divider(height=8),
        ], spacing=8),
        padding=12, bgcolor=ft.Colors.with_opacity(0.05, N.BLUE_GREY_800),
        border_radius=8)

    seccion_resultado = ft.Container(
        content=ft.Column([resultado_text], spacing=4),
        padding=6, bgcolor=ft.Colors.with_opacity(0.1, N.GREEN_900),
        border_radius=8, border=ft.Border.all(1, N.GREEN_700))

    qr_panel = ft.Container(
        content=ft.Column([
            ft.Text("QR", size=12, weight=ft.FontWeight.BOLD, color=N.BLUE_400),
            qr_image,
            ft.Row([
                ft.FilledButton("Descargar", icon=ft.Icons.DOWNLOAD, on_click=descargar_qr),
                ft.FilledButton("Imprimir", icon=ft.Icons.PRINT, on_click=imprimir_qr_action),
            ], spacing=4),
        ], spacing=8, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        padding=12, bgcolor=ft.Colors.with_opacity(0.05, N.BLUE_GREY_800),
        border_radius=8, alignment=ft.Alignment.CENTER)

    if needs_initial_setup:
        resultado_text.value = "⚠️ CONFIGURACIÓN INICIAL: Ingresa credenciales y crea una tienda"


    # ---------- backup / restauración ----------
    from pathlib import Path as _Path

    from services.backup_service import (exportar_backup as _exportar_backup,
                                         restaurar_backup as _restaurar_backup,
                                         validar_backup as _validar_backup)

    backup_archivo = {"ruta": None, "info": None}
    backup_estado = ft.Text("", size=12, color=N.GREY_400)
    backup_info = ft.Text("", size=11, color=N.GREY_500)
    backup_base = ft.Text(f"Ruta de la base de datos actual: {settings.db_path}", size=11,
                          color=N.GREY_500, selectable=True)

    async def exportar_backup(e=None):
        try:
            from datetime import datetime as _dt
            destino = await save_file(
                page, title="Guardar copia de seguridad",
                file_name=f"backup_libreria_{_dt.now():%Y%m%d_%H%M%S}.db",
                extensions=["db"])
            if not destino:
                return
            ruta = agregar_extension(destino, "db")
            info = await asyncio.to_thread(_exportar_backup, settings.db_path, ruta)
            backup_estado.value = f"Backup generado: {ruta}"
            backup_estado.color = N.GREEN_400
            backup_info.value = f"Tablas: {info.get('conteos')} · {info.get('bytes', 0):,} bytes"
            page.update()
        except Exception as ex:  # noqa: BLE001
            backup_estado.value = f"Error al exportar: {ex}"
            backup_estado.color = N.RED_400
            page.update()

    async def elegir_backup(e=None):
        try:
            ruta = await pick_file(page, title="Seleccionar copia de seguridad")
            if not ruta:
                return
            info = await asyncio.to_thread(_validar_backup, ruta)
            backup_archivo["ruta"] = ruta
            backup_archivo["info"] = info
            backup_info.value = (f"Backup válido · {_Path(ruta).name} · "
                                 f"{info.get('conteos')}")
            backup_info.color = N.GREEN_400
            backup_estado.value = "Elegí cómo restaurar: Fusionar o Reemplazar."
            backup_estado.color = N.BLUE_300
            page.update()
        except Exception as ex:  # noqa: BLE001
            backup_archivo["ruta"] = None
            backup_info.value = f"Archivo inválido: {ex}"
            backup_info.color = N.RED_400
            page.update()

    async def _restaurar(modo: str):
        ruta = backup_archivo.get("ruta")
        if not ruta:
            backup_estado.value = "Primero elegí un archivo de backup."
            backup_estado.color = N.RED_400
            page.update()
            return
        backup_estado.value = "Restaurando… no cierres la aplicación."
        backup_estado.color = N.ORANGE_400
        page.update()
        try:
            res = await asyncio.to_thread(_restaurar_backup, settings.db_path, ruta, modo)
            settings.reload()
            if modo == "fusionar":
                detalle = (f"productos +{res.get('productos_importados', 0)} "
                           f"(omitidos {res.get('productos_omitidos', 0)}), "
                           f"ventas +{res.get('ventas_importadas', 0)} "
                           f"(omitidas {res.get('ventas_omitidas', 0)}), "
                           f"proveedores +{res.get('proveedores_importados', 0)}, "
                           f"órdenes +{res.get('ordenes_importadas', 0)}")
            else:
                detalle = f"datos restaurados: {res.get('conteos')}"
            backup_estado.value = f"Restauración OK ({modo}): {detalle}"
            backup_estado.color = N.GREEN_400
            backup_info.value = f"Backup de seguridad: {res.get('seguridad')}"
            snack(page, "Datos restaurados correctamente", ok=True)
            page.update()
        except Exception as ex:  # noqa: BLE001
            backup_estado.value = f"Error al restaurar: {ex}"
            backup_estado.color = N.RED_400
            snack(page, f"Error al restaurar: {ex}", ok=False)
            page.update()

    def preguntar_restaurar(modo: str):
        if not backup_archivo.get("ruta"):
            snack(page, "Primero elegí un archivo de backup", ok=False)
            return
        if modo == "reemplazar":
            titulo = "Reemplazar TODA la base"
            mensaje = ("Se reemplazará la base actual por el backup. "
                       "Se creará automáticamente una copia de seguridad en "
                       "la carpeta backups/ antes de continuar.")
            color = N.RED_700
        else:
            titulo = "Fusionar backup"
            mensaje = ("Se agregarán proveedores, productos, ventas y órdenes "
                       "que no existan. No se duplican productos (por código) "
                       "ni ventas (por huella). La configuración actual no se modifica.")
            color = N.BLUE_700

        def _ok(_e):
            cerrar_dialogo(page)
            page.run_task(_restaurar, modo)

        from ui.helpers import abrir_dialogo as _abrir
        _abrir(page, ft.AlertDialog(
            modal=True,
            title=ft.Text(titulo),
            content=ft.Text(mensaje),
            actions=[
                ft.TextButton("CANCELAR", on_click=lambda _e: cerrar_dialogo(page)),
                ft.FilledButton("CONTINUAR", on_click=_ok,
                                style=ft.ButtonStyle(bgcolor=color,
                                                     color=ft.Colors.WHITE)),
            ],
        ))

    # ---------- TABS ----------
    def _tab_content(controls):
        return ft.Container(
            content=ft.Column(controls, spacing=10, scroll=ft.ScrollMode.AUTO, expand=True),
            padding=4, expand=True,
        )

    backup_tab = _tab_content([
        ft.Text("Copia de seguridad", size=15, weight=ft.FontWeight.BOLD,
                color=N.BLUE_300),
        ft.Text("Exportá la base completa o restaurá un backup. "
                "En modo fusionar se evitan productos y ventas duplicadas.",
                size=11, color=N.GREY_400),
        backup_base,
        ft.Row([
            ft.FilledButton("EXPORTAR BACKUP", icon=ft.Icons.SAVE_ALT,
                            on_click=exportar_backup,
                            style=ft.ButtonStyle(bgcolor=N.GREEN_700,
                                                 color=ft.Colors.WHITE)),
            ft.OutlinedButton("ELEGIR BACKUP", icon=ft.Icons.FOLDER_OPEN,
                              on_click=elegir_backup),
        ], spacing=10, wrap=True),
        backup_info,
        ft.Row([
            ft.FilledButton("FUSIONAR", icon=ft.Icons.MERGE_TYPE,
                            on_click=lambda _e: preguntar_restaurar("fusionar"),
                            style=ft.ButtonStyle(bgcolor=N.BLUE_700,
                                                 color=ft.Colors.WHITE)),
            ft.FilledButton("REEMPLAZAR", icon=ft.Icons.RESTORE,
                            on_click=lambda _e: preguntar_restaurar("reemplazar"),
                            style=ft.ButtonStyle(bgcolor=N.RED_700,
                                                 color=ft.Colors.WHITE)),
        ], spacing=10, wrap=True),
        ft.Container(
            content=ft.Column([
                ft.Text("Recomendaciones", size=12, weight=ft.FontWeight.BOLD),
                ft.Text("• Exportá un backup antes de restaurar.", size=11,
                        color=N.GREY_400),
                ft.Text("• 'Fusionar' es ideal para unir datos de otra PC.", size=11,
                        color=N.GREY_400),
                ft.Text("• 'Reemplazar' deja la base exactamente como el backup.",
                        size=11, color=N.GREY_400),
            ], spacing=3),
            padding=12, border_radius=8,
            bgcolor=ft.Colors.with_opacity(0.06, N.BLUE_GREY_800),
        ),
        backup_estado,
    ])

    tienda_tab = _tab_content([
        ft.ResponsiveRow([
            ft.Column([seccion_negocio, seccion_ventas],
                      col={"xs": 12, "lg": 6}, spacing=10),
            ft.Column([seccion_seguridad, seccion_directorios, seccion_red],
                      col={"xs": 12, "lg": 6}, spacing=10),
        ], spacing=10, run_spacing=10),
    ])

    contenidos = [
        tienda_tab,
        _tab_content([seccion_mp, seccion_mp_terminales, seccion_crear_pos, qr_panel]),
        _tab_content([seccion_facturacion]),
        backup_tab,
    ]
    etiquetas = ["🏪 Tienda", "🔐 Mercado Pago", "🧾 Facturación AFIP", "💾 Backup"]
    sel = {"idx": 0}
    botones_tab: list = []

    def _cambiar_tab(i):
        sel["idx"] = i
        for j, b in enumerate(botones_tab):
            b.style = ft.ButtonStyle(
                bgcolor=N.BLUE_700 if j == i else N.GREY_800,
                color=ft.Colors.WHITE,
            )
            b.icon = ft.Icons.CHECK if j == i else None
        contenedor_tabs.content.controls = [contenidos[i]]
        page.update()

    for i, label in enumerate(etiquetas):
        botones_tab.append(ft.FilledTonalButton(
            label, icon=(ft.Icons.CHECK if i == 0 else None),
            style=ft.ButtonStyle(
                bgcolor=N.BLUE_700 if i == 0 else N.GREY_800,
                color=ft.Colors.WHITE),
            on_click=lambda e, i=i: _cambiar_tab(i),
        ))

    alto_pantalla = int(getattr(page, "height", 0) or
                        getattr(getattr(page, "window", None), "height", 0) or 900)
    # Adaptar el contenido a la pantalla; evitar el antiguo tope fijo de 460 px.
    alto_dialogo = max(360, min(900, alto_pantalla - 64))
    alto_tabs = max(220, alto_dialogo - 190)
    contenedor_tabs = ft.Container(
        content=ft.Column([contenidos[0]], expand=True),
        height=alto_tabs,
    )
    tabs_row = ft.Row(botones_tab, spacing=6, wrap=True)

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Row([
            ft.Icon(ft.Icons.SETTINGS, color=N.BLUE_400),
            ft.Text("Ajustes", size=20, weight=ft.FontWeight.BOLD),
        ], spacing=8),
        content=ft.Container(
            content=ft.Column(
                [tabs_row, contenedor_tabs, seccion_resultado],
                spacing=10, tight=True,
            ),
            height=alto_dialogo - 115,
            width=min(1040, max(360, int(getattr(page, "width", 0) or 1200) - 64)),
        ),
        actions=[
            ft.TextButton("Cancelar", on_click=lambda _: cerrar_dialogo(page)),
            ft.FilledButton("Guardar", icon=ft.Icons.SAVE, on_click=guardar_config),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    return dialog

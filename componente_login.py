"""Login local con usuarios y roles.

Los usuarios se administran desde ROLES Y USUARIOS (solo ADMIN). Se mantiene
compatibilidad con el usuario/clave único de la tabla config.
"""
from __future__ import annotations

import json
from pathlib import Path

import flet as ft
from ui.paleta import N

from utils.paths import base_dir as _base_dir

_RECUERDO_LOGIN = _base_dir() / "login_recordado.json"


def _cargar_recordado() -> tuple[str, str]:
    """Nunca restaurar una contraseña desde un archivo local."""
    try:
        data = json.loads(_RECUERDO_LOGIN.read_text(encoding="utf-8"))
        usuario = str(data.get("usuario") or "")
        if "clave" in data:
            # Migración de instalaciones antiguas: quitar la clave en claro.
            _guardar_recordado(usuario, "")
        return usuario, ""
    except Exception:
        return "", ""


def _guardar_recordado(usuario: str, clave: str = "") -> None:
    """Solo se persiste el nombre de usuario; jamás la contraseña."""
    try:
        _RECUERDO_LOGIN.parent.mkdir(parents=True, exist_ok=True)
        _RECUERDO_LOGIN.write_text(
            json.dumps({"usuario": usuario}), encoding="utf-8")
        _RECUERDO_LOGIN.chmod(0o600)
    except Exception:
        pass


def _borrar_recordado() -> None:
    try:
        _RECUERDO_LOGIN.unlink()
    except Exception:
        pass

from ui.theme import (BTN_PRIMARIO, GRADIENTE_FONDO, GRADIENTE_NEON,
                      logo_widget, sombra_neon)

_USUARIO_DEFAULT = "admin"
_CLAVE_DEFAULT = "admin"
_NOMBRE_TIENDA_DEFAULT = "Tienda"


def nombre_tienda(db_manager) -> str:
    try:
        nombre = (db_manager.get_config_value("NOMBRE_NEGOCIO") or "").strip()
    except Exception:
        nombre = ""
    return nombre or _NOMBRE_TIENDA_DEFAULT


def credenciales_configuradas(db_manager) -> bool:
    try:
        if db_manager.listar_usuarios():
            return True
    except Exception:
        pass
    try:
        return bool(db_manager.get_config_value("LOGIN_USUARIO")
                    and db_manager.get_config_value("LOGIN_CLAVE"))
    except Exception:
        return False


def validar_login(db_manager, usuario: str, clave: str) -> bool:
    """Validación real; en cliente nunca usar credenciales locales de respaldo."""
    from core.db_factory import modo_actual

    try:
        if db_manager.autenticar_usuario(usuario, clave) is not None:
            return True
    except Exception:
        pass
    if modo_actual() == "cliente":
        # Fallar cerrado: config local jamás sustituye al login del servidor.
        return False
    try:
        user_ok = (db_manager.get_config_value("LOGIN_USUARIO")
                   or _USUARIO_DEFAULT).strip()
        clave_ok = (db_manager.get_config_value("LOGIN_CLAVE")
                    or _CLAVE_DEFAULT).strip()
    except Exception:
        user_ok, clave_ok = _USUARIO_DEFAULT, _CLAVE_DEFAULT
    return (usuario or "").strip() == user_ok and (clave or "").strip() == clave_ok


def LoginView(db_manager, on_login, page: ft.Page):
    _rec_usuario, _rec_clave = _cargar_recordado()
    usuario_field = ft.TextField(
        label="Usuario", value=_rec_usuario, autofocus=True, width=320,
        prefix_icon=ft.Icons.PERSON_OUTLINE)
    clave_field = ft.TextField(
        label="Clave", password=True, can_reveal_password=True, width=320,
        value=_rec_clave,
        prefix_icon=ft.Icons.LOCK_OUTLINE)
    recordar_cb = ft.Checkbox(
        label="Recordar usuario", value=bool(_rec_usuario))
    error_text = ft.Text("", size=12, color=N.RED_400, visible=False)
    configurado = credenciales_configuradas(db_manager)
    ayuda = ft.Text(
        "Usuario inicial: «admin», clave «admin». Cambiala desde "
        "ROLES Y USUARIOS."
        if not configurado else
        "Ingresá con el usuario y la clave asignados por el administrador.",
        size=11, italic=True, color=N.GREY_500,
        text_align=ft.TextAlign.CENTER)

    def ingresar(e=None):
        from core.db_factory import modo_actual
        error_conexion = None
        try:
            usuario = db_manager.autenticar_usuario(
                usuario_field.value, clave_field.value)
        except Exception as exc:
            usuario = None
            # No imprimir tokens, claves ni respuestas HTTP completas.
            error_conexion = str(exc) if isinstance(
                exc, (ConnectionError, RuntimeError)
            ) else "No se pudo iniciar sesión con POS Server. Verificá la conexión."
        if (usuario is None and error_conexion is None
                and modo_actual() != "cliente" and validar_login(
                    db_manager, usuario_field.value, clave_field.value)):
            from core.permisos import permisos_todos

            usuario = {
                "usuario": (usuario_field.value or "").strip(),
                "nombre": "Administrador", "rol": "ADMIN", "rol_id": 0,
                "es_admin": True, "activo": True,
                "permisos": permisos_todos(),
            }
        if usuario:
            # ApiClient ya obtuvo y almacenó la sesión POS en modo cliente.
            # Repetir el login generaba otro token y podía borrar la sesión
            # válida si esa segunda solicitud fallaba por timeout.
            if modo_actual() != "cliente":
                try:
                    import httpx
                    from adapters.entregas import set_session
                    from core.settings import settings
                    base = "http://127.0.0.1:" + str(settings.api_port)
                    response = httpx.post(base + "/pos/auth/login",
                        json={"usuario": usuario_field.value,
                              "clave": clave_field.value}, timeout=4)
                    if response.status_code == 200:
                        set_session(response.json()["access_token"])
                    else:
                        set_session(None)
                except Exception:
                    from adapters.entregas import set_session
                    set_session(None)
            if recordar_cb.value:
                _guardar_recordado(usuario_field.value or "")
            else:
                _borrar_recordado()
            try:
                on_login(usuario, bool(recordar_cb.value))
            except TypeError:
                on_login(usuario)
            return
        error_text.value = error_conexion or "Usuario o clave incorrectos"
        error_text.visible = True
        # Preservar el campo si el fallo es de conexión (no fue validado).
        if not error_conexion:
            clave_field.value = ""
        page.update()
        try:
            page.run_task(clave_field.focus)
        except Exception:
            pass

    usuario_field.on_submit = lambda _e: ingresar()
    clave_field.on_submit = ingresar

    def configurar_red(e=None):
        from database_manager import DatabaseManager
        from core.db_factory import modo_actual, _server_url
        from ui.helpers import abrir_dialogo, cerrar_dialogo
        db_local = DatabaseManager()
        modo = ft.Dropdown(label="Modo de conexión", value=modo_actual(), width=290,
            options=[ft.dropdown.Option("local", "Local"),
                     ft.dropdown.Option("servidor", "Servidor"),
                     ft.dropdown.Option("cliente", "Cliente LAN")])
        url = ft.TextField(label="URL del servidor POS", value=_server_url(), width=290)
        clave = ft.TextField(
            label="Clave LAN de POS Server (opcional si ya está configurada)",
            password=True, can_reveal_password=True, width=290,
            hint_text="Pegá la clave copiada desde POS Server",
        )
        estado = ft.Text("La clave se guarda en archivo privado de esta terminal (0600), nunca en la URL.", size=12, color=N.AMBER_400)
        def guardar(e):
            try:
                if (clave.value or "").strip():
                    from core.settings import guardar_clave_lan_local
                    guardar_clave_lan_local(clave.value)
                db_local.set_config("MODO_RED", modo.value)
                db_local.set_config("SERVER_URL", (url.value or "").strip())
            except ValueError as exc:
                estado.value = str(exc)
                page.update()
                return
            clave.value = ""
            cerrar_dialogo(page)
            estado.value = "Configuración guardada. Reiniciá el POS."
            page.update()
        dlg = ft.AlertDialog(modal=True, title=ft.Text("Conexión de esta terminal"),
            content=ft.Column([modo, url, clave, estado], tight=True, spacing=12),
            actions=[ft.TextButton("Cancelar", on_click=lambda e: cerrar_dialogo(page)),
                     ft.FilledButton("Guardar", on_click=guardar)])
        abrir_dialogo(page, dlg)

    tarjeta = ft.Container(
        content=ft.Column([
            ft.Icon(ft.Icons.LOCK_PERSON, size=56, color=N.BLUE_300),
            ft.Text("INICIAR SESIÓN", size=22, weight=ft.FontWeight.BOLD),
            ft.Text("Sistema de Gestión", size=12, color=N.GREY_400),
            ft.Container(height=8),
            usuario_field,
            clave_field,
            recordar_cb,
            error_text,
            ft.FilledButton(
                "INGRESAR", icon=ft.Icons.LOGIN, width=320, height=46,
                style=BTN_PRIMARIO, on_click=ingresar),
            ayuda,
            ft.TextButton("Configurar conexión LAN de esta terminal", icon=ft.Icons.SETTINGS_ETHERNET, on_click=configurar_red),
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
        padding=32, border_radius=14, width=400,
        bgcolor=ft.Colors.with_opacity(0.55, N.DEEP),
        border=ft.Border.all(1.5, ft.Colors.with_opacity(0.7, N.CYAN)),
        shadow=sombra_neon(N.VIOLET, 40, 0.35),
    )

    return ft.Container(
        content=ft.Column([
            ft.Container(
                content=ft.Column([
                    logo_widget(48),
                    ft.Text(nombre_tienda(db_manager), size=26,
                            weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE,
                            text_align=ft.TextAlign.CENTER),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=4),
                gradient=GRADIENTE_NEON, shadow=sombra_neon(N.CYAN, 30, 0.4),
                padding=16, border_radius=12,
                width=400, alignment=ft.Alignment.CENTER),
            ft.Container(height=16),
            tarjeta,
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER,
           alignment=ft.MainAxisAlignment.CENTER, spacing=0, expand=True),
        padding=20, expand=True, alignment=ft.Alignment.CENTER,
        gradient=GRADIENTE_FONDO,
    )

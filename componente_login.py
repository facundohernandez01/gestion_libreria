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
    try:
        data = json.loads(_RECUERDO_LOGIN.read_text(encoding="utf-8"))
        return str(data.get("usuario") or ""), str(data.get("clave") or "")
    except Exception:
        return "", ""


def _guardar_recordado(usuario: str, clave: str) -> None:
    try:
        _RECUERDO_LOGIN.write_text(
            json.dumps({"usuario": usuario, "clave": clave}), encoding="utf-8")
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
    """Compatibilidad: True si las credenciales son válidas."""
    try:
        return db_manager.autenticar_usuario(usuario, clave) is not None
    except Exception:
        pass
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
        label="Recordar usuario y clave", value=bool(_rec_usuario or _rec_clave))
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
        from core.pos_operator_session import preparar_sesion_operador
        from adapters.entregas import set_session

        modo = modo_actual()
        # El cliente HTTP crea una sesión vinculada a X-Terminal-Id.
        # Una segunda petición de login aquí sobrescribía el token con uno
        # sin terminal y /cajas/abierta respondía 403 después de un 200.
        set_session(None)
        try:
            usuario = db_manager.autenticar_usuario(
                usuario_field.value, clave_field.value)
        except Exception:
            usuario = None
        if usuario is None and modo != "cliente" and validar_login(
                db_manager, usuario_field.value, clave_field.value):
            from core.permisos import permisos_todos

            usuario = {
                "usuario": (usuario_field.value or "").strip(),
                "nombre": "Administrador", "rol": "ADMIN", "rol_id": 0,
                "es_admin": True, "activo": True,
                "permisos": permisos_todos(),
            }
        if usuario and preparar_sesion_operador(
                modo, usuario_field.value, clave_field.value):
            if recordar_cb.value:
                _guardar_recordado(usuario_field.value or "", clave_field.value or "")
            else:
                _borrar_recordado()
            try:
                on_login(usuario, bool(recordar_cb.value))
            except TypeError:
                on_login(usuario)
            return
        error_text.value = (
            getattr(db_manager, "ultimo_error_login", "") or
            "Usuario o clave incorrectos"
        )
        error_text.visible = True
        clave_field.value = ""
        page.update()
        try:
            page.run_task(clave_field.focus)
        except Exception:
            pass

    usuario_field.on_submit = lambda _e: ingresar()
    clave_field.on_submit = ingresar

    def configurar_red(e=None):
        from core.db_factory import modo_actual, _server_url, es_edicion_intrashop
        from core.pos_client_settings import guardar_server_url
        from ui.helpers import abrir_dialogo, cerrar_dialogo

        es_cliente_intrashop = es_edicion_intrashop()
        # El cliente IntraShop no debe crear ni configurar una SQLite local
        # para recordar una IP: esa configuración no era leída por _server_url.
        modo = ft.Dropdown(
            label="Modo de conexión", value=modo_actual(), width=290,
            disabled=es_cliente_intrashop,
            options=[ft.dropdown.Option("local", "Local"),
                     ft.dropdown.Option("servidor", "Servidor"),
                     ft.dropdown.Option("cliente", "Cliente LAN")],
        )
        url = ft.TextField(
            label="URL del servidor POS", value=_server_url(), width=290,
            hint_text="http://192.168.1.100:8000",
        )
        estado = ft.Text(
            "La conexión se guarda en este equipo, nunca en la base central. "
            "Reiniciá el POS para aplicar los cambios.",
            size=12, color=N.AMBER_400,
        )

        def guardar(e):
            try:
                if es_cliente_intrashop:
                    guardar_server_url(url.value or "")
                else:
                    from database_manager import DatabaseManager
                    db_local = DatabaseManager()
                    db_local.set_config("MODO_RED", modo.value)
                    db_local.set_config("SERVER_URL", (url.value or "").strip())
            except (ValueError, OSError) as exc:
                estado.value = str(exc)
                estado.color = N.RED_400
                page.update()
                return
            cerrar_dialogo(page)
            from ui.helpers import snack
            snack(page, "Conexión guardada en esta terminal. Reiniciá el POS.")

        dlg = ft.AlertDialog(
            modal=True, title=ft.Text("Conexión de esta terminal"),
            content=ft.Column([modo, url, estado], tight=True, spacing=12),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: cerrar_dialogo(page)),
                ft.FilledButton("Guardar", on_click=guardar),
            ],
        )
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

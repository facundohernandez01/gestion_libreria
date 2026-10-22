"""Login local con usuarios y roles.

Los usuarios se administran desde ROLES Y USUARIOS (solo ADMIN). Se mantiene
compatibilidad con el usuario/clave único de la tabla config.
"""
from __future__ import annotations

import flet as ft

from ui.theme import BTN_PRIMARIO

_USUARIO_DEFAULT = "admin"
_CLAVE_DEFAULT = "admin"


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
    usuario_field = ft.TextField(
        label="Usuario", value="", autofocus=True, width=320,
        prefix_icon=ft.Icons.PERSON_OUTLINE)
    clave_field = ft.TextField(
        label="Clave", password=True, can_reveal_password=True, width=320,
        prefix_icon=ft.Icons.LOCK_OUTLINE)
    error_text = ft.Text("", size=12, color=ft.Colors.RED_400, visible=False)
    configurado = credenciales_configuradas(db_manager)
    ayuda = ft.Text(
        "Usuario inicial: «admin», clave «admin». Cambiala desde "
        "ROLES Y USUARIOS."
        if not configurado else
        "Ingresá con el usuario y la clave asignados por el administrador.",
        size=11, italic=True, color=ft.Colors.GREY_500,
        text_align=ft.TextAlign.CENTER)

    def ingresar(e=None):
        try:
            usuario = db_manager.autenticar_usuario(
                usuario_field.value, clave_field.value)
        except Exception:
            usuario = None
        if usuario is None and validar_login(
                db_manager, usuario_field.value, clave_field.value):
            from core.permisos import permisos_todos

            usuario = {
                "usuario": (usuario_field.value or "").strip(),
                "nombre": "Administrador", "rol": "ADMIN", "rol_id": 0,
                "es_admin": True, "activo": True,
                "permisos": permisos_todos(),
            }
        if usuario:
            try:
                on_login(usuario)
            except TypeError:
                on_login()
            return
        error_text.value = "Usuario o clave incorrectos"
        error_text.visible = True
        clave_field.value = ""
        page.update()
        try:
            page.run_task(clave_field.focus)
        except Exception:
            pass

    usuario_field.on_submit = lambda _e: ingresar()
    clave_field.on_submit = ingresar

    tarjeta = ft.Container(
        content=ft.Column([
            ft.Icon(ft.Icons.LOCK_PERSON, size=56, color=ft.Colors.BLUE_300),
            ft.Text("INICIAR SESIÓN", size=22, weight=ft.FontWeight.BOLD),
            ft.Text("Sistema de Gestión", size=12, color=ft.Colors.GREY_400),
            ft.Container(height=8),
            usuario_field,
            clave_field,
            error_text,
            ft.FilledButton(
                "INGRESAR", icon=ft.Icons.LOGIN, width=320, height=46,
                style=BTN_PRIMARIO, on_click=ingresar),
            ayuda,
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
        padding=32, border_radius=14, width=400,
        bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.WHITE),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.25, ft.Colors.BLUE_GREY_600)),
    )

    return ft.Container(
        content=ft.Column([
            ft.Container(
                content=ft.Column([
                    ft.Icon(ft.Icons.MENU_BOOK, size=34, color=ft.Colors.WHITE),
                    ft.Text("LIBRERÍA", size=26, weight=ft.FontWeight.BOLD,
                            color=ft.Colors.WHITE),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=4),
                bgcolor=ft.Colors.BLUE_900, padding=16, border_radius=12,
                width=400, alignment=ft.Alignment.CENTER),
            ft.Container(height=16),
            tarjeta,
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER,
           alignment=ft.MainAxisAlignment.CENTER, spacing=0, expand=True),
        padding=20, expand=True, alignment=ft.Alignment.CENTER,
    )

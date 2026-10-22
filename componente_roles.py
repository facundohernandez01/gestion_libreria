"""Administración de roles y usuarios (solo rol ADMIN).

- Crear/editar/eliminar roles con permisos por sección (checkboxes).
- Crear/editar/eliminar usuarios y asignarles un rol.
"""
from __future__ import annotations

import flet as ft

from core.permisos import ETIQUETAS, PERMISOS, normalizar, permisos_todos
from ui.helpers import abrir_dialogo, cerrar_dialogo, snack
from ui.theme import BTN_PRIMARIO


def RolesUsuariosView(db_manager, on_volver, page: ft.Page,
                      usuario_actual: str = "", seccion_inicial: str = "roles"):
    contenedor = ft.Container(expand=True)
    tab_roles = ft.FilledButton("ROLES", icon=ft.Icons.BADGE)
    tab_usuarios = ft.OutlinedButton("USUARIOS", icon=ft.Icons.PEOPLE)

    def _recargar(seccion: str):
        if seccion == "usuarios":
            tab_roles.style = ft.ButtonStyle(bgcolor=ft.Colors.with_opacity(0.12, ft.Colors.WHITE))
            tab_usuarios.style = ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700)
            contenedor.content = _vista_usuarios()
        else:
            tab_roles.style = ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700)
            tab_usuarios.style = ft.ButtonStyle(bgcolor=ft.Colors.with_opacity(0.12, ft.Colors.WHITE))
            contenedor.content = _vista_roles()
        page.update()

    # ---------- helpers ----------
    def _confirmar(titulo: str, mensaje: str, on_ok):
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(titulo),
            content=ft.Text(mensaje),
            actions=[
                ft.TextButton("CANCELAR", on_click=lambda _e: cerrar_dialogo(page)),
                ft.FilledButton("CONFIRMAR", style=BTN_PRIMARIO,
                                on_click=lambda _e: (_cerrar(dlg), on_ok())),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        abrir_dialogo(page, dlg)

    def _cerrar(dlg):
        try:
            dlg.open = False
            page.update()
        except Exception:
            cerrar_dialogo(page)

    # ---------- editor de rol ----------
    def _editar_rol(rol: dict | None = None):
        rol = rol or {}
        es_admin_rol = bool(rol.get("es_admin"))
        permisos = rol.get("permisos") or {}
        nombre_field = ft.TextField(
            label="Nombre del rol", value=rol.get("nombre") or "",
            disabled=es_admin_rol, width=380)
        desc_field = ft.TextField(
            label="Descripción", value=rol.get("descripcion") or "",
            width=380, multiline=True, min_lines=1, max_lines=2)
        checks = {}
        for clave, etiqueta in PERMISOS:
            checks[clave] = ft.Checkbox(
                label=etiqueta,
                value=True if es_admin_rol else bool(permisos.get(clave)),
                disabled=es_admin_rol)
        error_text = ft.Text("", size=11, color=ft.Colors.RED_400, visible=False)

        def guardar(_e=None):
            nombre = "ADMIN" if es_admin_rol else (nombre_field.value or "").strip()
            if not nombre:
                error_text.value = "Ingresá un nombre para el rol"
                error_text.visible = True
                page.update()
                return
            elegidos = ({c: True for c in checks} if es_admin_rol
                        else {c: bool(chk.value) for c, chk in checks.items()})
            rid, err = db_manager.guardar_rol({
                "id": rol.get("id"), "nombre": nombre,
                "descripcion": (desc_field.value or "").strip(),
                "permisos": elegidos,
            })
            if err:
                error_text.value = err
                error_text.visible = True
                page.update()
                return
            _cerrar(dlg)
            snack(page, "Rol guardado", ok=True)
            _recargar("roles")

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("EDITAR ROL" if rol.get("id") else "NUEVO ROL"),
            content=ft.Container(
                content=ft.Column([
                    nombre_field, desc_field,
                    ft.Text("Permisos", size=12, weight=ft.FontWeight.BOLD,
                            color=ft.Colors.BLUE_300),
                    ft.Column([checks[c] for c, _ in PERMISOS], spacing=0),
                    ft.Text("El rol ADMIN siempre tiene todos los permisos.",
                            size=11, italic=True, color=ft.Colors.GREY_500,
                            visible=es_admin_rol),
                    error_text,
                ], spacing=8, scroll=ft.ScrollMode.AUTO),
                width=420, height=430),
            actions=[
                ft.TextButton("CANCELAR", on_click=lambda _e: _cerrar(dlg)),
                ft.FilledButton("GUARDAR", icon=ft.Icons.SAVE, style=BTN_PRIMARIO,
                                on_click=guardar),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        abrir_dialogo(page, dlg)

    # ---------- editor de usuario ----------
    def _editar_usuario(usuario: dict | None = None):
        usuario = usuario or {}
        roles = db_manager.listar_roles()
        if not roles:
            snack(page, "Primero creá un rol", ok=False)
            return
        opciones = [ft.dropdown.Option(str(r["id"]), r["nombre"]) for r in roles]
        usuario_field = ft.TextField(
            label="Usuario", value=usuario.get("usuario") or "", width=360)
        nombre_field = ft.TextField(
            label="Nombre y apellido", value=usuario.get("nombre") or "", width=360)
        clave_field = ft.TextField(
            label="Clave", password=True, can_reveal_password=True, width=360,
            hint_text=("Dejar vacío para conservar la clave actual"
                       if usuario.get("id") else "Obligatoria"))
        rol_dropdown = ft.Dropdown(
            label="Rol", width=360, options=opciones,
            value=str(usuario.get("rol_id") or roles[0]["id"]))
        activo_switch = ft.Switch(
            label="Usuario activo",
            value=bool(usuario.get("activo", True)))
        error_text = ft.Text("", size=11, color=ft.Colors.RED_400, visible=False)

        def guardar(_e=None):
            uid, err = db_manager.guardar_usuario({
                "id": usuario.get("id"),
                "usuario": (usuario_field.value or "").strip(),
                "clave": (clave_field.value or "").strip(),
                "nombre": (nombre_field.value or "").strip(),
                "rol_id": rol_dropdown.value,
                "activo": bool(activo_switch.value),
            })
            if err:
                error_text.value = err
                error_text.visible = True
                page.update()
                return
            _cerrar(dlg)
            snack(page, "Usuario guardado", ok=True)
            _recargar("usuarios")

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("EDITAR USUARIO" if usuario.get("id") else "NUEVO USUARIO"),
            content=ft.Container(
                content=ft.Column([
                    usuario_field, nombre_field, clave_field,
                    rol_dropdown, activo_switch, error_text,
                ], spacing=8),
                width=380),
            actions=[
                ft.TextButton("CANCELAR", on_click=lambda _e: _cerrar(dlg)),
                ft.FilledButton("GUARDAR", icon=ft.Icons.SAVE, style=BTN_PRIMARIO,
                                on_click=guardar),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        abrir_dialogo(page, dlg)

    # ---------- vistas ----------
    def _vista_roles():
        roles = db_manager.listar_roles()
        tarjetas = ft.Column(spacing=8)
        for rol in roles:
            activos = [ETIQUETAS[c] for c, v in normalizar(rol.get("permisos")).items()
                       if v]
            permisos_texto = ("Todos los permisos" if rol.get("es_admin")
                              else (", ".join(activos) if activos
                                    else "Sin permisos asignados"))

            def _edit(_e, r=rol):
                _editar_rol(r)

            def _del(_e, r=rol):
                _confirmar(
                    f"Eliminar rol {r['nombre']}",
                    "El rol se eliminará definitivamente.",
                    lambda r=r: _eliminar_rol(r))

            acciones = [ft.IconButton(icon=ft.Icons.EDIT, tooltip="Editar",
                                      icon_color=ft.Colors.BLUE_300,
                                      on_click=_edit)]
            if not rol.get("es_admin"):
                acciones.append(ft.IconButton(
                    icon=ft.Icons.DELETE_OUTLINE, tooltip="Eliminar",
                    icon_color=ft.Colors.RED_300, on_click=_del))
            tarjetas.controls.append(ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.VERIFIED_USER if rol.get("es_admin")
                            else ft.Icons.BADGE, color=ft.Colors.BLUE_300),
                    ft.Column([
                        ft.Text(rol["nombre"], size=14,
                                weight=ft.FontWeight.BOLD),
                        ft.Text(rol.get("descripcion") or "—", size=11,
                                color=ft.Colors.GREY_400),
                        ft.Text(permisos_texto, size=10,
                                color=ft.Colors.CYAN_300),
                    ], spacing=2, expand=True),
                    ft.Text(f"{rol.get('usuarios_count', 0)} usuario(s)",
                            size=10, color=ft.Colors.GREY_500),
                    ft.Row(acciones, spacing=0),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
                padding=10, border_radius=8,
                bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.WHITE),
                border=ft.Border.all(1, ft.Colors.with_opacity(
                    0.3, ft.Colors.BLUE_GREY_700)),
            ))
        return ft.Column([
            ft.Row([
                ft.Text(f"{len(roles)} rol(es)", size=12, color=ft.Colors.GREY_400),
                ft.Container(expand=True),
                ft.FilledButton("NUEVO ROL", icon=ft.Icons.ADD,
                                style=BTN_PRIMARIO,
                                on_click=lambda _e: _editar_rol(None)),
            ]),
            tarjetas,
        ], spacing=10, scroll=ft.ScrollMode.AUTO, expand=True)

    def _eliminar_rol(rol: dict):
        ok, err = db_manager.eliminar_rol(int(rol["id"]))
        snack(page, "Rol eliminado" if ok else err, ok=ok)
        _recargar("roles")

    def _vista_usuarios():
        usuarios = db_manager.listar_usuarios()
        filas = []
        for u in usuarios:
            def _edit(_e, usr=u):
                _editar_usuario(usr)

            def _del(_e, usr=u):
                if (usr.get("usuario") or "").lower() == (usuario_actual or "").lower():
                    snack(page, "No podés eliminar tu propio usuario", ok=False)
                    return
                _confirmar(
                    f"Eliminar usuario {usr['usuario']}",
                    "El usuario se eliminará definitivamente.",
                    lambda usr=usr: _eliminar_usuario(usr))

            filas.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(u.get("usuario") or "", size=12)),
                ft.DataCell(ft.Text(u.get("nombre") or "—", size=12)),
                ft.DataCell(ft.Text(u.get("rol") or "—", size=12,
                                    color=ft.Colors.CYAN_300)),
                ft.DataCell(ft.Container(
                    content=ft.Text("ACTIVO" if u.get("activo") else "INACTIVO",
                                    size=9, color=ft.Colors.WHITE,
                                    weight=ft.FontWeight.BOLD),
                    bgcolor=(ft.Colors.with_opacity(0.3, ft.Colors.GREEN_700)
                             if u.get("activo") else
                             ft.Colors.with_opacity(0.3, ft.Colors.RED_700)),
                    padding=4, border_radius=4)),
                ft.DataCell(ft.Row([
                    ft.IconButton(icon=ft.Icons.EDIT, tooltip="Editar",
                                  icon_color=ft.Colors.BLUE_300, on_click=_edit),
                    ft.IconButton(icon=ft.Icons.DELETE_OUTLINE,
                                  tooltip="Eliminar",
                                  icon_color=ft.Colors.RED_300, on_click=_del),
                ], spacing=0)),
            ]))
        tabla = ft.DataTable(
            columns=[ft.DataColumn(ft.Text("Usuario")),
                     ft.DataColumn(ft.Text("Nombre")),
                     ft.DataColumn(ft.Text("Rol")),
                     ft.DataColumn(ft.Text("Estado")),
                     ft.DataColumn(ft.Text("Acciones"))],
            rows=filas, column_spacing=26, heading_row_height=34)
        if not filas:
            tabla.rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text("Sin usuarios", italic=True,
                                    color=ft.Colors.GREY_500)),
                *[ft.DataCell(ft.Text("")) for _ in range(4)],
            ]))
        return ft.Column([
            ft.Row([
                ft.Text(f"{len(usuarios)} usuario(s)", size=12,
                        color=ft.Colors.GREY_400),
                ft.Container(expand=True),
                ft.FilledButton("NUEVO USUARIO", icon=ft.Icons.PERSON_ADD,
                                style=BTN_PRIMARIO,
                                on_click=lambda _e: _editar_usuario(None)),
            ]),
            ft.Container(
                content=ft.Column([tabla], scroll=ft.ScrollMode.AUTO),
                expand=True, border=ft.Border.all(1, ft.Colors.BLUE_GREY_700),
                border_radius=6, padding=8),
        ], spacing=10, expand=True)

    def _eliminar_usuario(usuario: dict):
        ok, err = db_manager.eliminar_usuario(int(usuario["id"]))
        snack(page, "Usuario eliminado" if ok else err, ok=ok)
        _recargar("usuarios")

    tab_roles.on_click = lambda _e: _recargar("roles")
    tab_usuarios.on_click = lambda _e: _recargar("usuarios")
    _recargar("usuarios" if seccion_inicial == "usuarios" else "roles")

    return ft.Container(
        content=ft.Column([
            ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.MANAGE_ACCOUNTS, size=24,
                            color=ft.Colors.BLUE_300),
                    ft.Text("ROLES Y USUARIOS", size=20,
                            weight=ft.FontWeight.BOLD),
                ], alignment=ft.MainAxisAlignment.CENTER, spacing=10),
                bgcolor=ft.Colors.BLUE_900, padding=8,
                alignment=ft.Alignment.CENTER),
            ft.Container(height=8),
            ft.Row([
                tab_roles, tab_usuarios,
                ft.Container(expand=True),
                ft.OutlinedButton("VOLVER", icon=ft.Icons.ARROW_BACK,
                                  on_click=lambda _e: on_volver()),
            ], spacing=8),
            ft.Container(height=6),
            contenedor,
            ft.Text("Solo un usuario con rol ADMIN puede administrar roles y "
                    "usuarios. El rol ADMIN siempre tiene todos los permisos.",
                    size=11, italic=True, color=ft.Colors.GREY_500),
        ], spacing=8, expand=True),
        padding=20, expand=True,
    )

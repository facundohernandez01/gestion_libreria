"""ABM de proveedores con contactos (modal)."""
from __future__ import annotations

import flet as ft

from ui.helpers import abrir_dialogo, cerrar_dialogo, snack


def ProveedoresModal(db_manager, page: ft.Page, on_cerrar=None):
    estado = {"modo": "lista", "editando": None}
    contactos_controles: list[tuple[ft.TextField, ft.TextField, ft.TextField]] = []

    titulo = ft.Text("PROVEEDORES", size=18, weight=ft.FontWeight.BOLD)
    contenido = ft.Container(width=780, height=470)
    acciones = ft.Row([], alignment=ft.MainAxisAlignment.END, spacing=8)

    tabla = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Proveedor")),
            ft.DataColumn(ft.Text("CUIT")),
            ft.DataColumn(ft.Text("Teléfono")),
            ft.DataColumn(ft.Text("Email")),
            ft.DataColumn(ft.Text("Contactos")),
            ft.DataColumn(ft.Text("Acciones")),
        ],
        rows=[], column_spacing=14, heading_row_height=36,
    )
    buscar = ft.TextField(
        label="Buscar", prefix_icon=ft.Icons.SEARCH, width=320,
        hint_text="Nombre, CUIT o teléfono…", dense=True,
    )

    # ---------- lista ----------
    def _cargar_lista(e=None):
        termino = buscar.value or ""
        datos = db_manager.listar_proveedores(termino)
        tabla.rows.clear()
        for p in datos:
            def _editar(_e, prov=p):
                _abrir_form(prov)

            def _borrar(_e, prov=p):
                _confirmar_borrar(prov)

            tabla.rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(p["nombre"], size=12, weight=ft.FontWeight.BOLD)),
                ft.DataCell(ft.Text(p.get("cuit") or "", size=12)),
                ft.DataCell(ft.Text(p.get("telefono") or "", size=12)),
                ft.DataCell(ft.Text(p.get("email") or "", size=12)),
                ft.DataCell(ft.Text(str(p.get("contactos_count") or 0), size=12)),
                ft.DataCell(ft.Row([
                    ft.IconButton(icon=ft.Icons.EDIT, icon_color=ft.Colors.BLUE_400,
                                  tooltip="Editar", on_click=_editar),
                    ft.IconButton(icon=ft.Icons.DELETE, icon_color=ft.Colors.RED_400,
                                  tooltip="Eliminar", on_click=_borrar),
                ], spacing=0)),
            ]))
        if not datos:
            tabla.rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text("Sin proveedores cargados", italic=True,
                                    color=ft.Colors.GREY_500, size=12)),
                ft.DataCell(ft.Text("")), ft.DataCell(ft.Text("")),
                ft.DataCell(ft.Text("")), ft.DataCell(ft.Text("")),
                ft.DataCell(ft.Text("")),
            ]))
        estado["modo"] = "lista"
        titulo.value = "PROVEEDORES"
        contenido.content = ft.Column([
            ft.Row([
                buscar,
                ft.Container(expand=True),
                ft.FilledButton("NUEVO PROVEEDOR", icon=ft.Icons.ADD,
                                on_click=lambda _e: _abrir_form(None)),
            ], spacing=10),
            ft.Container(content=ft.Column([tabla], scroll=ft.ScrollMode.AUTO),
                         height=390, border=ft.Border.all(1, ft.Colors.BLUE_GREY_700),
                         border_radius=6, padding=8),
        ], spacing=10)
        acciones.controls = [
            ft.TextButton("CERRAR", on_click=lambda _e: _cerrar()),
        ]
        page.update()

    def _confirmar_borrar(p):
        def _ok(_e):
            eliminado = db_manager.eliminar_proveedor(int(p["id"]))
            try:
                confirm.open = False
                page.update()
            except Exception:
                cerrar_dialogo(page)
            _cargar_lista()
            if eliminado:
                snack(page, "Proveedor eliminado", ok=True)
            else:
                snack(page, "No se pudo eliminar (tiene órdenes asociadas)", ok=False)

        confirm = ft.AlertDialog(
            modal=True,
            title=ft.Text("Eliminar proveedor"),
            content=ft.Text(f"¿Eliminar '{p['nombre']}'?\n"
                            "Los productos quedarán sin proveedor."),
            actions=[
                ft.TextButton("CANCELAR", on_click=lambda _e: cerrar_dialogo(page)),
                ft.FilledButton("ELIMINAR", icon=ft.Icons.DELETE,
                                style=ft.ButtonStyle(bgcolor=ft.Colors.RED_700,
                                                     color=ft.Colors.WHITE),
                                on_click=_ok),
            ],
        )
        abrir_dialogo(page, confirm)

    # ---------- formulario ----------
    contenedor_contactos = ft.Column([], spacing=6, scroll=ft.ScrollMode.AUTO, height=170)

    def _refrescar_contactos():
        filas = []
        for f_nombre, f_tel, f_email in list(contactos_controles):
            def _quitar(_e, fn=f_nombre):
                contactos_controles[:] = [c for c in contactos_controles if c[0] is not fn]
                _refrescar_contactos()

            filas.append(ft.Row([
                f_nombre, f_tel, f_email,
                ft.IconButton(icon=ft.Icons.REMOVE_CIRCLE, icon_color=ft.Colors.RED_400,
                              tooltip="Quitar", on_click=_quitar),
            ], spacing=8))
        contenedor_contactos.controls = filas
        page.update()

    def _agregar_contacto(nombre="", telefono="", email=""):
        f_nombre = ft.TextField(label="Nombre", value=nombre, width=200, dense=True)
        f_tel = ft.TextField(label="Teléfono", value=telefono, width=160, dense=True)
        f_email = ft.TextField(label="Email", value=email, width=220, dense=True)
        contactos_controles.append((f_nombre, f_tel, f_email))
        _refrescar_contactos()

    def _abrir_form(p):
        contactos_controles.clear()
        datos = db_manager.obtener_proveedor(int(p["id"])) if p else None
        if datos:
            for c in datos.get("contactos") or []:
                _agregar_contacto(c.get("nombre") or "", c.get("telefono") or "",
                                  c.get("email") or "")
        nombre = ft.TextField(label="Nombre *", value=(datos or {}).get("nombre") or "",
                              width=380)
        cuit = ft.TextField(label="CUIT", value=(datos or {}).get("cuit") or "", width=200)
        telefono = ft.TextField(label="Teléfono", value=(datos or {}).get("telefono") or "",
                                width=200)
        email = ft.TextField(label="Email", value=(datos or {}).get("email") or "", width=280)
        direccion = ft.TextField(label="Dirección",
                                 value=(datos or {}).get("direccion") or "", width=480)
        notas = ft.TextField(label="Notas", value=(datos or {}).get("notas") or "",
                             width=580, multiline=True, min_lines=1, max_lines=3)

        def _guardar(_e):
            if not (nombre.value or "").strip():
                snack(page, "El nombre es obligatorio", ok=False)
                return
            contactos = [
                {"nombre": fn.value, "telefono": ft.value, "email": fe.value}
                for fn, ft_, fe in contactos_controles
                if (fn.value or "").strip()
            ]
            pid = db_manager.guardar_proveedor({
                "id": (datos or {}).get("id"),
                "nombre": nombre.value,
                "cuit": cuit.value,
                "telefono": telefono.value,
                "email": email.value,
                "direccion": direccion.value,
                "notas": notas.value,
            }, contactos)
            if pid:
                snack(page, "Proveedor guardado", ok=True)
                _cargar_lista()
            else:
                snack(page, "No se pudo guardar (¿nombre duplicado?)", ok=False)

        estado["modo"] = "form"
        titulo.value = "EDITAR PROVEEDOR" if datos else "NUEVO PROVEEDOR"
        contenido.content = ft.Column([
            ft.Row([nombre, cuit], spacing=10),
            ft.Row([telefono, email], spacing=10),
            direccion,
            notas,
            ft.Divider(),
            ft.Row([
                ft.Text("Contactos", weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_400),
                ft.Container(expand=True),
                ft.TextButton("AGREGAR CONTACTO", icon=ft.Icons.PERSON_ADD,
                              on_click=lambda _e: _agregar_contacto()),
            ], spacing=8),
            contenedor_contactos,
        ], spacing=10, scroll=ft.ScrollMode.AUTO)
        _refrescar_contactos()
        acciones.controls = [
            ft.TextButton("CANCELAR", on_click=lambda _e: _cargar_lista()),
            ft.FilledButton("GUARDAR", icon=ft.Icons.SAVE, on_click=_guardar,
                            style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN_700,
                                                 color=ft.Colors.WHITE)),
        ]
        page.update()

    def _cerrar():
        if on_cerrar:
            on_cerrar()
        cerrar_dialogo(page)

    buscar.on_change = _cargar_lista
    dialog = ft.AlertDialog(
        modal=True,
        title=titulo,
        content=contenido,
        actions=[acciones],
        actions_alignment=ft.MainAxisAlignment.END,
        open=True,
    )
    _cargar_lista()
    return dialog

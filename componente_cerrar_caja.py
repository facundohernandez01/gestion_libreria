import flet as ft
from datetime import datetime

def CerrarCajaModal(db_manager, caja_id, on_caja_cerrada, page):
    """Modal de cierre de caja"""
    
    # Obtener información de la caja
    caja = db_manager.obtener_caja_abierta()
    ventas = db_manager.obtener_ventas_del_dia(caja_id)
    gastos = db_manager.obtener_gastos_caja(caja_id)
    
    total_ventas = sum(v['total'] for v in ventas)
    total_gastos = sum(g['monto'] for g in gastos)
    importe_apertura = caja['importe_apertura']
    importe_cierre = importe_apertura + total_ventas - total_gastos
    
    # Lista de gastos
    gastos_list = ft.ListView(height=150, spacing=5)
    
    def actualizar_gastos():
        """Actualiza la lista de gastos"""
        gastos_actuales = db_manager.obtener_gastos_caja(caja_id)
        total_g = sum(g['monto'] for g in gastos_actuales)
        
        gastos_list.controls.clear()
        for gasto in gastos_actuales:
            gasto_row = ft.Container(
                content=ft.Row([
                    ft.Text(gasto['concepto'], width=300),
                    ft.Text(gasto['fecha'][11:16] if len(gasto['fecha']) > 11 else 'N/A', width=80),
                    ft.Text(f"${gasto['monto']:.2f}", width=100, text_align=ft.TextAlign.RIGHT)
                ]),
                bgcolor=ft.Colors.RED_900,
                padding=10,
                border_radius=5
            )
            gastos_list.controls.append(gasto_row)
        
        if not gastos_actuales:
            gastos_list.controls.append(
                ft.Text("No se registraron gastos", italic=True, text_align=ft.TextAlign.CENTER)
            )
        
        # Actualizar totales
        nuevo_importe = importe_apertura + total_ventas - total_g
        total_gastos_text.value = f"$ {total_g:.2f}"
        total_caja_text.value = f"$ {nuevo_importe:.2f}"
        
        page.update()
    
    # Cargar gastos iniciales
    for gasto in gastos:
        gasto_row = ft.Container(
            content=ft.Row([
                ft.Text(gasto['concepto'], width=300),
                ft.Text(gasto['fecha'][11:16] if len(gasto['fecha']) > 11 else 'N/A', width=80),
                ft.Text(f"${gasto['monto']:.2f}", width=100, text_align=ft.TextAlign.RIGHT)
            ]),
            bgcolor=ft.Colors.RED_900,
            padding=10,
            border_radius=5
        )
        gastos_list.controls.append(gasto_row)
    
    if not gastos:
        gastos_list.controls.append(
            ft.Text("No se registraron gastos", italic=True, text_align=ft.TextAlign.CENTER)
        )
    
    # Campos
    observaciones_field = ft.TextField(
        label="COMENTARIOS",
        multiline=True,
        min_lines=3,
        max_lines=5,
        width=500
    )
    
    # Textos dinámicos
    total_gastos_text = ft.Text(f"$ {total_gastos:.2f}", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.RED_700)
    total_caja_text = ft.Text(f"$ {importe_cierre:.2f}", size=20, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_700)
    
    def agregar_gasto(e):
        """Abre diálogo para agregar gasto"""
        concepto_field = ft.TextField(label="Concepto del gasto", width=300)
        monto_field = ft.TextField(
            label="Monto",
            prefix_text="$",
            keyboard_type=ft.KeyboardType.NUMBER,
            width=200
        )
        
        def guardar_gasto(e):
            try:
                if not concepto_field.value or not monto_field.value:
                    mostrar_error("Complete todos los campos")
                    return
                
                monto = float(monto_field.value)
                if monto <= 0:
                    mostrar_error("El monto debe ser mayor a 0")
                    return
                
                gasto_id = db_manager.agregar_gasto(caja_id, monto, concepto_field.value)
                
                if gasto_id:
                    mostrar_exito("Gasto registrado")
                    dialog_gasto.open = False
                    actualizar_gastos()
                else:
                    mostrar_error("Error al registrar el gasto")
            except ValueError:
                mostrar_error("Ingrese un monto válido")
        
        dialog_gasto = ft.AlertDialog(
            title=ft.Text("Agregar Gasto"),
            content=ft.Column([
                concepto_field,
                monto_field
            ], tight=True, height=150),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: cerrar_dialog(dialog_gasto)),
                ft.ElevatedButton("Guardar", on_click=guardar_gasto)
            ],
            open=True
        )
        
        page.overlay.append(dialog_gasto)
        page.update()
    
    def cerrar_dialog(dialog):
        dialog.open = False
        page.update()
    
    def confirmar_cierre(e):
        """Confirma el cierre de caja"""
        observaciones = observaciones_field.value or ""
        exito = db_manager.cerrar_caja(caja_id, observaciones)
        
        if exito:
            mostrar_exito("Caja cerrada exitosamente")
            on_caja_cerrada()
        else:
            mostrar_error("Error al cerrar la caja")
    
    def cancelar(e):
        """Cancela el cierre"""
        on_caja_cerrada()
    
    def mostrar_error(mensaje):
        snack = ft.SnackBar(
            content=ft.Text(mensaje, color=ft.Colors.WHITE),
            bgcolor=ft.Colors.RED_700
        )
        page.overlay.append(snack)
        snack.open = True
        page.update()
    
    def mostrar_exito(mensaje):
        snack = ft.SnackBar(
            content=ft.Text(mensaje, color=ft.Colors.WHITE),
            bgcolor=ft.Colors.GREEN_700
        )
        page.overlay.append(snack)
        snack.open = True
        page.update()
    
    # Resumen
    resumen = ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Text("Importe apertura:", size=14, width=200),
                ft.Text(f"$ {importe_apertura:.2f}", size=14, weight=ft.FontWeight.BOLD)
            ]),
            ft.Row([
                ft.Text("Total ventas:", size=14, width=200),
                ft.Text(f"$ {total_ventas:.2f}", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_700)
            ]),
            ft.Row([
                ft.Text("Total gastos:", size=14, width=200),
                total_gastos_text
            ]),
            ft.Divider(),
            ft.Row([
                ft.Text("TOTAL EN CAJA:", size=16, weight=ft.FontWeight.BOLD, width=200),
                total_caja_text
            ])
        ]),
        bgcolor=ft.Colors.BLUE_GREY_900,
        padding=15,
        border_radius=10
    )
    
    # Contenido del modal
    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Row([
            ft.Icon(ft.Icons.LOCK, color=ft.Colors.RED_700),
            ft.Text("CERRAR CAJA", size=24, weight=ft.FontWeight.BOLD)
        ]),
        content=ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.CALENDAR_TODAY),
                    ft.Text("Fecha y hora: "),
                    ft.Text(datetime.now().strftime("%d/%m/%Y %H:%M:%S"), weight=ft.FontWeight.BOLD)
                ]),
                ft.Divider(),
                ft.Row([
                    ft.Text("GASTOS", weight=ft.FontWeight.BOLD, size=16),
                    ft.IconButton(
                        icon=ft.Icons.ADD_CIRCLE,
                        tooltip="Agregar gasto",
                        on_click=agregar_gasto
                    )
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Container(
                    content=gastos_list,
                    border=ft.border.all(1, ft.Colors.OUTLINE),
                    border_radius=5,
                    padding=5
                ),
                ft.Divider(),
                resumen,
                observaciones_field
            ], scroll=ft.ScrollMode.AUTO, spacing=10),
            width=550,
            height=450
        ),
        actions=[
            ft.TextButton(
                "CANCELAR",
                on_click=cancelar,
                style=ft.ButtonStyle(color=ft.Colors.RED_700)
            ),
            ft.ElevatedButton(
                "CONFIRMAR CIERRE",
                icon=ft.Icons.LOCK,
                on_click=confirmar_cierre,
                style=ft.ButtonStyle(
                    bgcolor=ft.Colors.RED_700,
                    color=ft.Colors.WHITE
                )
            )
        ],
        actions_alignment=ft.MainAxisAlignment.END,
        open=True
    )
    
    return dialog
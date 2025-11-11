import flet as ft
from datetime import datetime

def AbrirCajaView(db_manager, on_caja_abierta, page):
    """Vista de apertura de caja"""
    
    fecha_text = ft.Text(
        value=datetime.now().strftime("%d/%m/%Y %H:%M"),
        size=20,
        weight=ft.FontWeight.BOLD
    )
    
    importe_field = ft.TextField(
        label="$ Importe al abrir",
        prefix_text="$",
        keyboard_type=ft.KeyboardType.NUMBER,
        width=300,
        autofocus=True,
        value="0"
    )
    
    observaciones_field = ft.TextField(
        label="Observaciones",
        multiline=True,
        min_lines=3,
        max_lines=5,
        width=500
    )
    
    def abrir_caja(e):
        try:
            importe = float(importe_field.value or 0)
            
            if importe < 0:
                mostrar_error("El importe debe ser mayor o igual a 0")
                return
            
            observaciones = observaciones_field.value or ""
            caja_id = db_manager.abrir_caja(importe, observaciones)
            
            if caja_id:
                mostrar_exito("Caja abierta correctamente")
                on_caja_abierta(caja_id)
            else:
                mostrar_error("Error al abrir la caja")
                
        except ValueError:
            mostrar_error("Ingrese un importe válido")
    
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
    
    btn_aceptar = ft.ElevatedButton(
        text="ABRIR CAJA",
        icon=ft.Icons.LOCK_OPEN,
        on_click=abrir_caja,
        style=ft.ButtonStyle(
            color=ft.Colors.WHITE,
            bgcolor=ft.Colors.GREEN_700
        ),
        width=200,
        height=50
    )
    
    btn_salir = ft.OutlinedButton(
        text="SALIR",
        icon=ft.Icons.EXIT_TO_APP,
        on_click=lambda e: page.window.close(),
        width=200,
        height=50
    )
    
    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Container(
                    content=ft.Text("ABRIR CAJA", size=30, weight=ft.FontWeight.BOLD),
                    bgcolor=ft.Colors.BLUE_900,
                    padding=20,
                    alignment=ft.alignment.center
                ),
                ft.Container(height=20),
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.CALENDAR_TODAY, size=30),
                            ft.Text("FECHA ACTUAL: ", size=18, weight=ft.FontWeight.BOLD),
                            fecha_text
                        ],
                        alignment=ft.MainAxisAlignment.CENTER
                    ),
                    padding=10
                ),
                ft.Container(height=20),
                ft.Container(
                    content=importe_field,
                    alignment=ft.alignment.center
                ),
                ft.Container(height=10),
                ft.Container(
                    content=observaciones_field,
                    alignment=ft.alignment.center
                ),
                ft.Container(height=30),
                ft.Row(
                    controls=[btn_salir, btn_aceptar],
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=20
                )
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            scroll=ft.ScrollMode.AUTO
        ),
        padding=20,
        expand=True
    )
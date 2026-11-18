import flet as ft
from ui.paleta import N
from datetime import datetime
from ui.helpers import snack as _snack

def AbrirCajaView(db_manager, on_caja_abierta, page):
    """Vista de apertura de caja"""
    
    fecha_text = ft.Text(
        value=datetime.now().strftime("%d/%m/%Y %H:%M"),
        size=20,
        weight=ft.FontWeight.BOLD
    )
    
    importe_field = ft.TextField(
        label="$ Importe al abrir",
        prefix=ft.Text("$"),
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
    
    # En una migración jamás apropiarse automáticamente de la caja de otro POS.
    # Solo administración puede ver/asociar cajas heredadas sin terminal.
    legacy_cajas = []
    if hasattr(db_manager, "listar_cajas_sin_terminal"):
        try:
            legacy_cajas = db_manager.listar_cajas_sin_terminal()
        except Exception:
            pass

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
                mostrar_error(
                    getattr(db_manager, "ultimo_error_caja", "") or
                    "Error al abrir la caja"
                )
                
        except ValueError:
            mostrar_error("Ingrese un importe válido")
    
    def mostrar_error(mensaje):
        _snack(page, mensaje, ok=False)

    def mostrar_exito(mensaje):
        _snack(page, mensaje, ok=True)

    async def _salir(e):
        await page.window.close()

    caja_heredada = ft.Dropdown(
        label="Caja existente sin terminal", width=340,
        options=[
            ft.dropdown.Option(
                key=str(c["id"]),
                text=f"Caja #{c['id']} · {str(c.get('fecha_apertura') or '')[:16]}"
            )
            for c in legacy_cajas
        ],
    )
    confirmar_heredada = ft.Checkbox(
        label="Verifiqué que esta caja abierta pertenece a este equipo POS.",
        value=False,
    )

    def vincular_caja_heredada(e):
        if not caja_heredada.value or not confirmar_heredada.value:
            mostrar_error("Seleccioná una caja y confirmá que corresponde a este POS.")
            return
        try:
            caja_id = int(caja_heredada.value)
            result = db_manager.asociar_caja_existente(caja_id)
            if not result.get("ok") or result.get("caja_id") != caja_id:
                raise ValueError("El servidor no confirmó la vinculación.")
            mostrar_exito(f"Caja #{caja_id} vinculada a esta terminal.")
            on_caja_abierta(caja_id)
        except Exception as exc:
            mostrar_error("No se pudo asociar la caja: " + str(exc))

    panel_caja_heredada = ft.Container(
        visible=bool(legacy_cajas),
        content=ft.Column([
            ft.Text("Caja abierta de una versión anterior", weight=ft.FontWeight.BOLD),
            ft.Text(
                "Elegí la caja histórica de ESTE equipo. No se asocia automáticamente "
                "para evitar mezclar ventas entre terminales.", size=12,
            ),
            caja_heredada,
            confirmar_heredada,
            ft.OutlinedButton(
                "Asociar caja existente a este POS",
                icon=ft.Icons.LINK,
                on_click=vincular_caja_heredada,
            ),
        ], spacing=9),
        padding=14,
        border_radius=8,
        bgcolor=ft.Colors.with_opacity(0.05, N.BLUE_700),
    )

    btn_aceptar = ft.FilledButton(
        content="ABRIR CAJA",
        icon=ft.Icons.LOCK_OPEN,
        on_click=abrir_caja,
        style=ft.ButtonStyle(
            color=ft.Colors.WHITE,
            bgcolor=N.GREEN_700
        ),
        width=200,
        height=50
    )
    
    btn_salir = ft.OutlinedButton(
        content="SALIR",
        icon=ft.Icons.EXIT_TO_APP,
        on_click=_salir,
        width=200,
        height=50
    )
    
    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Container(
                    content=ft.Text("ABRIR CAJA", size=30, weight=ft.FontWeight.BOLD),
                    bgcolor=N.BLUE_900,
                    padding=20,
                    alignment=ft.Alignment.CENTER
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
                    alignment=ft.Alignment.CENTER
                ),
                ft.Container(height=10),
                ft.Container(
                    content=observaciones_field,
                    alignment=ft.Alignment.CENTER
                ),
                ft.Container(height=20),
                panel_caja_heredada,
                ft.Container(height=20),
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
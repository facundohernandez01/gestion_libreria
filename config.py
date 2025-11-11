import flet as ft
from database_manager import DatabaseManager

def ConfigModal(page: ft.Page):
    db = DatabaseManager()
    
    # Cargar valores actuales
    config = db.get_all_config()
    
    nombre_negocio = ft.TextField(
        label="Nombre del negocio",
        value=config.get("NOMBRE_NEGOCIO", ""),
        width=400,
    )
    mp_user_id = ft.TextField(
        label="MercadoPago USER_ID",
        value=config.get("MP_USER_ID", ""),
        width=400,
    )
    mp_access_token = ft.TextField(
        label="MercadoPago ACCESS_TOKEN",
        value=config.get("MP_ACCESS_TOKEN", ""),
        width=400,
        password=True,
        can_reveal_password=True,
    )

    def guardar_config(e):
        db.set_config("NOMBRE_NEGOCIO", nombre_negocio.value)
        db.set_config("MP_USER_ID", mp_user_id.value)
        db.set_config("MP_ACCESS_TOKEN", mp_access_token.value)
        page.snack_bar = ft.SnackBar(ft.Text("Configuración guardada con éxito"))
        page.snack_bar.open = True
        page.update()
        page.close(dialog)

    guardar_btn = ft.ElevatedButton("Guardar", icon=ft.Icons.SAVE, on_click=guardar_config)

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Configuración del sistema"),
        content=ft.Column(
            [nombre_negocio, mp_user_id, mp_access_token],
            tight=True,
            spacing=10,
        ),
        actions=[guardar_btn],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    return dialog

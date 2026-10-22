import flet as ft
from database_manager import DatabaseManager
import requests
import os

def ConfigModal(page: ft.Page):
    page.title = "Configurar Mercado Pago"
    page.scroll = "adaptive"

    db = DatabaseManager()
    config = db.get_all_config()

    # Cargar valores desde DB
    access_token = config.get("ACCESS_TOKEN", "")
    user_id = config.get("USER_ID", "")
    external_pos_id = config.get("EXTERNAL_POS_ID", "")
    external_store_id = config.get("EXTERNAL_STORE_ID", "")

    
    # Campos
    token_field = ft.TextField(label="Access Token", value=access_token, width=400)
    user_field = ft.TextField(label="User ID", value=user_id, width=400)
    resultado_text = ft.Text("", size=14, color=ft.Colors.GREEN_400)    
    nombre_negocio_field = ft.TextField(
        label="Nombre del negocio",
        value=config.get("NOMBRE_NEGOCIO", ""),
        width=400
    )
    qr_url_saved = config.get("QR_URL", "")    
    pos_actual = config.get("EXTERNAL_POS_ID", "")
    store_actual = config.get("EXTERNAL_STORE_ID", "")

    if pos_actual and store_actual:
        resultado_text.value = f"POS actual: {pos_actual}\nStore actual: {store_actual}"
    qr_image = ft.Image(src=qr_url_saved if qr_url_saved else None, width=140, height=140)
    pos_dropdown = ft.Dropdown(width=400)

    pos_list = []

    def obtener_pos(e):
        token = token_field.value.strip()
        uid = user_field.value.strip()
        if not token or not uid:
            resultado_text.value = "❌ Debes ingresar Access Token y User ID"
            page.update()
            return

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        pos_resp = requests.get("https://api.mercadopago.com/pos", headers=headers)
        if pos_resp.status_code != 200:
            resultado_text.value = f"❌ Error listando POS: {pos_resp.status_code}"
            page.update()
            return

        nonlocal pos_list
        pos_list = pos_resp.json().get("results", [])
        if not pos_list:
            resultado_text.value = "⚠️ No hay POS configurados"
            page.update()
            return

        pos_dropdown.options.clear()
        for i, pos in enumerate(pos_list):
            pos_dropdown.options.append(ft.dropdown.Option(key=str(i), text=f"{pos['name']} ({pos.get('external_id', 'N/A')})"))

        resultado_text.value = f"✅ {len(pos_list)} POS encontrados. Selecciona uno."
        page.update()

    def seleccionar_pos(e):
        if not pos_dropdown.value:
            return

        idx = int(pos_dropdown.value)
        pos = pos_list[idx]
        external_pos_id = pos.get("external_id", "N/A")
        store_id = pos.get("store_id", None)
        qr_url = pos.get("qr", {}).get("image", None)

        # Obtener External Store ID
        token = token_field.value.strip()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        external_store_id = "N/A"
        if store_id:
            store_resp = requests.get(f"https://api.mercadopago.com/stores/{store_id}", headers=headers)
            if store_resp.status_code == 200:
                external_store_id = store_resp.json().get("external_id", "N/A")

        # Mostrar resultados
        resultado_text.value = f"✅ External POS ID: {external_pos_id}\n✅ External Store ID: {external_store_id}"
        if qr_url:
            qr_image.src = qr_url

        # Guardar en DB
        db.set_config("ACCESS_TOKEN", token_field.value)
        db.set_config("USER_ID", user_field.value)
        db.set_config("EXTERNAL_POS_ID", external_pos_id)
        db.set_config("EXTERNAL_STORE_ID", external_store_id)
        db.set_config("NOMBRE_NEGOCIO", nombre_negocio_field.value)
        if qr_url:
            db.set_config("QR_URL", qr_url)

        page.update()
    
    guardar_btn = ft.ElevatedButton(
        "Guardar configuración",
        icon=ft.Icons.SAVE,
        on_click=lambda e: guardar_config()
    )

    def guardar_config(e):
        # Guardar en DB
        db.set_config("NOMBRE_NEGOCIO", nombre_negocio_field.value)
        db.set_config("ACCESS_TOKEN", token_field.value)
        db.set_config("USER_ID", user_field.value)
        db.set_config("EXTERNAL_POS_ID", pos_actual if pos_actual else "")
        db.set_config("EXTERNAL_STORE_ID", store_actual if store_actual else "")
        db.set_config("QR_URL", qr_image.src if qr_image.src else "")

        # Descargar QR si existe
        if qr_image.src:
            img_dir = os.path.join(os.getcwd(), "img")
            os.makedirs(img_dir, exist_ok=True)
            img_path = os.path.join(img_dir, "qr.png")
            r = requests.get(qr_image.src)
            if r.status_code == 200:
                with open(img_path, "wb") as f:
                    f.write(r.content)

        # Mostrar mensaje y cerrar modal
        page.snack_bar = ft.SnackBar(ft.Text("Configuración guardada con éxito"))
        page.snack_bar.open = True
        page.update()
        page.close(dialog)  # 👈 Cierra el modal
        

    def imprimir_qr_action(e):
        img_path = os.path.join(os.getcwd(), "img", "qr.png")
        if not os.path.exists(img_path):
            page.snack_bar = ft.SnackBar(ft.Text("⚠️ No se encontró el QR para imprimir"))
            page.snack_bar.open = True
            page.update()
            return
        try:
            os.startfile(img_path, "print")  # Solo Windows
        except Exception as err:
            page.snack_bar = ft.SnackBar(ft.Text(f"Error al imprimir: {err}"))
            page.snack_bar.open = True
            page.update()
                
    guardar_btn = ft.ElevatedButton("Guardar", icon=ft.Icons.SAVE, on_click=guardar_config)
    cancelar_btn = ft.ElevatedButton("Cancelar", icon=ft.Icons.CLOSE, on_click=lambda e: page.close(dialog))
    imprimirqr = ft.ElevatedButton("Imprimir QR", icon=ft.Icons.PRINT, on_click=imprimir_qr_action)
       

    def descargar_qr(e):
        if not qr_image.src:
            resultado_text.value = "⚠️ Primero selecciona un POS con QR"
            page.update()
            return

        try:
            img_dir = os.path.join(os.getcwd(), "img")
            os.makedirs(img_dir, exist_ok=True)
            img_path = os.path.join(img_dir, "qr.png")

            r = requests.get(qr_image.src)
            if r.status_code == 200:
                with open(img_path, "wb") as f:
                    f.write(r.content)
                resultado_text.value = f"✅ QR descargado en {img_path}"
            else:
                resultado_text.value = "❌ Error descargando QR"
        except Exception as ex:
            resultado_text.value = f"❌ Error: {ex}"

        page.update()



            


    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Configuración de la tienda y Mercado Pago"),
        content=ft.Column([
            nombre_negocio_field,
            token_field,
            user_field,            
            ft.Row([
                ft.ElevatedButton("Obtener POS", on_click=obtener_pos),
                pos_dropdown,
                ft.ElevatedButton("Seleccionar POS", on_click=seleccionar_pos)
            ], spacing=6),
            resultado_text,
            qr_image,
        ], spacing=10, height=400),
        actions=[cancelar_btn, imprimirqr, guardar_btn],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    return dialog

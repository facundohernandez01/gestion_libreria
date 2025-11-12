import flet as ft
import requests
import os

def ConfiguracionMercadoPago(page: ft.Page):
    page.title = "Configurar Mercado Pago"
    page.scroll = "adaptive"

    # Inputs para Access Token y User ID
    access_token = os.getenv("ACCESS_TOKEN", "")
    user_id = os.getenv("USER_ID", "")

    token_field = ft.TextField(label="Access Token", value=access_token, width=400)
    user_field = ft.TextField(label="User ID", value=user_id, width=400)

    resultado_text = ft.Text("", size=14, color=ft.Colors.GREEN_400)
    qr_image = ft.Image(width=200, height=200)

    def obtener_datos(e):
        token = token_field.value.strip()
        uid = user_field.value.strip()
        if not token or not uid:
            resultado_text.value = "❌ Debes ingresar Access Token y User ID"
            page.update()
            return

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        # 1. Listar POS
        pos_resp = requests.get("https://api.mercadopago.com/pos", headers=headers)
        if pos_resp.status_code != 200:
            resultado_text.value = f"❌ Error listando POS: {pos_resp.status_code}"
            page.update()
            return

        pos_list = pos_resp.json().get("results", [])
        if not pos_list:
            resultado_text.value = "⚠️ No hay POS configurados"
            page.update()
            return

        pos = pos_list[0]  # Tomamos el primero (puedes hacer selector)
        external_pos_id = pos.get("external_id", "N/A")
        store_id = pos.get("store_id", None)
        qr_url = pos.get("qr", {}).get("image", None)

        # 2. Obtener External Store ID
        external_store_id = "N/A"
        if store_id:
            store_resp = requests.get(f"https://api.mercadopago.com/stores/{store_id}", headers=headers)
            if store_resp.status_code == 200:
                external_store_id = store_resp.json().get("external_id", "N/A")

        # Mostrar resultados
        resultado_text.value = f"✅ External POS ID: {external_pos_id}\n✅ External Store ID: {external_store_id}"
        if qr_url:
            qr_image.src = qr_url

        page.update()

    # Layout
    page.add(
        ft.Column([
            ft.Text("Configuración Mercado Pago", size=20, weight=ft.FontWeight.BOLD),
            token_field,
            user_field,
            ft.ElevatedButton("Obtener Datos", on_click=obtener_datos),
            resultado_text,
            qr_image
        ], spacing=20)
    )

# Para ejecutar la app:
if __name__ == "__main__":
    ft.app(target=ConfiguracionMercadoPago)
import flet as ft
import requests
import time
import os
from database_manager import DatabaseManager
import threading

def ConfigModal(page: ft.Page):
    page.title = "Configurar Mercado Pago"
    page.scroll = "adaptive"

    db = DatabaseManager()
    config = db.get_all_config()

    def sincronizar_store_id():
        external_store_id = db.get_config("EXTERNAL_STORE_ID")
        token = db.get_config("ACCESS_TOKEN")
        uid = db.get_config("USER_ID")

        # 🔸 Si falta alguno de estos datos, no hacemos nada
        if not external_store_id or not token or not uid:
            print("⚠️ No hay datos suficientes para sincronizar el STORE_ID.")
            return

        try:
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            url = f"https://api.mercadopago.com/users/{uid}/stores"

            print("🔍 Buscando store_id para:", external_store_id)
            resp = requests.get(url, headers=headers)

            if resp.status_code == 200:
                stores = resp.json().get("results", [])
                for store in stores:
                    if store.get("external_id") == external_store_id:
                        numeric_id = store.get("id")
                        if numeric_id:
                            db.set_config("STORE_ID", str(numeric_id))
                            print(f"✅ STORE_ID sincronizado correctamente: {numeric_id}")
                            return
                print("⚠️ No se encontró una tienda con ese EXTERNAL_STORE_ID.")
            else:
                print(f"❌ Error al consultar tiendas: {resp.status_code} - {resp.text}")

        except Exception as ex:
            print(f"❌ Error sincronizando STORE_ID: {ex}")

    sincronizar_store_id()

    # Valores actuales
    access_token = config.get("ACCESS_TOKEN", "")
    user_id = config.get("USER_ID", "")
    external_pos_id = config.get("EXTERNAL_POS_ID", "")
    external_store_id = config.get("EXTERNAL_STORE_ID", "")
    qr_url_saved = config.get("QR_URL", "")

    # Campos
    token_field = ft.TextField(label="Access Token", value=access_token, width=400)
    user_field = ft.TextField(label="User ID", value=user_id, width=400)
    nombre_negocio_field = ft.TextField(label="Nombre del negocio", value=config.get("NOMBRE_NEGOCIO", ""), width=400)
    resultado_text = ft.Text("", size=14, color=ft.Colors.GREEN_400)
    qr_image = ft.Image(src=qr_url_saved if qr_url_saved else None, width=140, height=140)
    
    # Detectar si es primera vez (sin POS ni Store)
    if not external_pos_id or not external_store_id:
        def crear_store_y_pos(token, uid, nombre_negocio):
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            # Crear Store
            store_payload = {
                "name": nombre_negocio,
                "external_id": f"STORE{int(time.time())}",
                "location": {
                    "street_number": "123",
                    "street_name": "Principal",
                    "city_name": "Rosario",
                    "state_name": "Santa Fe",
                    "latitude": -32.9468,
                    "longitude": -60.6393,
                    "reference": "Local comercial"
                }
            }
            store_resp = requests.post(f"https://api.mercadopago.com/users/{uid}/stores", headers=headers, json=store_payload)
            if store_resp.status_code not in [200, 201]:
                return None, None, None, f"Error creando Store: {store_resp.text}"
            store_id = store_resp.json()["id"]
            external_store_id = store_resp.json()["external_id"]

            # Crear POS
            pos_payload = {
                "name": "Caja Principal",
                "external_id": f"POS{int(time.time())}",
                "store_id": store_id,
                "fixed_amount": True,
                "category": 621102
            }
            pos_resp = requests.post("https://api.mercadopago.com/pos", headers=headers, json=pos_payload)
            if pos_resp.status_code not in [200, 201]:
                return None, None, None, f"Error creando POS: {pos_resp.text}"
            external_pos_id = pos_resp.json()["external_id"]
            qr_url = pos_resp.json().get("qr", {}).get("image", "")
            return external_store_id, external_pos_id, qr_url, None

        resultado_text.value = "⚠️ No hay POS ni Store configurados. Ingresa credenciales y crea uno."
    
    def crear_handler(e):
        resultado_text.value = "⏳ Creando..."
        page.update()

        def worker():
            store_id, pos_id, qr_url, error = crear_store_y_pos(
                token_field.value.strip(),
                user_field.value.strip(),
                nombre_negocio_field.value.strip()
            )

            if error:
                resultado_text.value = error
            else:
                resultado_text.value = f"✅ Store y POS creados\nStore: {store_id}\nPOS: {pos_id}"
                qr_image.src = qr_url
                db.set_config("ACCESS_TOKEN", token_field.value)
                db.set_config("USER_ID", user_field.value)
                db.set_config("EXTERNAL_STORE_ID", store_id)
                db.set_config("EXTERNAL_POS_ID", pos_id)
                db.set_config("QR_URL", qr_url)
                db.set_config("NOMBRE_NEGOCIO", nombre_negocio_field.value)

            page.update()

        threading.Thread(target=worker, daemon=True).start()

        crear_btn = ft.ElevatedButton(
            "Abrir local (Crear Store y POS)",
            icon=ft.Icons.STORE,
            on_click=crear_handler

        )

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Configuración inicial"),
            content=ft.Column([
                nombre_negocio_field,
                token_field,
                user_field,
                crear_btn,
                resultado_text,
                qr_image
            ], spacing=10),
            actions=[ft.ElevatedButton("Cerrar", on_click=lambda e: page.close(dialog))]
        )
        return dialog

    # Función para crear Store y POS
    def crear_store_y_pos(token, uid, nombre_negocio):
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        # Crear Store
        store_payload = {
            "name": nombre_negocio,
            "external_id": f"STORE{int(time.time())}",
            "location": {
                "street_number": "123",
                "street_name": "Principal",
                "city_name": "Rosario",
                "state_name": "Santa Fe",
                "latitude": -32.9468,
                "longitude": -60.6393,
                "reference": "Local comercial"
            }
        }
        store_resp = requests.post(f"https://api.mercadopago.com/users/{uid}/stores", headers=headers, json=store_payload)
        if store_resp.status_code not in [200, 201]:
            return None, None, None, f"❌ Error creando Store: {store_resp.text}"
        store_id = store_resp.json().get("id")
        external_store_id = store_resp.json().get("external_id")

        # Crear POS
        pos_payload = {
            "name": "Caja Principal",
            "external_id": f"POS{int(time.time())}",
            "store_id": store_id,
            "fixed_amount": True,
            "category": 621102
        }
        pos_resp = requests.post("https://api.mercadopago.com/pos", headers=headers, json=pos_payload)
        if pos_resp.status_code not in [200, 201]:
            return None, None, None, f"❌ Error creando POS: {pos_resp.text}"
        external_pos_id = pos_resp.json().get("external_id")
        qr_url = pos_resp.json().get("qr", {}).get("image", "")

        return external_store_id, external_pos_id, qr_url, None

    if not external_pos_id or not external_store_id:
            creando = False  # flag para evitar doble creación

            def crear_handler(e):
                nonlocal creando
                if creando:
                    return
                creando = True
                crear_btn.disabled = True
                resultado_text.value = "⏳ Creando tienda y POS..."
                page.update()

                def worker():
                    store_id, pos_id, qr_url, error = crear_store_y_pos(
                        token_field.value.strip(),
                        user_field.value.strip(),
                        nombre_negocio_field.value.strip()
                    )

                    if error:
                        resultado_text.value = error
                        crear_btn.disabled = False
                        creando = False
                    else:
                        resultado_text.value = f"✅ Store y POS creados\nStore: {store_id}\nPOS: {pos_id}"
                        qr_image.src = qr_url
                        db.set_config("ACCESS_TOKEN", token_field.value)
                        db.set_config("USER_ID", user_field.value)
                        db.set_config("EXTERNAL_STORE_ID", store_id)
                        db.set_config("EXTERNAL_POS_ID", pos_id)
                        db.set_config("QR_URL", qr_url)
                        db.set_config("NOMBRE_NEGOCIO", nombre_negocio_field.value)
                        crear_btn.text = "Listo"
                        crear_btn.icon = ft.Icons.CHECK
                        crear_btn.on_click = lambda ev: page.close(dialog)

                    page.update()

                threading.Thread(target=worker, daemon=True).start()

            crear_btn = ft.ElevatedButton(
                "Habilitar cobro con QR estático",
                icon=ft.Icons.STORE,
                on_click=crear_handler
            )

            dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text("Configuración inicial de Mercado Pago"),
                content=ft.Column([
                    nombre_negocio_field,
                    token_field,
                    user_field,
                    crear_btn,
                    resultado_text,
                    qr_image
                ], spacing=10),
                actions=[ft.ElevatedButton("Cerrar", on_click=lambda e: page.close(dialog))]
            )
            return dialog

    # Si ya hay configuración → mostrar UI original
    pos_dropdown = ft.Dropdown(width=400)
    resultado_text.value = f"POS actual: {external_pos_id}\nStore actual: {external_store_id}"

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
        token = token_field.value.strip()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        external_store_id = "N/A"
        if store_id:
            store_resp = requests.get(f"https://api.mercadopago.com/stores/{store_id}", headers=headers)
            if store_resp.status_code == 200:
                external_store_id = store_resp.json().get("external_id", "N/A")
        resultado_text.value = f"✅ External POS ID: {external_pos_id}\n✅ External Store ID: {external_store_id}"
        if qr_url:
            qr_image.src = qr_url
        db.set_config("ACCESS_TOKEN", token_field.value)
        db.set_config("USER_ID", user_field.value)
        db.set_config("EXTERNAL_POS_ID", external_pos_id)
        db.set_config("EXTERNAL_STORE_ID", external_store_id)
        db.set_config("NOMBRE_NEGOCIO", nombre_negocio_field.value)
        if qr_url:
            db.set_config("QR_URL", qr_url)
        page.update()

    def guardar_config(e):
        db.set_config("NOMBRE_NEGOCIO", nombre_negocio_field.value)
        db.set_config("ACCESS_TOKEN", token_field.value)
        db.set_config("USER_ID", user_field.value)
        db.set_config("EXTERNAL_POS_ID", external_pos_id)
        db.set_config("EXTERNAL_STORE_ID", external_store_id)
        db.set_config("QR_URL", qr_image.src if qr_image.src else "")
        page.snack_bar = ft.SnackBar(ft.Text("Configuración guardada con éxito"))
        page.snack_bar.open = True
        page.update()
        page.close(dialog)

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
        
    def crear_pos_adicional(e):
        token = token_field.value.strip()
        uid = user_field.value.strip()
        store_id = db.get_config("EXTERNAL_STORE_ID")

        if not token or not uid or not store_id:
            resultado_text.value = "❌ Faltan datos para crear el POS adicional"
            page.update()
            return

        resultado_text.value = "⏳ Creando nuevo POS..."
        page.update()

        def worker():
            try:
                headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
                pos_payload = {
                    "name": f"Caja {int(time.time())}",
                    "external_id": f"POS{int(time.time())}",
                    "store_id": store_id,
                    "fixed_amount": True,
                    "category": 621102
                }
                pos_resp = requests.post("https://api.mercadopago.com/pos", headers=headers, json=pos_payload)
                if pos_resp.status_code not in [200, 201]:
                    resultado_text.value = f"❌ Error creando POS: {pos_resp.text}"
                else:
                    pos_data = pos_resp.json()
                    nuevo_pos = pos_data.get("external_id")
                    qr_url = pos_data.get("qr", {}).get("image", "")
                    resultado_text.value = f"✅ Nuevo POS creado: {nuevo_pos}"
                    qr_image.src = qr_url
                    db.set_config("EXTERNAL_POS_ID", nuevo_pos)
                    if qr_url:
                        db.set_config("QR_URL", qr_url)
            except Exception as ex:
                resultado_text.value = f"❌ Error: {ex}"
            page.update()

        threading.Thread(target=worker, daemon=True).start()

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Configuración de la tienda y Mercado Pago"),
        content=ft.Column([
            nombre_negocio_field,
            token_field,
            user_field,
            ft.Row([
                ft.ElevatedButton("Crear nuevo POS", icon=ft.Icons.ADD, on_click=crear_pos_adicional),
                ft.ElevatedButton("Obtener POS", on_click=obtener_pos),
                pos_dropdown,
                ft.ElevatedButton("Seleccionar POS", on_click=seleccionar_pos)
            ], spacing=6),
            resultado_text,
            qr_image
        ], spacing=10, height=400),
        actions=[
            ft.ElevatedButton("Cancelar", icon=ft.Icons.CLOSE, on_click=lambda e: page.close(dialog)),
            ft.ElevatedButton("Imprimir QR", icon=ft.Icons.PRINT, on_click=imprimir_qr_action),
            ft.ElevatedButton("Descargar QR", icon=ft.Icons.DOWNLOAD, on_click=descargar_qr),
            ft.ElevatedButton("Guardar", icon=ft.Icons.SAVE, on_click=guardar_config)
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    return dialog
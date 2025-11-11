import flet as ft
import asyncio
from mp_qr import crear_orden, verificar_estado

def NuevaVentaView(db_manager, caja_id, on_confirmar, on_cerrar, filter_mode, page):
    """Modal de nueva venta"""
    
    carrito = []
    
    # Campos de búsqueda
    search_field = ft.TextField(
        label="Buscar producto",
        prefix_icon=ft.Icons.SEARCH,
        width=400,
        autofocus=True
    )
    
    filtro_dropdown = ft.Dropdown(
        width=150,
        value=filter_mode or "descripcion",
        options=[
            ft.dropdown.Option("descripcion", "Descripción"),
            ft.dropdown.Option("codigo", "Código")
        ]
    )
    
    # Listas
    resultados_list = ft.ListView(height=120, spacing=4)
    carrito_list = ft.ListView(height=120, spacing=4)
    total_text = ft.Text(
        value="TOTAL: $0.00",
        size=15,
        weight=ft.FontWeight.BOLD,
        color=ft.Colors.GREEN_700
    )
    
    def buscar_producto(e=None):
        """Busca productos - búsqueda predictiva"""
        termino = search_field.value
        if not termino or len(termino) < 1:
            resultados_list.controls.clear()
            page.update()
            return
        
        campo = filtro_dropdown.value
        productos = db_manager.buscar_productos(termino, campo)
        
        resultados_list.controls.clear()
        
        for producto in productos[:10]:
            stock_color = ft.Colors.GREEN_700 if producto['stock_actual'] > producto['stock_minimo'] else ft.Colors.RED_700
            
            resultado_row = ft.Container(
                content=ft.Row([
                    ft.Column([
                        ft.Text(producto['descripcion'], weight=ft.FontWeight.BOLD, size=13),
                        ft.Text(f"Código: {producto['codigo']}", size=10, color=ft.Colors.GREY_500)
                    ], spacing=2, expand=True),
                    ft.Column([
                        ft.Text(f"${producto['precio_lista']:.2f}", size=15, weight=ft.FontWeight.BOLD),
                        ft.Text(f"Stock: {producto['stock_actual']}", size=10, color=stock_color)
                    ], horizontal_alignment=ft.CrossAxisAlignment.END, spacing=2),
                    ft.IconButton(
                        icon=ft.Icons.ADD_SHOPPING_CART,
                        icon_color=ft.Colors.GREEN_700,
                        on_click=lambda e, p=producto: agregar_al_carrito(p),
                        tooltip="Agregar"
                    )
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                bgcolor=ft.Colors.BLUE_GREY_900,
                padding=10,
                border_radius=5,
                on_click=lambda e, p=producto: agregar_al_carrito(p),
                ink=True
            )
            resultados_list.controls.append(resultado_row)
        
        page.update()
    
    def agregar_al_carrito(producto):
        """Agrega producto al carrito"""
        if producto['stock_actual'] <= 0:
            mostrar_error("Producto sin stock")
            return
        
        # Verificar si ya está en el carrito
        for item in carrito:
            if item['producto_id'] == producto['id']:
                if item['cantidad'] < producto['stock_actual']:
                    item['cantidad'] += 1
                    item['subtotal'] = item['cantidad'] * item['precio_unitario']
                else:
                    mostrar_error("No hay más stock disponible")
                    return
                break
        else:
            carrito.append({
                'producto_id': producto['id'],
                'descripcion': producto['descripcion'],
                'precio_unitario': producto['precio_lista'],
                'cantidad': 1,
                'subtotal': producto['precio_lista'],
                'stock_disponible': producto['stock_actual']
            })
        
        # Limpiar búsqueda
        search_field.value = ""
        resultados_list.controls.clear()
        actualizar_carrito()
        search_field.focus()
    
    def actualizar_carrito():
        """Actualiza vista del carrito"""
        carrito_list.controls.clear()
        total = 0
        
        for i, item in enumerate(carrito):
            total += item['subtotal']
            
            carrito_row = ft.Container(
                content=ft.Row([
                    ft.Text(item['descripcion'], width=220, size=12),
                    ft.Row([
                        ft.IconButton(
                            icon=ft.Icons.REMOVE,
                            icon_size=16,
                            on_click=lambda e, idx=i: cambiar_cantidad(idx, -1)
                        ),
                        ft.Text(f"x{item['cantidad']}", width=35, text_align=ft.TextAlign.CENTER, size=13),
                        ft.IconButton(
                            icon=ft.Icons.ADD,
                            icon_size=16,
                            on_click=lambda e, idx=i: cambiar_cantidad(idx, 1)
                        )
                    ], spacing=0),
                    ft.Text(f"${item['subtotal']:.2f}", width=90, text_align=ft.TextAlign.RIGHT, 
                           weight=ft.FontWeight.BOLD, size=13),
                    ft.IconButton(
                        icon=ft.Icons.DELETE,
                        icon_size=18,
                        icon_color=ft.Colors.RED_700,
                        on_click=lambda e, idx=i: eliminar_item(idx)
                    )
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                bgcolor=ft.Colors.GREEN_900,
                padding=8,
                border_radius=5
            )
            carrito_list.controls.append(carrito_row)
        
        total_text.value = f"TOTAL: ${total:.2f}"
        
        if not carrito:
            carrito_list.controls.append(
                ft.Text("Carrito vacío", italic=True, text_align=ft.TextAlign.CENTER)
            )
        
        page.update()
    
    def cambiar_cantidad(index, delta):
        """Cambia cantidad de un item"""
        item = carrito[index]
        nueva_cantidad = item['cantidad'] + delta
        
        if nueva_cantidad <= 0:
            eliminar_item(index)
        elif nueva_cantidad <= item['stock_disponible']:
            item['cantidad'] = nueva_cantidad
            item['subtotal'] = item['cantidad'] * item['precio_unitario']
            actualizar_carrito()
        else:
            mostrar_error("No hay más stock disponible")
    
    def eliminar_item(index):
        """Elimina item del carrito"""
        carrito.pop(index)
        actualizar_carrito()
    
    def confirmar_venta(imprimir=False):
        """Confirma la venta"""
        if not carrito:
            mostrar_error("El carrito está vacío")
            return
        
        venta_id, exito = db_manager.crear_venta(caja_id, carrito)
        
        if exito:
            if imprimir:
                imprimir_ticket(venta_id)
            mostrar_exito(f"Venta #{venta_id} registrada exitosamente")
            dialog.open = False
            page.update()
            def delayed_close():
                import time
                time.sleep(0.15)
                on_confirmar()

            page.run_thread(delayed_close)    
        else:
            mostrar_error("Error al registrar la venta")
    
    def imprimir_ticket(venta_id):
        """Imprime ticket de venta"""
        # Aquí iría la lógica de impresión
        print(f"Imprimiendo ticket de venta #{venta_id}")
        mostrar_exito(f"Ticket #{venta_id} enviado a impresora")
    
    def abortar(e):
        """Cierra el modal correctamente"""
        dialog.open = False
        page.update()

        def delayed_close():
            import time
            time.sleep(0.15)
            on_cerrar()

        page.run_thread(delayed_close)


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
    
    # Handler para Enter en búsqueda
    def on_search_submit(e):
        """Enter en búsqueda - agregar al carrito si es por código"""
        if filtro_dropdown.value == "codigo" and search_field.value:
            # Buscar producto exacto por código
            productos = db_manager.buscar_productos(search_field.value, "codigo")
            if len(productos) == 1:
                agregar_al_carrito(productos[0])
            elif len(productos) == 0:
                mostrar_error("Código no encontrado")
            else:
                buscar_producto()
        else:
            buscar_producto()
    
    # Configurar búsqueda predictiva
    search_field.on_change = buscar_producto  # Búsqueda en tiempo real
    search_field.on_submit = on_search_submit  # Enter para agregar
    cancelar_pago = False

    def pagar_con_qr(e):
        nonlocal cancelar_pago  # permite modificar variable externa
        cancelar_pago = False

        if not carrito:
            mostrar_error("El carrito está vacío")
            return

        total = sum(item['subtotal'] for item in carrito)
        external_pos_id = "POS1762813032"
        external_store_id = "SUC001"

        # --- Overlay modal mientras se espera el pago ---
        overlay_spinner = ft.AlertDialog(
            modal=True,
            title=ft.Text("Esperando pago del cliente...", size=16, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                content=ft.Column([
                    ft.ProgressRing(width=70, height=70, color=ft.Colors.PURPLE_400),
                    ft.Text("Escaneá el QR con Mercado Pago", size=13, color=ft.Colors.GREY_400)
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER),
                alignment=ft.alignment.center,
                width=300,
                height=180
            ),
            actions=[
                ft.TextButton(
                    "CANCELAR",
                    icon=ft.Icons.CANCEL,
                    style=ft.ButtonStyle(color=ft.Colors.RED_600),
                    on_click=lambda e: cancelar_espera()
                )
            ],
            actions_alignment=ft.MainAxisAlignment.CENTER,
            open=True
        )
        page.dialog = overlay_spinner
        page.update()

        # --- Función para cancelar ---
        def cancelar_espera():
            nonlocal cancelar_pago
            cancelar_pago = True
            overlay_spinner.open = False
            page.update()
            mostrar_error("Pago cancelado por el usuario")

            # 🔹 Llamada para liberar el POS inmediatamente
            try:
                import requests
                url = f"https://api.mercadopago.com/instore/qr/seller/collectors/{USER_ID}/pos/{external_pos_id}/orders"
                resp = requests.delete(url, headers={
                    "Authorization": f"Bearer {ACCESS_TOKEN}",
                    "Content-Type": "application/json"
                })
                if resp.status_code in (200, 204):
                    print("✅ Orden eliminada correctamente, QR liberado.")
                else:
                    print(f"⚠️ No se pudo eliminar la orden ({resp.status_code})")
            except Exception as err:
                print(f"⚠️ Error al liberar QR: {err}")

        def log_ui(msg):
            snack = ft.SnackBar(content=ft.Text(msg), bgcolor=ft.Colors.BLUE_GREY_900)
            page.overlay.append(snack)
            snack.open = True
            page.update()

        # --- Crear orden ---
        ok = crear_orden(external_pos_id, external_store_id, total, cb=log_ui)
        if not ok:
            overlay_spinner.open = False
            page.update()
            mostrar_error("Error al crear la orden en Mercado Pago")
            return

        # --- Monitorear el pago ---
        def esperar_pago():
            try:
                for intento in range(60):  # 5 minutos aprox
                    if cancelar_pago:
                        print("🛑 Pago cancelado por el usuario.")
                        return
                    ok = verificar_estado(external_pos_id, cb=log_ui)
                    if ok:
                        overlay_spinner.open = False
                        page.update()
                        mostrar_exito("✅ Pago recibido. Confirmando venta...")
                        confirmar_venta(False)
                        return
                    time.sleep(5)

                # Timeout
                overlay_spinner.open = False
                page.update()
                mostrar_error("⏰ Tiempo agotado o pago no detectado.")

                # 🔹 Limpiar QR al finalizar el ciclo sin pago
                try:
                    import requests
                    url = f"https://api.mercadopago.com/instore/qr/seller/collectors/{USER_ID}/pos/{external_pos_id}/orders"
                    requests.delete(url, headers={
                        "Authorization": f"Bearer {ACCESS_TOKEN}",
                        "Content-Type": "application/json"
                    })
                    print("♻️ QR liberado por timeout.")
                except:
                    pass

            except Exception as err:
                overlay_spinner.open = False
                page.update()
                mostrar_error(f"⚠️ Error monitoreando pago: {err}")

        page.run_thread(esperar_pago)



    # Contenido del modal
    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Row([
            ft.Icon(ft.Icons.SHOPPING_CART, color=ft.Colors.GREEN_700),
            ft.Text("Nueva Venta", size=22, weight=ft.FontWeight.BOLD),
            ft.Container(expand=True),
            ft.Text(f"Modo: {filtro_dropdown.value}", size=12, color=ft.Colors.GREY_500)
        ]),
        content=ft.Container(
            content=ft.Column([
                ft.Row([
                    search_field,
                    filtro_dropdown
                ]),
                ft.Text("Resultados (click o Enter para agregar):", size=11, italic=True, color=ft.Colors.GREY_500),
                ft.Container(
                    content=resultados_list,
                    border=ft.border.all(1, ft.Colors.BLUE_GREY_700),
                    border_radius=5,
                    padding=5
                ),
                ft.Divider(),
                ft.Row([
                    ft.Icon(ft.Icons.SHOPPING_CART, color=ft.Colors.GREEN_700, size=20),
                    ft.Text("CARRITO", size=15, weight=ft.FontWeight.BOLD)
                ]),
                ft.Container(
                    content=carrito_list,
                    border=ft.border.all(1, ft.Colors.GREEN_700),
                    border_radius=5,
                    padding=5
                ),
                ft.Container(
                    content=total_text,
                    alignment=ft.alignment.center_right,
                    padding=10
                )
            ], scroll=ft.ScrollMode.AUTO, spacing=8),
            width=700,
            height=480
        ),
        actions=[
            ft.TextButton("ABORTAR", on_click=abortar),
            ft.ElevatedButton(
                "CONFIRMAR E IMPRIMIR",
                icon=ft.Icons.PRINT,
                on_click=lambda e: confirmar_venta(True),
                style=ft.ButtonStyle(
                    bgcolor=ft.Colors.BLUE_700,
                    color=ft.Colors.WHITE
                )
            ),
            ft.ElevatedButton(
                "PAGAR CON MERCADO PAGO",
                icon=ft.Icons.QR_CODE_2,
                on_click=pagar_con_qr,
                style=ft.ButtonStyle(
                    bgcolor=ft.Colors.PURPLE_700,
                    color=ft.Colors.WHITE
                )
            ),
            ft.ElevatedButton(
                "CONFIRMAR VENTA",
                icon=ft.Icons.CHECK_CIRCLE,
                on_click=lambda e: confirmar_venta(False),
                style=ft.ButtonStyle(
                    bgcolor=ft.Colors.GREEN_700,
                    color=ft.Colors.WHITE
                )
            )
        ],
        actions_alignment=ft.MainAxisAlignment.END,
        open=True
    )
    
    return dialog
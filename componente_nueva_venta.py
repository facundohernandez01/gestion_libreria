import flet as ft
import asyncio
import requests
from mp_qr import crear_orden, verificar_estado,  USER_ID, ACCESS_TOKEN
from database_manager import DatabaseManager
db = DatabaseManager()

external_pos_id = db.get_config_value("EXTERNAL_POS_ID") or ""
external_store_id = db.get_config_value("EXTERNAL_STORE_ID") or ""

def NuevaVentaView(db_manager, caja_id, on_confirmar, on_cerrar, filter_mode, page):
    """Modal de nueva venta"""
    log_box = ft.Container(
        bgcolor=ft.Colors.with_opacity(0.15, ft.Colors.BLUE_GREY_700),
        border_radius=6,
        padding=10,
        content=ft.Text(
            "ℹ️ Listo para registrar una venta.",
            size=13,
            color=ft.Colors.WHITE,
            selectable=False
        ),
        alignment=ft.alignment.center_left,
        width=280,
    )
    col_izquierda = ft.Container(
        content=log_box,
        expand=1,
        padding=10,
        bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.WHITE),
        border_radius=5
    )
    def mostrar_mensaje(mensaje, color):
        log_box.content.value = mensaje
        log_box.bgcolor = ft.Colors.with_opacity(0.2, color)
        log_box.content.color = ft.Colors.WHITE
        page.update()

    def mostrar_exito(mensaje):
        mostrar_mensaje(f"✅ {mensaje}", ft.Colors.GREEN_700)

    def mostrar_error(mensaje):
        mostrar_mensaje(f"⚠️ {mensaje}", ft.Colors.RED_700)

    def log_ui(msg):
        mostrar_mensaje(f"ℹ️ {msg}", ft.Colors.BLUE_GREY_700)

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
        color=ft.Colors.GREEN_200
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
                    ft.Text(item['descripcion'], width=200, size=12),
                    ft.Row([
                        ft.GestureDetector(
                        on_tap=lambda e, idx=i: cambiar_cantidad(idx, -1),
                        content=ft.Container(
                            content=ft.Icon(ft.Icons.REMOVE, size=10, color=ft.Colors.WHITE),
                            padding=ft.padding.only(right=8)  # agrega espacio a la derecha
                        )
                        ),
                        ft.Text(f"x{item['cantidad']}", width=25, text_align=ft.TextAlign.CENTER, size=12),
                        ft.GestureDetector(
                        on_tap=lambda e, idx=i: cambiar_cantidad(idx, 1),
                        content=ft.Container(
                            content=ft.Icon(ft.Icons.ADD, size=10, color=ft.Colors.WHITE),
                            padding=ft.padding.only(right=8)  # agrega espacio a la derecha
                        )
                        ),
                    ], spacing=0),
                    ft.Text(f"${item['subtotal']:.2f}", width=90, text_align=ft.TextAlign.RIGHT, 
                           weight=ft.FontWeight.BOLD, size=12),

                    ft.GestureDetector(
                        on_tap=lambda e, idx=i: eliminar_item(idx),
                        content=ft.Container(
                            content=ft.Icon(ft.Icons.DELETE, size=14, color=ft.Colors.RED_700),
                            padding=ft.padding.only(right=8)  # agrega espacio a la derecha
                    )
                    )
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                bgcolor=ft.Colors.GREEN_900,
                padding=0,
                border_radius=5,
                height=20
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
        nonlocal cancelar_pago
        cancelar_pago = False

        if not carrito:
            mostrar_error("El carrito está vacío")
            return

        total = sum(item['subtotal'] for item in carrito)
        external_pos_id =  db.get_config_value("EXTERNAL_POS_ID") or ""
        external_store_id = db.get_config_value("EXTERNAL_STORE_ID") or ""

        monitor_container = ft.Container(
            bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.BLUE_GREY_800),
            border_radius=8,
            padding=10,
            content=ft.Column([
                ft.ProgressRing(width=10, height=10, color=ft.Colors.PURPLE_400),
                ft.Text("El cliente debe escanear el QR con Mercado Pago...", size=10, color=ft.Colors.GREY_400),
            ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        )

        # Reemplazar log_box por monitor_container
        col_izquierda.content = monitor_container
        page.update()

        def log_ui(msg):
            monitor_container.content.controls.append(
                ft.Text(msg, color=ft.Colors.BLUE_100, size=12)
            )
            page.update()

        def cancelar_espera():
            nonlocal cancelar_pago
            cancelar_pago = True
            col_izquierda.content = log_box
            if cancel_button in dialog.actions:
                dialog.actions.remove(cancel_button)
            page.update()
            mostrar_error("Pago cancelado por el usuario")

        # Botón de cancelar visible mientras se monitorea
        cancel_button = ft.TextButton(
            "CANCELAR PAGO",
            icon=ft.Icons.CANCEL,
            style=ft.ButtonStyle(color=ft.Colors.RED_600),
            on_click=lambda e: cancelar_espera()
        )
        dialog.actions.insert(0, cancel_button)
        page.update()

        # === Lógica asincrónica del proceso de pago ===
        def proceso_pago():
            ok = crear_orden(external_pos_id, external_store_id, total, cb=log_ui)
            if not ok:
                dialog.content.content.controls.remove(monitor_container)
                page.update()
                mostrar_error("Error al crear la orden en Mercado Pago")
                return

            ok = verificar_estado(external_pos_id, cb=log_ui, cancelar=lambda: cancelar_pago)
            dialog.content.content.controls.remove(monitor_container)
            if cancel_button in dialog.actions:
                dialog.actions.remove(cancel_button)
            page.update()

            if ok and not cancelar_pago:
                col_izquierda.content = log_box
                page.update()
                mostrar_exito("✅ Pago recibido. Confirmando venta...")
                confirmar_venta(False)
            elif not cancelar_pago:
                col_izquierda.content = log_box  
                page.update()
                mostrar_error("⏰ Tiempo agotado o pago no detectado.")

        page.run_thread(proceso_pago)





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
                ft.Row([search_field, filtro_dropdown]),
                ft.Text("Resultados (click o Enter para agregar):", size=11, italic=True, color=ft.Colors.GREY_500),
                ft.Container(content=resultados_list, border=ft.border.all(1, ft.Colors.BLUE_GREY_700), border_radius=5, padding=5),
                ft.Divider(),
                
      
                
                ft.Row(
                    [
                        col_izquierda,  # Aquí irá log_box o monitor_container
                        ft.Column(
                            [   
                             ft.Row([
                                ft.Icon(ft.Icons.SHOPPING_CART, color=ft.Colors.GREEN_700, size=20),
                                ft.Text("CARRITO", size=15, weight=ft.FontWeight.BOLD),
                            ]),
                                ft.Container(content=carrito_list, border=ft.border.all(1, ft.Colors.GREEN_700), border_radius=5, padding=5, expand=True),
                                ft.Container(content=total_text, alignment=ft.alignment.center_right, padding=10)
                            
                            ],
                            expand=2,
                            spacing=10
                        )
                    ],
                    spacing=20,
                    expand=True
                )

            ],
            scroll=ft.ScrollMode.AUTO,
            spacing=8),
            height=500,
            width= 1000
            
        ),
        actions=[
            ft.TextButton("ABORTAR", on_click=abortar),
            ft.ElevatedButton("CONFIRMAR E IMPRIMIR", icon=ft.Icons.PRINT, on_click=lambda e: confirmar_venta(True), style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE)),

            ft.ElevatedButton(
                content=ft.Image(src="img/logomp.png", width=170, height=34),
                on_click=pagar_con_qr,
                style=ft.ButtonStyle(
                    bgcolor=ft.Colors.TRANSPARENT
                )
            ),

            ft.ElevatedButton("CONFIRMAR VENTA", icon=ft.Icons.CHECK_CIRCLE, on_click=lambda e: confirmar_venta(False), style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN_700, color=ft.Colors.WHITE))
        ],
        actions_alignment=ft.MainAxisAlignment.END,
        open=True
    )
    
    return dialog
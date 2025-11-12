import flet as ft
from datetime import datetime
from mostrar_qr import mostrar_qr
from config import ConfigModal

def VentanaPrincipal(page: ft.Page, db_manager, caja_id, on_nueva_venta_teclado, on_nueva_venta_lector, on_gestion_articulos, on_cerrar_caja):
    """Ventana principal con lista de ventas y acciones"""
    def abrir_qr(e):
        dlg = ft.AlertDialog(
            modal=True,
            content=mostrar_qr(page),
            actions=[
                ft.TextButton("Cerrar", on_click=lambda e: page.close(dlg))
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.open(dlg)

    def abrir_config(e):
        dlg = ConfigModal(page)
        page.open(dlg)

    
    # Obtener ventas del día
    ventas = db_manager.obtener_ventas_del_dia(caja_id)
    total_vendido = sum(v['total'] for v in ventas)
    
    print(f"Ventas encontradas: {len(ventas)}")
    
    # Estado para controlar qué ventas están expandidas
    ventas_expandidas = set()
    
    def crear_lista_ventas():
        """Crea la lista de ventas con items expandibles"""
        lista = ft.Column(spacing=5)
        
        for venta in ventas:
            venta_id = venta['id']
            expandido = venta_id in ventas_expandidas
            
            # Botón para expandir/contraer
            def toggle_expand(e, vid=venta_id):
                if vid in ventas_expandidas:
                    ventas_expandidas.remove(vid)
                else:
                    ventas_expandidas.add(vid)
                actualizar_ventas()
            
            icono_expand = ft.Icons.EXPAND_LESS if expandido else ft.Icons.EXPAND_MORE
            
            # Fila principal de venta estilo imagen
            venta_row = ft.Container(
                content=ft.Row([
                    ft.IconButton(
                        icon=icono_expand,
                        on_click=toggle_expand,
                        icon_color=ft.Colors.with_opacity(0.6, ft.Colors.WHITE),
                        icon_size=24
                    ),
                    ft.Icon(ft.Icons.RECEIPT, color=ft.Colors.BLUE_400, size=24),
                    ft.Column([
                        ft.Text(
                            f"Venta #{venta['id']:04d} - {venta['fecha'][11:16] if len(venta['fecha']) > 11 else 'N/A'}",
                            size=15,
                            weight=ft.FontWeight.BOLD,
                            color=ft.Colors.WHITE
                        ),
                        ft.Text(
                            venta['fecha'][11:16] if len(venta['fecha']) > 11 else 'N/A',
                            size=11,
                            color=ft.Colors.with_opacity(0.5, ft.Colors.WHITE)
                        )
                    ], spacing=2, expand=True),
                    ft.Column([
                        ft.Text(
                            f"${venta['total']:.2f}",
                            size=18,
                            weight=ft.FontWeight.BOLD,
                            color=ft.Colors.GREEN_400
                        ),
                        ft.Text(
                            f"{venta.get('items_count', 0)} items",
                            size=11,
                            color=ft.Colors.with_opacity(0.5, ft.Colors.WHITE),
                            text_align=ft.TextAlign.RIGHT
                        )
                    ], horizontal_alignment=ft.CrossAxisAlignment.END, spacing=2)
                ], alignment=ft.MainAxisAlignment.START),
                bgcolor=ft.Colors.with_opacity(0.15, ft.Colors.WHITE),
                padding=14,
                border_radius=8,
                
                animate=ft.Animation(150, ft.AnimationCurve.EASE_OUT)
            )
            
            lista.controls.append(venta_row)
            
            # Items de la venta (si está expandida)
            if expandido:
                items = db_manager.obtener_items_venta(venta_id)
                
                items_col = ft.Column(spacing=8)
                for item in items:
                    item_row = ft.Row([
                        ft.Container(width=5),  # Espaciado
                        ft.Icon(ft.Icons.CIRCLE, size=6, color=ft.Colors.BLUE_400),
                        ft.Text(item['producto_nombre'], size=13, color=ft.Colors.WHITE, expand=True),
                        ft.Text(f"x{item['cantidad']}", size=13, color=ft.Colors.with_opacity(0.6, ft.Colors.WHITE), width=50),
                        ft.Text(f"${item['precio_unitario']:.2f}", size=13, color=ft.Colors.with_opacity(0.6, ft.Colors.WHITE), width=80),
                        ft.Text(f"${item['subtotal']:.2f}", size=13, 
                               text_align=ft.TextAlign.RIGHT, weight=ft.FontWeight.W_500,
                               color=ft.Colors.GREEN_400, width=90)
                    ], spacing=8)
                    items_col.controls.append(item_row)
                
                items_container = ft.Container(
                    content=items_col,
                    bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.WHITE),
                    padding=12,
                    margin=ft.margin.only(left=10, right=2, top=0, bottom=5),
                    border_radius=8,
                    animate=ft.Animation(200, ft.AnimationCurve.EASE_IN_OUT)
                )
                lista.controls.append(items_container)
        
        if not ventas:
            lista.controls.append(
                ft.Container(
                    content=ft.Column([
                        ft.Icon(ft.Icons.RECEIPT_LONG_OUTLINED, size=80, color=ft.Colors.with_opacity(0.3, ft.Colors.WHITE)),
                        ft.Text(
                            "No hay ventas registradas aún",
                            text_align=ft.TextAlign.CENTER,
                            size=16,
                            color=ft.Colors.with_opacity(0.5, ft.Colors.WHITE)
                        )
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=15),
                    alignment=ft.alignment.center,
                    padding=60
                )
            )
        
        return lista
    
    # Contenedor de ventas con scroll vertical
    ventas_column = ft.Column(
        controls=[crear_lista_ventas()],
        scroll=ft.ScrollMode.ALWAYS,
        expand=True,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER
    )

    ventas_container = ft.Container(
        content=ventas_column,
        expand=True,
        height=400,
        border_radius=10,
        padding=1,
        bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.WHITE)
    )





        
    def actualizar_ventas():
        
        """Actualiza la lista de ventas"""
        ventas_column.controls = [crear_lista_ventas()]
        page.update()
    
    # Header mejorado
    header = ft.Container(
        content=ft.Column([

            ft.Row([
                ft.Icon(ft.Icons.CALENDAR_TODAY, size=20, color=ft.Colors.with_opacity(0.7, ft.Colors.WHITE)),
                ft.Text(f"{datetime.now().strftime('%d/%m/%Y')}", size=15, 
                       color=ft.Colors.with_opacity(0.9, ft.Colors.WHITE)),
                ft.Container(width=40),
                ft.Icon(ft.Icons.POINT_OF_SALE, size=20, color=ft.Colors.with_opacity(0.7, ft.Colors.WHITE)),
                ft.Text(f"Caja #{caja_id:04d}", size=20, weight=ft.FontWeight.BOLD,
                       color=ft.Colors.with_opacity(0.9, ft.Colors.WHITE))
            ], alignment=ft.MainAxisAlignment.CENTER, spacing=8)
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=3),
        bgcolor=ft.Colors.BLUE_900,
        padding=1
    )
    
    # Sección de ventas de hoy
    ventas_header = ft.Container(
        content=ft.Row([
            ft.Icon(ft.Icons.HISTORY, color=ft.Colors.BLUE_400, size=28),
            ft.Text("VENTAS DE HOY", size=22, weight=ft.FontWeight.BOLD)
        ], spacing=1),
        padding=ft.padding.only(left=1, bottom=1)
    )
    
    # Panel derecho con total y botones
    panel_derecho = ft.Container(
        content=ft.Column([
            # Botones de nueva venta
            ft.Container(
                content=ft.Column([
                    ft.ElevatedButton(
                        content=ft.Column([
                            ft.Icon(ft.Icons.KEYBOARD, size=40, color=ft.Colors.WHITE),
                            ft.Container(height=5),
                            ft.Text("Nueva venta", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                            ft.Text("(Teclado)", size=11, color=ft.Colors.with_opacity(0.8, ft.Colors.WHITE))
                        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=2, tight=True),
                        width=180,
                        height=110,
                        style=ft.ButtonStyle(
                            bgcolor=ft.Colors.GREEN_700,
                            shape=ft.RoundedRectangleBorder(radius=8),
                            elevation=4
                        ),
                        on_click=lambda e: on_nueva_venta_teclado()
                    ),
                    ft.ElevatedButton(
                        content=ft.Column([
                            ft.Icon(ft.Icons.QR_CODE_SCANNER, size=40, color=ft.Colors.WHITE),
                            ft.Container(height=5),
                            ft.Text("Nueva venta", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                            ft.Text("(Lector)", size=11, color=ft.Colors.with_opacity(0.8, ft.Colors.WHITE))
                        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=2, tight=True),
                        width=180,
                        height=110,
                        style=ft.ButtonStyle(
                            bgcolor=ft.Colors.BLUE_700,
                            shape=ft.RoundedRectangleBorder(radius=8),
                            elevation=4
                        ),
                        on_click=lambda e: on_nueva_venta_lector()
                    ),
                    ft.ElevatedButton(
                        content=ft.Row([
                            ft.Icon(ft.Icons.QR_CODE_2, size=20, color=ft.Colors.WHITE),
                            ft.Text("MOSTRAR QR", size=13, color=ft.Colors.WHITE)
                        ], alignment=ft.MainAxisAlignment.CENTER, spacing=8),
                        width=180,
                        height=110,
                        style=ft.ButtonStyle(
                            bgcolor=ft.Colors.GREEN,
                            shape=ft.RoundedRectangleBorder(radius=8),
                            elevation=3
                        ),
                        on_click=abrir_qr
                ),
                ]),
                alignment=ft.alignment.top_center
            ),
            ft.Container(expand=True),
            # Total vendido
            ft.Container(
                content=ft.Column([
                    ft.Text(f"Total vendido Caja #{caja_id:04d}",                     
                           size=14, 
                           color=ft.Colors.with_opacity(0.7, ft.Colors.WHITE),
                           text_align=ft.TextAlign.CENTER),
                    ft.Text(
                        f"$ {total_vendido:.2f}",
                        size=26,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.GREEN_400,
                        text_align=ft.TextAlign.CENTER
                    )
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=5),
                bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.WHITE),
                padding=4,
                border_radius=8,
                width=180,
                height=110,
                border=ft.border.all(2, ft.Colors.GREEN_700)
            ),
            ft.Container(height=20),
            # Botones de acción
            
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        padding=10,
        expand=True,
    )
    
    # Layout principal
    contenido_principal = ft.Row([
        # Panel izquierdo - Ventas
        ft.Column([
            ventas_header,
            ventas_container,
            ft.Container(height=20),

            ft.Row([
                ft.ElevatedButton(
                    content=ft.Row([
                        ft.Icon(ft.Icons.INVENTORY_2, size=20),
                        ft.Text("GESTIÓN ARTÍCULOS", size=13)
                    ], alignment=ft.MainAxisAlignment.CENTER, spacing=8),
                    width=200,
                    height=45,
                    style=ft.ButtonStyle(
                        shape=ft.RoundedRectangleBorder(radius=8)
                    ),
                    on_click=lambda e: on_gestion_articulos()
                ),
                ft.ElevatedButton(
                    content=ft.Row([
                        ft.Icon(ft.Icons.LOCK, size=20, color=ft.Colors.WHITE),
                        ft.Text("CERRAR CAJA", size=13, color=ft.Colors.WHITE)
                    ], alignment=ft.MainAxisAlignment.CENTER, spacing=8),
                    width=200,
                    height=45,
                    style=ft.ButtonStyle(
                        bgcolor=ft.Colors.RED_700,
                        shape=ft.RoundedRectangleBorder(radius=8),
                        elevation=3
                    ),
                    on_click=lambda e: on_cerrar_caja()
                ),
                # 🎯 Ejemplo de botón adicional
                ft.ElevatedButton(
                    content=ft.Row([
                        ft.Icon(ft.Icons.SETTINGS_APPLICATIONS, size=20, color=ft.Colors.WHITE),
                        ft.Text("Ajustes", size=13, color=ft.Colors.WHITE)
                    ], alignment=ft.MainAxisAlignment.CENTER, spacing=8),
                    width=200,
                    height=45,
                    style=ft.ButtonStyle(
                        bgcolor=ft.Colors.BLACK,
                        shape=ft.RoundedRectangleBorder(radius=8),
                        elevation=3
                    ),
                    on_click=abrir_config
                )
            ],        
            alignment=ft.MainAxisAlignment.START,  # izquierda
            spacing=15  # separación entre botones
            )
        ], 
        spacing=10,
        expand=3
        ),
        


        # Panel derecho - Acciones
         ft.Container(content=panel_derecho.content, expand=1)
    ], alignment=ft.MainAxisAlignment.CENTER, spacing=30, adaptive=True)
    
    # Función para refrescar ventas
    def cargar_ventas():
        """Refresca la lista de ventas desde fuera del componente"""
        nonlocal ventas, total_vendido
        ventas = db_manager.obtener_ventas_del_dia(caja_id)
        total_vendido = sum(v['total'] for v in ventas)
        print(f"🔄 Refrescando ventas: {len(ventas)} encontradas")
        
        # Actualizar el texto del total
        panel_derecho.content.controls[2].content.controls[1].value = f"$ {total_vendido:.2f}"
        
        actualizar_ventas()
    
    # Contenedor principal
    container_principal = ft.Container(
        content=ft.Column([
            header,
            ft.Container(height=25),
            ft.Container(
            content=contenido_principal,
            width=1200,  # ancho máximo
            alignment=ft.alignment.center
        )

        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, scroll=ft.ScrollMode.AUTO, expand=True),
        padding=20,
        expand=True
    )
    
    # Exponer la función como método del contenedor
    container_principal.cargar_ventas = cargar_ventas
    
    return container_principal
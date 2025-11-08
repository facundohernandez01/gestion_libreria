import flet as ft
from datetime import datetime

class GestionStockView(ft.Container):
    def __init__(self, db_manager, on_volver):
        super().__init__()
        self.db = db_manager
        self.on_volver = on_volver
        
        # Header
        self.header = ft.Container(
            content=ft.Text("GESTIÓN DE STOCK", size=28, weight=ft.FontWeight.BOLD),
            bgcolor=ft.Colors.BLUE_900,
            padding=20,
            alignment=ft.alignment.center
        )
        
        # Alertas de stock bajo
        self.alertas_container = ft.Container(
            bgcolor=ft.Colors.RED_900,
            padding=15,
            border_radius=10,
            visible=False
        )
        
        # Tabs para diferentes vistas
        self.tabs = ft.Tabs(
            selected_index=0,
            animation_duration=300,
            tabs=[
                ft.Tab(
                    text="STOCK BAJO",
                    icon=ft.Icons.WARNING,
                    content=self.crear_vista_stock_bajo()
                ),
                ft.Tab(
                    text="AJUSTE DE STOCK",
                    icon=ft.Icons.EDIT,
                    content=self.crear_vista_ajuste_stock()
                ),
                ft.Tab(
                    text="MOVIMIENTOS",
                    icon=ft.Icons.HISTORY,
                    content=self.crear_vista_movimientos()
                )
            ],
            expand=1
        )
        
        # Botón volver
        self.btn_volver = ft.ElevatedButton(
            text="VOLVER",
            icon=ft.Icons.ARROW_BACK,
            on_click=lambda e: self.on_volver()
        )
        
        # Layout
        self.content = ft.Column([
            self.header,
            ft.Container(height=10),
            self.alertas_container,
            ft.Container(height=10),
            self.tabs,
            ft.Container(height=10),
            ft.Container(
                content=self.btn_volver,
                alignment=ft.alignment.center
            )
        ], expand=True)
        
        self.padding = 20
        self.expand = True
    
    def crear_vista_stock_bajo(self):
        """Crea la vista de productos con stock bajo"""
        self.stock_bajo_list = ft.ListView(
            spacing=5,
            expand=True
        )
        
        return ft.Container(
            content=ft.Column([
                ft.Text("Productos con stock bajo o crítico", 
                       size=16, weight=ft.FontWeight.BOLD),
                ft.Container(height=10),
                self.stock_bajo_list
            ]),
            padding=10,
            expand=True
        )
    
    def crear_vista_ajuste_stock(self):
        """Crea la vista para ajustar stock"""
        self.buscar_producto_field = ft.TextField(
            label="Buscar producto",
            prefix_icon=ft.Icons.SEARCH,
            on_change=self.buscar_para_ajuste,
            width=400
        )
        
        self.resultados_ajuste = ft.ListView(
            height=300,
            spacing=5
        )
        
        return ft.Container(
            content=ft.Column([
                ft.Text("Buscar producto para ajustar stock", 
                       size=16, weight=ft.FontWeight.BOLD),
                ft.Container(height=10),
                self.buscar_producto_field,
                ft.Container(height=10),
                self.resultados_ajuste
            ]),
            padding=10,
            expand=True
        )
    
    def crear_vista_movimientos(self):
        """Crea la vista de historial de movimientos"""
        self.movimientos_list = ft.ListView(
            spacing=5,
            expand=True
        )
        
        return ft.Container(
            content=ft.Column([
                ft.Text("Historial de movimientos de stock", 
                       size=16, weight=ft.FontWeight.BOLD),
                ft.Container(height=10),
                self.movimientos_list
            ]),
            padding=10,
            expand=True
        )
    
    def cargar_stock_bajo(self):
        """Carga productos con stock bajo"""
        productos = self.db.obtener_productos_bajo_stock()
        
        self.stock_bajo_list.controls.clear()
        
        if productos:
            # Mostrar alerta
            self.alertas_container.content = ft.Row([
                ft.Icon(ft.Icons.WARNING, color=ft.Colors.YELLOW, size=30),
                ft.Text(
                    f"¡ATENCIÓN! {len(productos)} producto(s) con stock bajo o crítico",
                    size=16,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.YELLOW
                )
            ])
            self.alertas_container.visible = True
        else:
            self.alertas_container.visible = False
        
        for producto in productos:
            porcentaje_stock = (producto['stock_actual'] / producto['stock_minimo'] * 100) if producto['stock_minimo'] > 0 else 0
            
            if producto['stock_actual'] == 0:
                color = ft.Colors.RED_900
                icono = ft.Icons.CANCEL
                estado = "SIN STOCK"
            elif porcentaje_stock <= 50:
                color = ft.Colors.RED_800
                icono = ft.Icons.ERROR
                estado = "CRÍTICO"
            else:
                color = ft.Colors.ORANGE_800
                icono = ft.Icons.WARNING
                estado = "BAJO"
            
            producto_row = ft.Container(
                content=ft.Row([
                    ft.Icon(icono, color=ft.Colors.WHITE),
                    ft.Column([
                        ft.Text(producto['descripcion'], weight=ft.FontWeight.BOLD, size=14),
                        ft.Text(f"Código: {producto['codigo']}", size=11, color=ft.Colors.GREY_400)
                    ], spacing=2),
                    ft.Column([
                        ft.Text(f"Stock: {producto['stock_actual']}", size=14, weight=ft.FontWeight.BOLD),
                        ft.Text(f"Mínimo: {producto['stock_minimo']}", size=11)
                    ], horizontal_alignment=ft.CrossAxisAlignment.END),
                    ft.Container(
                        content=ft.Text(estado, size=12, weight=ft.FontWeight.BOLD),
                        bgcolor=ft.Colors.RED_700 if estado == "CRÍTICO" or estado == "SIN STOCK" else ft.Colors.ORANGE_700,
                        padding=8,
                        border_radius=5
                    ),
                    ft.ElevatedButton(
                        "AJUSTAR",
                        icon=ft.Icons.EDIT,
                        on_click=lambda e, p=producto: self.ajustar_stock_producto(p)
                    )
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                bgcolor=color,
                padding=15,
                border_radius=5
            )
            
            self.stock_bajo_list.controls.append(producto_row)
        
        if not productos:
            self.stock_bajo_list.controls.append(
                ft.Container(
                    content=ft.Column([
                        ft.Icon(ft.Icons.CHECK_CIRCLE, color=ft.Colors.GREEN_700, size=60),
                        ft.Text("¡Todos los productos tienen stock suficiente!", 
                               size=18, color=ft.Colors.GREEN_700, weight=ft.FontWeight.BOLD)
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
                    padding=40,
                    alignment=ft.alignment.center
                )
            )
        
        self.page.update()
    
    def buscar_para_ajuste(self, e):
        """Busca productos para ajustar stock"""
        termino = self.buscar_producto_field.value
        if not termino or len(termino) < 2:
            return
        
        productos = self.db.buscar_productos(termino, "descripcion")
        
        self.resultados_ajuste.controls.clear()
        
        for producto in productos[:10]:
            stock_color = ft.Colors.GREEN_700 if producto['stock_actual'] > producto['stock_minimo'] else ft.Colors.RED_700
            
            resultado_row = ft.Container(
                content=ft.Row([
                    ft.Column([
                        ft.Text(producto['descripcion'], weight=ft.FontWeight.BOLD, size=14),
                        ft.Text(f"Código: {producto['codigo']}", size=11, color=ft.Colors.GREY_400)
                    ], spacing=2),
                    ft.Column([
                        ft.Text(f"Stock actual: {producto['stock_actual']}", 
                               size=14, color=stock_color, weight=ft.FontWeight.BOLD),
                        ft.Text(f"Mínimo: {producto['stock_minimo']}", size=11)
                    ], horizontal_alignment=ft.CrossAxisAlignment.END),
                    ft.ElevatedButton(
                        "AJUSTAR",
                        icon=ft.Icons.EDIT,
                        on_click=lambda e, p=producto: self.ajustar_stock_producto(p)
                    )
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                bgcolor=ft.Colors.BLUE_GREY_900,
                padding=10,
                border_radius=5
            )
            
            self.resultados_ajuste.controls.append(resultado_row)
        
        self.page.update()
    
    def ajustar_stock_producto(self, producto):
        """Abre diálogo para ajustar stock de un producto"""
        cantidad_field = ft.TextField(
            label="Nueva cantidad de stock",
            keyboard_type=ft.KeyboardType.NUMBER,
            value=str(producto['stock_actual']),
            width=200
        )
        
        observaciones_field = ft.TextField(
            label="Observaciones",
            multiline=True,
            min_lines=2,
            width=400
        )
        
        def guardar_ajuste(e):
            try:
                nueva_cantidad = int(cantidad_field.value)
                
                if nueva_cantidad < 0:
                    self.mostrar_error("La cantidad no puede ser negativa")
                    return
                
                diferencia = nueva_cantidad - producto['stock_actual']
                
                # Actualizar stock
                exito = self.db.actualizar_stock(
                    producto['id'],
                    abs(diferencia),
                    "ajuste",
                    None,
                    observaciones_field.value or "Ajuste manual de stock"
                )
                
                if exito:
                    self.mostrar_exito(f"Stock actualizado: {producto['stock_actual']} → {nueva_cantidad}")
                    dialog.open = False
                    self.cargar_stock_bajo()
                    self.buscar_para_ajuste(None)
                else:
                    self.mostrar_error("Error al actualizar el stock")
                    
            except ValueError:
                self.mostrar_error("Ingrese una cantidad válida")
        
        dialog = ft.AlertDialog(
            title=ft.Text(f"Ajustar Stock - {producto['descripcion']}"),
            content=ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Text("Stock actual:", weight=ft.FontWeight.BOLD),
                        ft.Text(str(producto['stock_actual']), size=18, color=ft.Colors.BLUE_700)
                    ]),
                    ft.Container(height=10),
                    cantidad_field,
                    ft.Container(height=10),
                    observaciones_field
                ], tight=True),
                width=450,
                height=250
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: self.cerrar_dialog(dialog)),
                ft.ElevatedButton(
                    "GUARDAR",
                    icon=ft.Icons.SAVE,
                    on_click=guardar_ajuste,
                    style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN_700, color=ft.Colors.WHITE)
                )
            ]
        )
        
        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()
    
    def cerrar_dialog(self, dialog):
        dialog.open = False
        self.page.update()
    
    def cargar_movimientos(self):
        """Carga el historial de movimientos (implementación básica)"""
        # Esta función se puede expandir para mostrar movimientos de stock
        self.movimientos_list.controls.clear()
        self.movimientos_list.controls.append(
            ft.Text("Historial de movimientos - Funcionalidad en desarrollo", 
                   italic=True, text_align=ft.TextAlign.CENTER)
        )
        self.page.update()
    
    def mostrar_error(self, mensaje):
        snack = ft.SnackBar(
            content=ft.Text(mensaje, color=ft.Colors.WHITE),
            bgcolor=ft.Colors.RED_700
        )
        self.page.overlay.append(snack)
        snack.open = True
        self.page.update()
    
    def mostrar_exito(self, mensaje):
        snack = ft.SnackBar(
            content=ft.Text(mensaje, color=ft.Colors.WHITE),
            bgcolor=ft.Colors.GREEN_700
        )
        self.page.overlay.append(snack)
        snack.open = True
        self.page.update()
    
    def did_mount(self):
        """Se ejecuta cuando el componente se monta"""
        self.cargar_stock_bajo()
        self.cargar_movimientos()
import flet as ft
import pandas as pd
from datetime import datetime

def GestionArticulosView(db_manager, on_volver, page):
    """Vista de gestión de artículos"""
    
    # DataTable
    productos_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Código")),
            ft.DataColumn(ft.Text("Descripción")),
            ft.DataColumn(ft.Text("Marca")),
            ft.DataColumn(ft.Text("Precio")),
            ft.DataColumn(ft.Text("Stock")),
            ft.DataColumn(ft.Text("Acciones"))
        ],
        rows=[],
        column_spacing=20
    )
    
    # Buscador
    search_field = ft.TextField(
        label="BUSCAR",
        prefix_icon=ft.Icons.SEARCH,
        width=350,
        hint_text="Busque por código, descripción o categoría..."
    )
    
    filtro_dropdown = ft.Dropdown(
        width=150,
        value="descripcion",
        options=[
            ft.dropdown.Option("descripcion", "Descripción"),
            ft.dropdown.Option("categoria", "Categoría"),
            ft.dropdown.Option("codigo", "Código")
        ]
    )
    
    def cargar_productos(productos=None):
        """Carga productos en la tabla"""
        if productos is None:
            productos = db_manager.buscar_productos("", "descripcion")
        
        productos_table.rows.clear()
        
        for producto in productos:
            stock_color = ft.Colors.GREEN_700 if producto['stock_actual'] > producto['stock_minimo'] else ft.Colors.RED_700
            
            def crear_handler_editar(p):
                return lambda e: editar_producto(p)
            
            row = ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text(producto['codigo'], size=12)),
                    ft.DataCell(ft.Text(producto['descripcion'], size=12)),
                    ft.DataCell(ft.Text(producto.get('marca', '') or '', size=12)),
                    ft.DataCell(ft.Text(f"${producto['precio_lista']:.2f}", size=12)),
                    ft.DataCell(ft.Text(str(producto['stock_actual']), color=stock_color, size=12)),
                    ft.DataCell(
                        ft.IconButton(
                            icon=ft.Icons.EDIT,
                            icon_color=ft.Colors.BLUE_400,
                            tooltip="Editar",
                            on_click=crear_handler_editar(producto)
                        )
                    )
                ],
                on_select_changed=crear_handler_editar(producto)
            )
            productos_table.rows.append(row)
        
        page.update()
    
    def buscar_productos(e):
        """Busca productos - búsqueda predictiva"""
        termino = search_field.value
        campo = filtro_dropdown.value
        productos = db_manager.buscar_productos(termino, campo)
        cargar_productos(productos)
    
    def nuevo_producto(e):
        """Abre modal para crear nuevo producto"""
        from componente_producto import ProductoModal
        modal = ProductoModal(
            db_manager=db_manager,
            producto=None,
            on_guardado=lambda: cargar_productos(),
            page=page
        )
        page.overlay.append(modal)
        page.update()
    
    def editar_producto(producto):
        """Abre modal para editar producto"""
        from componente_producto import ProductoModal
        modal = ProductoModal(
            db_manager=db_manager,
            producto=producto,
            on_guardado=lambda: cargar_productos(),
            page=page
        )
        page.overlay.append(modal)
        page.update()
    
    def importar_excel(e):
        def on_file_selected(e: ft.FilePickerResultEvent):
            if e.files:
                try:
                    file_path = e.files[0].path
                    df = pd.read_excel(file_path)
                    
                    # Obtener columnas del Excel
                    columnas = df.columns.tolist()
                    
                    df = df.fillna({
                        col: 0 if col.lower() in ['precio_lista', 'precio_costo', 'stock_inicial', 'stock_minimo'] else ''
                        for col in columnas
                    })
                    
                    importados = 0
                    for _, row in df.iterrows():
                        try:
                            producto = {}
                            for col in columnas:
                                if col.lower() in ['precio_lista', 'precio_costo']:
                                    producto[col] = float(row[col])
                                elif col.lower() in ['stock_inicial', 'stock_minimo']:
                                    producto[col] = int(row[col])
                                else:
                                    producto[col] = str(row[col]).strip()
                            
                            if not producto.get('codigo'):
                                continue
                            
                            db_manager.guardar_producto(producto)
                            importados += 1
                        except Exception as ex:
                            print(f"Error en fila: {ex}")
                            continue
                    
                    mostrar_exito(f"Se importaron {importados} productos")
                    cargar_productos()
                except Exception as ex:
                    mostrar_error(f"Error al importar: {str(ex)}")
        
        file_picker = ft.FilePicker(on_result=on_file_selected)
        page.overlay.append(file_picker)
        page.update()
        file_picker.pick_files(
            allowed_extensions=["xlsx", "xls"],
            dialog_title="Seleccionar archivo Excel"
        )
        
    def descargar_excel(e):
        """Descarga productos a Excel"""
        try:
            productos = db_manager.buscar_productos("", "descripcion")
            if not productos:
                mostrar_error("No hay productos para exportar")
                return
            
            df = pd.DataFrame(productos)
            columnas = ['codigo', 'descripcion', 'categoria', 'marca', 
                       'precio_lista', 'precio_costo', 'stock_actual', 'stock_minimo']
            df = df[columnas]
            
            filename = f"productos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            df.to_excel(filename, index=False)
            
            mostrar_exito(f"Archivo guardado: {filename}")
        except Exception as ex:
            mostrar_error(f"Error al exportar: {str(ex)}")
    
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
    
    # Configurar eventos
    search_field.on_change = buscar_productos
    
    # Cargar productos iniciales
    cargar_productos()
    
    # Layout
    return ft.Container(
        content=ft.Column([
            ft.Container(
                content=ft.Text("GESTIÓN DE ARTÍCULOS", size=20, weight=ft.FontWeight.BOLD),
                bgcolor=ft.Colors.BLUE_900,
                padding=6,
                alignment=ft.alignment.center
            ),
            ft.Container(height=15),
            ft.Row([
                search_field,
                filtro_dropdown,
                ft.ElevatedButton(
                    "NUEVO PRODUCTO",
                    icon=ft.Icons.ADD_CIRCLE,
                    on_click=nuevo_producto,
                    style=ft.ButtonStyle(
                        bgcolor=ft.Colors.GREEN_700,
                        color=ft.Colors.WHITE
                    ),
                    height=45
                )
            ], alignment=ft.MainAxisAlignment.CENTER, spacing=10),
            ft.Container(height=10),
            ft.Container(
                content=ft.Row(
                    [productos_table],
                    alignment=ft.MainAxisAlignment.CENTER  # 🔹 Centra la tabla horizontalmente
                ),
                height=400,
                border=ft.border.all(1, ft.Colors.BLUE_GREY_700),
                border_radius=5,
                padding=10,
                alignment=ft.alignment.center,  # 🔹 Centra también verticalmente
            ),

            ft.Container(height=15),
            ft.Row([
                ft.ElevatedButton(
                    "IMPORTAR EXCEL",
                    icon=ft.Icons.UPLOAD_FILE,
                    on_click=importar_excel,
                    style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE)
                ),
                ft.ElevatedButton(
                    "EXPORTAR EXCEL",
                    icon=ft.Icons.DOWNLOAD,
                    on_click=descargar_excel
                ),
                ft.ElevatedButton(
                    "VOLVER",
                    icon=ft.Icons.ARROW_BACK,
                    on_click=lambda e: on_volver()
                )
            ], alignment=ft.MainAxisAlignment.CENTER, spacing=10)
        ], scroll=ft.ScrollMode.AUTO, expand=True),
        padding=20,
        expand=True
    )
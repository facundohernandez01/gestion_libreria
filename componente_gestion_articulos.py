import flet as ft
import pandas as pd
from datetime import datetime

class GestionArticulosView(ft.Column):
    def __init__(self, db_manager, on_volver):
        super().__init__()
        self.db = db_manager
        self.on_volver = on_volver

        # Inicializar el DataTable como atributo para que exista antes de did_mount()
        self.productos_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Código")),
                ft.DataColumn(ft.Text("Descripción")),
                ft.DataColumn(ft.Text("Precio")),
                ft.DataColumn(ft.Text("Stock"))
            ],
            rows=[]
        )

    def build(self):
        search = ft.TextField(label="Buscar producto", expand=True)
        dg = self.productos_table
        dg.width = 800

        return ft.Column([
            ft.Row([search, ft.ElevatedButton("Nuevo producto")]),
            dg,
            ft.Row([ft.ElevatedButton("Importar Excel"), ft.ElevatedButton("Exportar Excel"), ft.ElevatedButton("Volver", on_click=lambda e: self.on_volver())])
        ], scroll=True)
    
    def did_mount(self):
        """Se ejecuta cuando el componente se monta"""
        # Llamar a la carga de productos en montaje
        self.cargar_productos()

    def cargar_productos(self, productos=None):
        """Carga los productos en la tabla"""
        # Limpiar filas actuales
        try:
            self.productos_table.rows.clear()
        except Exception:
            # Si por alguna razón aún no existe, asegurar que es una lista vacía
            self.productos_table.rows = []

        # Obtener productos desde la DB (proteger si el método no existe)
        productos = []
        try:
            # se asume que DatabaseManager tiene un método obtener_productos o listar_productos
            if hasattr(self.db, "obtener_productos"):
                productos = self.db.obtener_productos()
            elif hasattr(self.db, "listar_productos"):
                productos = self.db.listar_productos()
            elif hasattr(self.db, "get_all_products"):
                productos = self.db.get_all_products()
            else:
                # fallback ejemplo si no hay DB conectada
                productos = [
                    {"codigo": "123", "descripcion": "Libro A", "precio": 120.0, "stock": 5},
                    {"codigo": "456", "descripcion": "Goma", "precio": 10.0, "stock": 20},
                ]
        except Exception:
            productos = []

        # Rellenar la tabla
        for p in productos:
            try:
                row = ft.DataRow(cells=[
                    ft.DataCell(ft.Text(str(p.get("codigo", "")))),
                    ft.DataCell(ft.Text(str(p.get("descripcion", "")))),
                    ft.DataCell(ft.Text(str(p.get("precio", "")))),
                    ft.DataCell(ft.Text(str(p.get("stock", ""))))
                ])
                self.productos_table.rows.append(row)
            except Exception:
                continue

        # Actualizar la vista
        try:
            self.update()
        except Exception:
            pass
    
    def buscar_productos(self, e):
        """Busca productos según el filtro"""
        termino = self.search_field.value
        campo = self.filtro_dropdown.value
        
        productos = self.db.buscar_productos(termino, campo)
        self.cargar_productos(productos)
    
    def nuevo_producto(self, e):
        """Abre el modal para crear un nuevo producto"""
        from componente_producto import ProductoModal
        modal = ProductoModal(
            self.db,
            producto=None,
            on_guardado=self.on_producto_guardado
        )
        self.page.overlay.append(modal)
        modal.open = True
        self.page.update()
    
    def editar_producto(self, producto):
        """Abre el modal para editar un producto existente"""
        from componente_producto import ProductoModal
        modal = ProductoModal(
            self.db,
            producto=producto,
            on_guardado=self.on_producto_guardado
        )
        self.page.overlay.append(modal)
        modal.open = True
        self.page.update()
    
    def on_producto_guardado(self):
        """Callback cuando se guarda un producto"""
        self.cargar_productos()
    
    def importar_excel(self, e):
        """Importa productos desde un archivo Excel"""
        def on_file_selected(e: ft.FilePickerResultEvent):
            if e.files:
                try:
                    file_path = e.files[0].path
                    df = pd.read_excel(file_path)

                    # Validar columnas requeridas
                    columnas_requeridas = ['codigo', 'descripcion', 'precio_lista']
                    if not all(col in df.columns for col in columnas_requeridas):
                        self.mostrar_error("El archivo debe contener las columnas: codigo, descripcion, precio_lista")
                        return

                    # Rellenar valores NaN para evitar errores
                    df = df.fillna({
                        'codigo': '',
                        'descripcion': '',
                        'categoria': '',
                        'marca': '',
                        'precio_lista': 0,
                        'precio_costo': 0,
                        'stock_inicial': 0,
                        'stock_minimo': 5
                    })

                    importados = 0
                    fallidos = 0

                    for _, row in df.iterrows():
                        try:
                            if not str(row['codigo']).strip() or not str(row['descripcion']).strip():
                                continue  # omitir filas vacías

                            producto = {
                                'codigo': str(row['codigo']).strip(),
                                'descripcion': str(row['descripcion']).strip(),
                                'categoria': str(row.get('categoria', '')).strip(),
                                'marca': str(row.get('marca', '')).strip(),
                                'precio_lista': float(row['precio_lista']) if row['precio_lista'] else 0.0,
                                'precio_costo': float(row.get('precio_costo', 0)) if not pd.isna(row.get('precio_costo', 0)) else 0.0,
                                'stock_inicial': int(row.get('stock_inicial', 0)) if not pd.isna(row.get('stock_inicial', 0)) else 0,
                                'stock_minimo': int(row.get('stock_minimo', 5)) if not pd.isna(row.get('stock_minimo', 5)) else 5
                            }

                            # Guardar o actualizar producto
                            self.db.guardar_producto(producto)
                            importados += 1

                        except Exception as ex:
                            print(f"Error importando fila {row.to_dict()}: {ex}")
                            fallidos += 1
                            continue

                    mensaje = f"Se importaron {importados} productos exitosamente"
                    if fallidos > 0:
                        mensaje += f" ({fallidos} filas con error)"
                    self.mostrar_exito(mensaje)

                    self.cargar_productos()

                except Exception as ex:
                    self.mostrar_error(f"Error al importar: {str(ex)}")

        file_picker = ft.FilePicker(on_result=on_file_selected)
        self.page.overlay.append(file_picker)
        self.page.update()
        file_picker.pick_files(
            allowed_extensions=["xlsx", "xls"],
            dialog_title="Seleccionar archivo Excel"
        )

    
    def descargar_excel(self, e):
        """Descarga los productos a un archivo Excel"""
        try:
            productos = self.db.buscar_productos("", "descripcion")
            
            if not productos:
                self.mostrar_error("No hay productos para exportar")
                return
            
            # Convertir a DataFrame
            df = pd.DataFrame(productos)
            
            # Seleccionar y ordenar columnas
            columnas = ['codigo', 'descripcion', 'categoria', 'marca', 
                       'precio_lista', 'precio_costo', 'stock_actual', 'stock_minimo']
            df = df[columnas]
            
            # Guardar archivo
            filename = f"productos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            df.to_excel(filename, index=False)
            
            self.mostrar_exito(f"Archivo guardado: {filename}")
            
        except Exception as ex:
            self.mostrar_error(f"Error al exportar: {str(ex)}")
    
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
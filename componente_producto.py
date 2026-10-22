import flet as ft
from ui.helpers import cerrar_dialogo, snack as _snack

def ProductoModal(db_manager, producto, on_guardado, page):
    """Modal para crear o editar producto"""
    
    es_nuevo = producto is None
    
    # Campos del formulario
    codigo_field = ft.TextField(
        label="CÓDIGO *",
        value=producto['codigo'] if producto else "",
        width=250
    )
    
    descripcion_field = ft.TextField(
        label="DESCRIPCIÓN *",
        value=producto['descripcion'] if producto else "",
        width=450
    )
    
    categoria_field = ft.TextField(
        label="CATEGORÍA",
        value=producto.get('categoria', '') if producto else "",
        width=250
    )
    
    marca_field = ft.TextField(
        label="MARCA",
        value=producto.get('marca', '') if producto else "",
        width=250
    )

    try:
        proveedores = db_manager.listar_proveedores("", 1000)
    except Exception:
        proveedores = []
    proveedor_field = ft.Dropdown(
        label="PROVEEDOR",
        width=300,
        value=str(producto.get("proveedor_id")) if producto and producto.get("proveedor_id") else None,
        options=[ft.dropdown.Option(str(p["id"]), p["nombre"]) for p in proveedores],
    )
    
    precio_lista_field = ft.TextField(
        label="PRECIO LISTA *",
        prefix=ft.Text("$"),
        value=str(producto['precio_lista']) if producto else "",
        keyboard_type=ft.KeyboardType.NUMBER,
        width=180
    )
    
    precio_costo_field = ft.TextField(
        label="PRECIO COSTO",
        prefix=ft.Text("$"),
        value=str(producto.get('precio_costo', 0)) if producto else "0",
        keyboard_type=ft.KeyboardType.NUMBER,
        width=180
    )
    
    stock_field = ft.TextField(
        label="STOCK ACTUAL" if not es_nuevo else "STOCK INICIAL",
        value=str(producto['stock_actual'] if producto else 0),
        keyboard_type=ft.KeyboardType.NUMBER,
        width=150
    )
    
    stock_minimo_field = ft.TextField(
        label="STOCK MÍNIMO",
        value=str(producto.get('stock_minimo', 5) if producto else 5),
        keyboard_type=ft.KeyboardType.NUMBER,
        width=150
    )
    
    # Texto de margen
    margen_text = ft.Text("", size=13)
    
    def calcular_margen(e=None):
        """Calcula y muestra el margen"""
        try:
            costo = float(precio_costo_field.value or 0)
            lista = float(precio_lista_field.value or 0)
            
            if costo > 0 and lista > 0:
                margen = ((lista - costo) / costo) * 100
                ganancia = lista - costo
                
                color = ft.Colors.GREEN_700 if margen > 30 else ft.Colors.ORANGE_700 if margen > 15 else ft.Colors.RED_700
                margen_text.value = f"Margen: {margen:.1f}% | Ganancia: ${ganancia:.2f}"
                margen_text.color = color
            else:
                margen_text.value = "Ingrese precios para calcular margen"
                margen_text.color = ft.Colors.GREY_500
            
            page.update()
        except:
            margen_text.value = ""
            page.update()
    
    # Eventos para calcular margen
    precio_lista_field.on_change = calcular_margen
    precio_costo_field.on_change = calcular_margen
    
    # Calcular margen inicial si es edición
    if producto:
        calcular_margen()
    
    def guardar(e):
        """Guarda el producto"""
        try:
            # Validaciones
            if not codigo_field.value or not descripcion_field.value or not precio_lista_field.value:
                mostrar_error("Complete los campos obligatorios (*)")
                return
            
            # Preparar datos
            datos_producto = {
                'codigo': codigo_field.value.strip(),
                'descripcion': descripcion_field.value.strip(),
                'categoria': categoria_field.value.strip() or "",
                'marca': marca_field.value.strip() or "",
                'precio_lista': float(precio_lista_field.value),
                'precio_costo': float(precio_costo_field.value or 0),
                'stock_minimo': int(stock_minimo_field.value or 5),
                'proveedor_id': int(proveedor_field.value) if proveedor_field.value else None,
            }
            
            if es_nuevo:
                datos_producto['stock_inicial'] = int(stock_field.value or 0)
            else:
                datos_producto['id'] = producto['id']
                datos_producto['stock_actual'] = int(stock_field.value or 0)
            
            # Guardar
            producto_id = db_manager.guardar_producto(datos_producto)
            
            if producto_id:
                # Cerrar primero: snack() abre un diálogo y si se cierra
                # después se popea el SnackBar y el modal queda abierto.
                cerrar_modal()
                on_guardado()
                mostrar_exito("Producto guardado exitosamente")
            else:
                mostrar_error("Error al guardar el producto")
                
        except ValueError:
            mostrar_error("Verifique que los valores numéricos sean correctos")
        except Exception as ex:
            mostrar_error(f"Error: {str(ex)}")
    
    def cancelar(e):
        """Cancela y cierra el modal"""
        cerrar_modal()
    
    def cerrar_modal():
        """Cierra el modal (explícito: pop_dialog falla si hay un SnackBar)."""
        try:
            dialog.open = False
            page.update()
        except Exception:
            cerrar_dialogo(page)

    def mostrar_error(mensaje):
        _snack(page, mensaje, ok=False)

    def mostrar_exito(mensaje):
        _snack(page, mensaje, ok=True)
    
    # Contenido del modal
    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Row([
            ft.Icon(ft.Icons.INVENTORY_2 if es_nuevo else ft.Icons.EDIT, color=ft.Colors.BLUE_700),
            ft.Text(
                "NUEVO PRODUCTO" if es_nuevo else f"EDITAR PRODUCTO (#{producto['id']})",
                size=20,
                weight=ft.FontWeight.BOLD
            )
        ]),
        content=ft.Container(
            content=ft.Column([
                ft.Text("Información básica", weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_400),
                ft.Row([codigo_field, categoria_field], spacing=10),
                descripcion_field,
                ft.Row([marca_field, proveedor_field], spacing=10, wrap=True),
                ft.Divider(),
                ft.Text("Precios", weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_400),
                ft.Row([precio_costo_field, precio_lista_field], spacing=10),
                ft.Container(
                    content=margen_text,
                    bgcolor=ft.Colors.BLUE_GREY_900,
                    padding=10,
                    border_radius=5
                ),
                ft.Divider(),
                ft.Text("Inventario", weight=ft.FontWeight.BOLD, color=ft.Colors.ORANGE_400),
                ft.Row([stock_field, stock_minimo_field], spacing=10),
                ft.Text("* Campos obligatorios", size=11, italic=True, color=ft.Colors.GREY_500)
            ], scroll=ft.ScrollMode.AUTO, spacing=10),
            width=500,
            height=480
        ),
        actions=[
            ft.TextButton("CANCELAR", on_click=cancelar),
            ft.FilledButton(
                "GUARDAR",
                icon=ft.Icons.SAVE,
                on_click=guardar,
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
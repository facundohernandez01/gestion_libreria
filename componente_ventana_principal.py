import webbrowser
from pathlib import Path

import flet as ft
from ui.paleta import N
from ui.theme import GRADIENTE_NEON, sombra_neon
from datetime import datetime
from mostrar_qr import mostrar_qr
from config import ConfigModal
from core.permisos import tiene
from ui.helpers import abrir_dialogo, cerrar_dialogo, snack
from utils.paths import base_dir
from utils.licencia import obtener_device_id

def VentanaPrincipal(page: ft.Page, db_manager, caja_id, on_nueva_venta_teclado, on_nueva_venta_lector, on_gestion_articulos, on_cerrar_caja, on_compras=None, on_historial_cajas=None, on_ingreso_stock=None, on_salir=None, permisos=None, es_admin=False, on_roles_usuarios=None, modo_cliente=False):
    """Ventana principal con lista de ventas y acciones"""
    permisos = permisos or {}

    def puede(clave):
        return tiene(permisos, clave, es_admin)

    def abrir_qr(e):
        dlg = ft.AlertDialog(
            modal=True,
            content=mostrar_qr(page),
            actions=[
                ft.TextButton("Cerrar", on_click=lambda e: cerrar_dialogo(page))
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        abrir_dialogo(page, dlg)

    def abrir_config(e):
        dlg = ConfigModal(page)
        abrir_dialogo(page, dlg)

    def abrir_reporte(e):
        from componente_reporte import mostrar_reporte_ventas
        mostrar_reporte_ventas(page, db_manager)

    def abrir_acerca(e=None):
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Acerca de"),
            content=ft.Container(
                content=ft.Column([
                    ft.Text("Kiosmico", size=18, weight=ft.FontWeight.BOLD,
                            color=N.BLUE_400),
                    ft.Text("Versión 1.1 - 10/2026", size=13),
                    ft.Text("Creado por: Facundo Hernandez", size=13),
                    ft.Text("facundohernandez.dev/kiosmico", size=12,
                            color=N.BLUE_300, selectable=True),
                ], spacing=6, tight=True),
                width=300,
            ),
            actions=[ft.TextButton("Cerrar",
                                   on_click=lambda _e: cerrar_dialogo(page))],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        abrir_dialogo(page, dlg)

    def abrir_reportar_problema(e=None):
        desc_field = ft.TextField(
            label="Descripción del problema", multiline=True, min_lines=4,
            width=420)
        incluir = ft.Checkbox(label="Incluir info del sistema", value=True)

        def enviar(_e=None):
            texto = (desc_field.value or "").strip()
            if not texto:
                snack(page, "Describí el problema", ok=False)
                return
            info = ""
            if incluir.value:
                try:
                    info = (f"\n\n---\nVersión: 1.1\n"
                            f"Fecha: {datetime.now().isoformat()}\n"
                            f"Dispositivo: {obtener_device_id()}\n")
                except Exception:
                    info = ""
            reporte = texto + info
            try:
                log = base_dir() / "reportes_problemas.log"
                with open(log, "a", encoding="utf-8") as fh:
                    fh.write(f"[{datetime.now().isoformat()}]\n{reporte}\n"
                             f"{'=' * 40}\n")
            except Exception as ex:  # noqa: BLE001
                snack(page, f"No se pudo guardar el reporte: {ex}", ok=False)
                return
            try:
                webbrowser.open("https://facundohernandez.dev/kiosmico")
            except Exception:
                pass
            cerrar_dialogo(page)
            snack(page, "Reporte guardado correctamente", ok=True)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Reportar un problema"),
            content=ft.Container(
                content=ft.Column([desc_field, incluir], spacing=10, tight=True),
                width=440,
            ),
            actions=[
                ft.TextButton("Cancelar",
                              on_click=lambda _e: cerrar_dialogo(page)),
                ft.FilledButton("Enviar", icon=ft.Icons.SEND, on_click=enviar,
                                style=ft.ButtonStyle(bgcolor=N.BLUE_700,
                                                     color=ft.Colors.WHITE)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        abrir_dialogo(page, dlg)

    
    try:
        pendientes_compra = db_manager.contar_ordenes_pendientes()
    except Exception:
        try:
            pendientes_compra = (db_manager.contar_ordenes_compra("en_proceso")
                                 + db_manager.contar_ordenes_compra("parcial"))
        except Exception:
            pendientes_compra = 0

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
                    ft.Icon(ft.Icons.RECEIPT, color=N.BLUE_400, size=24),
                    ft.Column([
                        ft.Text(
                            f"Venta #{venta['id']:04d} - {venta['fecha'][11:16] if len(venta['fecha']) > 11 else 'N/A'}",
                            size=15,
                            weight=ft.FontWeight.BOLD,
                            color=ft.Colors.WHITE
                        ),
                        ft.Text(
                            (venta['fecha'][11:16] if len(venta['fecha']) > 11 else 'N/A')
                            + (f" · {venta.get('usuario')}" if venta.get('usuario') else ""),
                            size=11,
                            color=ft.Colors.with_opacity(0.5, ft.Colors.WHITE)
                        )
                    ], spacing=2, expand=True),
                    ft.Column([
                        ft.Text(
                            f"${venta['total']:.2f}",
                            size=18,
                            weight=ft.FontWeight.BOLD,
                            color=N.GREEN_400
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
                        ft.Icon(ft.Icons.CIRCLE, size=6, color=N.BLUE_400),
                        ft.Text(item['producto_nombre'], size=13, color=ft.Colors.WHITE, expand=True),
                        ft.Text(f"x{item['cantidad']}", size=13, color=ft.Colors.with_opacity(0.6, ft.Colors.WHITE), width=50),
                        ft.Text(f"${item['precio_unitario']:.2f}", size=13, color=ft.Colors.with_opacity(0.6, ft.Colors.WHITE), width=80),
                        ft.Text(f"${item['subtotal']:.2f}", size=13, 
                               text_align=ft.TextAlign.RIGHT, weight=ft.FontWeight.W_500,
                               color=N.GREEN_400, width=90)
                    ], spacing=8)
                    items_col.controls.append(item_row)
                
                items_container = ft.Container(
                    content=items_col,
                    bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.WHITE),
                    padding=12,
                    margin=ft.Margin.only(left=10, right=2, top=0, bottom=5),
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
                    alignment=ft.Alignment.CENTER,
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
        content=ft.Row([
            ft.Container(expand=True),
            ft.Row([
                ft.Icon(ft.Icons.CALENDAR_TODAY, size=20, color=ft.Colors.with_opacity(0.7, ft.Colors.WHITE)),
                ft.Text(f"{datetime.now().strftime('%d/%m/%Y')}", size=15,
                       color=ft.Colors.with_opacity(0.9, ft.Colors.WHITE)),
                ft.Container(width=40),
                ft.Icon(ft.Icons.POINT_OF_SALE, size=20, color=ft.Colors.with_opacity(0.7, ft.Colors.WHITE)),
                ft.Text(f"Caja #{caja_id:04d}" if caja_id else "Sin caja abierta",
                       size=20, weight=ft.FontWeight.BOLD,
                       color=ft.Colors.with_opacity(0.9, ft.Colors.WHITE)),
                ft.Container(width=20),
                ft.Icon(ft.Icons.PERSON, size=18,
                        color=ft.Colors.with_opacity(0.7, ft.Colors.WHITE)),
                ft.Text(f"{getattr(db_manager, 'usuario_actual', '') or '—'}",
                       size=13, color=ft.Colors.with_opacity(0.85, ft.Colors.WHITE)),
            ], alignment=ft.MainAxisAlignment.CENTER, spacing=8),
            ft.Container(expand=True),
            ft.TextButton("ACERCA DE", icon=ft.Icons.INFO_OUTLINE,
                          style=ft.ButtonStyle(color=ft.Colors.WHITE),
                          on_click=abrir_acerca),
            ft.TextButton("REPORTAR", icon=ft.Icons.BUG_REPORT,
                          style=ft.ButtonStyle(color=ft.Colors.WHITE),
                          on_click=abrir_reportar_problema),
            ft.TextButton(
                "SALIR", icon=ft.Icons.LOGOUT,
                style=ft.ButtonStyle(color=ft.Colors.WHITE),
                on_click=lambda _e: on_salir() if on_salir else None),
        ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
        gradient=GRADIENTE_NEON,
        shadow=sombra_neon(N.CYAN, 18, 0.3),
        padding=ft.Padding.symmetric(horizontal=8, vertical=1)
    )
    
    # Sección de ventas de hoy
    ventas_header = ft.Container(
        content=ft.Row([
            ft.Icon(ft.Icons.HISTORY, color=N.BLUE_400, size=28),
            ft.Text("VENTAS DE HOY", size=22, weight=ft.FontWeight.BOLD)
        ], spacing=1),
        padding=ft.Padding.only(left=1, bottom=1)
    )
    
    # Comandas: acceso independiente de la caja, protegido por permiso del rol.
    if puede("ENTREGAS_INTRASHOP"):
        from componente_entregas_intrashop import panel_entregas
        tablero_entregas = ft.Container(
            content=panel_entregas(page, getattr(db_manager, "usuario_actual", "") or "operador POS"),
            visible=False, expand=True, height=440,
        )
        def cambiar_pestana(entregas):
            ventas_container.visible = not entregas
            tablero_entregas.visible = entregas
            page.update()
        ventas_header.content.controls.append(
            ft.TextButton("Ventas de hoy", on_click=lambda e: cambiar_pestana(False)))
        ventas_header.content.controls.append(
            ft.TextButton("Comandas IntraShop", icon=ft.Icons.RECEIPT_LONG,
                          on_click=lambda e: cambiar_pestana(True)))
    else:
        tablero_entregas = ft.Container(visible=False)

    # Panel derecho con total y botones
    panel_derecho = ft.Container(
        content=ft.Column([
            # Botones de nueva venta
            ft.Container(
                content=ft.Column([
                    ft.FilledButton(
                        content=ft.Column([
                            ft.Icon(ft.Icons.KEYBOARD, size=40, color=ft.Colors.WHITE),
                            ft.Container(height=5),
                            ft.Text("Nueva venta", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                            ft.Text("(Teclado)", size=11, color=ft.Colors.with_opacity(0.8, ft.Colors.WHITE)),
                            ft.Text("Atajo: Alt+Q", size=10,
                                    color=ft.Colors.with_opacity(0.65, ft.Colors.WHITE))
                        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=2, tight=True),
                        width=180,
                        height=110,
                        style=ft.ButtonStyle(
                            bgcolor=N.GREEN_700,
                            shape=ft.RoundedRectangleBorder(radius=8),
                            elevation=4
                        ),
                        on_click=lambda e: on_nueva_venta_teclado()
                    ),
                    ft.FilledButton(
                        content=ft.Column([
                            ft.Icon(ft.Icons.QR_CODE_SCANNER, size=40, color=ft.Colors.WHITE),
                            ft.Container(height=5),
                            ft.Text("Nueva venta", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                            ft.Text("(Lector)", size=11, color=ft.Colors.with_opacity(0.8, ft.Colors.WHITE)),
                            ft.Text("Atajo: Alt+W", size=10,
                                    color=ft.Colors.with_opacity(0.65, ft.Colors.WHITE))
                        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=2, tight=True),
                        width=180,
                        height=110,
                        style=ft.ButtonStyle(
                            bgcolor=N.BLUE_700,
                            shape=ft.RoundedRectangleBorder(radius=8),
                            elevation=4
                        ),
                        on_click=lambda e: on_nueva_venta_lector()
                    ),
                    ft.FilledButton(
                        content=ft.Row([
                            ft.Icon(ft.Icons.QR_CODE_2, size=20, color=ft.Colors.WHITE),
                            ft.Text("MOSTRAR QR", size=13, color=ft.Colors.WHITE)
                        ], alignment=ft.MainAxisAlignment.CENTER, spacing=8),
                        width=180,
                        height=110,
                        style=ft.ButtonStyle(
                            bgcolor=N.GREEN,
                            shape=ft.RoundedRectangleBorder(radius=8),
                            elevation=3
                        ),
                        on_click=abrir_qr
                ),
                ]),
                alignment=ft.Alignment.TOP_CENTER
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
                        color=N.GREEN_400,
                        text_align=ft.TextAlign.CENTER
                    )
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=5),
                bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.WHITE),
                padding=4,
                border_radius=8,
                width=180,
                height=110,
                border=ft.Border.all(2, N.GREEN_700)
            ),
            ft.Container(height=20),
            # Botones de acción
            
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        padding=10,
        expand=True,
    )
    
    # Botones de acción según permisos del rol
    botones_accion = []
    if puede("ARTICULOS"):
        botones_accion.append(ft.FilledButton(
            content=ft.Row([
                ft.Icon(ft.Icons.INVENTORY_2, size=20),
                ft.Text("GESTIÓN ARTÍCULOS", size=13)
            ], alignment=ft.MainAxisAlignment.CENTER, spacing=8),
            width=200, height=45,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
            on_click=lambda e: on_gestion_articulos()))
    if puede("COMPRAS"):
        botones_accion.append(ft.FilledButton(
            content=ft.Row([
                ft.Icon(ft.Icons.SHOPPING_CART, size=20, color=ft.Colors.WHITE),
                ft.Text(f"COMPRAS ({pendientes_compra})" if pendientes_compra
                        else "COMPRAS", size=13, color=ft.Colors.WHITE)
            ], alignment=ft.MainAxisAlignment.CENTER, spacing=8),
            width=200, height=45,
            style=ft.ButtonStyle(bgcolor=N.ORANGE_800,
                                 shape=ft.RoundedRectangleBorder(radius=8),
                                 elevation=3),
            on_click=lambda e: on_compras() if on_compras else None))
    if puede("CAJA"):
        botones_accion.append(ft.FilledButton(
            content=ft.Row([
                ft.Icon(ft.Icons.LOCK, size=20, color=ft.Colors.WHITE),
                ft.Text("CERRAR CAJA", size=13, color=ft.Colors.WHITE)
            ], alignment=ft.MainAxisAlignment.CENTER, spacing=8),
            width=200, height=45,
            style=ft.ButtonStyle(bgcolor=N.RED_700,
                                 shape=ft.RoundedRectangleBorder(radius=8),
                                 elevation=3),
            on_click=lambda e: on_cerrar_caja()))
    if puede("REPORTES"):
        botones_accion.append(ft.FilledButton(
            content=ft.Row([
                ft.Icon(ft.Icons.ASSESSMENT, size=20, color=ft.Colors.WHITE),
                ft.Text("REPORTES", size=13, color=ft.Colors.WHITE)
            ], alignment=ft.MainAxisAlignment.CENTER, spacing=8),
            width=200, height=45,
            style=ft.ButtonStyle(bgcolor=N.TEAL_700,
                                 shape=ft.RoundedRectangleBorder(radius=8),
                                 elevation=3),
            on_click=abrir_reporte))
    if puede("HISTORIAL_CAJAS"):
        botones_accion.append(ft.FilledButton(
            content=ft.Row([
                ft.Icon(ft.Icons.ACCOUNT_BALANCE_WALLET, size=20, color=ft.Colors.WHITE),
                ft.Text("HISTORIAL DE CAJAS", size=13, color=ft.Colors.WHITE)
            ], alignment=ft.MainAxisAlignment.CENTER, spacing=8),
            width=200, height=45,
            style=ft.ButtonStyle(bgcolor=N.INDIGO_800,
                                 shape=ft.RoundedRectangleBorder(radius=8),
                                 elevation=3),
            on_click=lambda e: on_historial_cajas() if on_historial_cajas else None))
    if puede("STOCK"):
        botones_accion.append(ft.FilledButton(
            content=ft.Row([
                ft.Icon(ft.Icons.ADD_BOX, size=20, color=ft.Colors.WHITE),
                ft.Text("INGRESO STOCK", size=13, color=ft.Colors.WHITE)
            ], alignment=ft.MainAxisAlignment.CENTER, spacing=8),
            width=200, height=45,
            style=ft.ButtonStyle(bgcolor=N.CYAN_800,
                                 shape=ft.RoundedRectangleBorder(radius=8),
                                 elevation=3),
            on_click=lambda e: on_ingreso_stock() if on_ingreso_stock else None))
    if es_admin and not modo_cliente and on_roles_usuarios:
        botones_accion.append(ft.FilledButton(
            content=ft.Row([
                ft.Icon(ft.Icons.MANAGE_ACCOUNTS, size=20, color=ft.Colors.WHITE),
                ft.Text("ROLES Y USUARIOS", size=13, color=ft.Colors.WHITE)
            ], alignment=ft.MainAxisAlignment.CENTER, spacing=8),
            width=200, height=45,
            style=ft.ButtonStyle(bgcolor=N.PURPLE_700,
                                 shape=ft.RoundedRectangleBorder(radius=8),
                                 elevation=3),
            on_click=lambda e: on_roles_usuarios()))
    if puede("CONFIGURACION") and not modo_cliente:
        botones_accion.append(ft.FilledButton(
            content=ft.Row([
                ft.Icon(ft.Icons.SETTINGS_APPLICATIONS, size=20, color=ft.Colors.WHITE),
                ft.Text("Ajustes", size=13, color=ft.Colors.WHITE)
            ], alignment=ft.MainAxisAlignment.CENTER, spacing=8),
            width=200, height=45,
            style=ft.ButtonStyle(bgcolor=N.BLACK,
                                 shape=ft.RoundedRectangleBorder(radius=8),
                                 elevation=3),
            on_click=abrir_config))

    # Layout principal
    contenido_principal = ft.Row([
        # Panel izquierdo - Ventas
        ft.Column([
            ventas_header,
            ventas_container,
            tablero_entregas,
            ft.Container(height=20),

            ft.Row(botones_accion,
            alignment=ft.MainAxisAlignment.START,
            spacing=15,
            wrap=True,
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
            alignment=ft.Alignment.CENTER
        )

        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, scroll=ft.ScrollMode.AUTO, expand=True),
        padding=20,
        expand=True
    )
    
    # Exponer la función como método del contenedor
    container_principal.cargar_ventas = cargar_ventas
    
    return container_principal
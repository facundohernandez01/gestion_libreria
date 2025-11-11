import flet as ft
from database_manager import DatabaseManager

class LibreriaApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.title = "Sistema de Gestión - Librería Kiosko"
        self.page.window.width = 700
        self.page.window.maximized = True
        self.page.theme_mode = ft.ThemeMode.SYSTEM
        self.page.on_keyboard_event = self.handle_key_event

        # Inicializar base de datos
        self.db = DatabaseManager()
        
        # Estado de la aplicación
        self.caja_actual = None
        self.vista_actual = None
        
        # Inicializar aplicación
        self.iniciar()
        
    def handle_key_event(self, e: ft.KeyboardEvent):
        """Atajos de teclado"""
        print(f"Tecla presionada: {e.key}, ctrl={e.ctrl}")

        if e.key == "F1":
            self.mostrar_nueva_venta("descripcion")

        elif e.ctrl and e.key.lower() == "n":
            self.mostrar_nueva_venta("codigo")

            
    def iniciar(self):
        """Determina la vista inicial según el estado de la caja"""
        caja_abierta = self.db.obtener_caja_abierta()
        
        if caja_abierta:
            self.caja_actual = caja_abierta['id']
            self.mostrar_ventana_principal()
        else:
            self.mostrar_abrir_caja()
    
    def mostrar_abrir_caja(self):
        """Muestra la ventana de apertura de caja"""
        from componente_abrir_caja import AbrirCajaView
        
        vista = AbrirCajaView(
            db_manager=self.db,
            on_caja_abierta=self.on_caja_abierta,
            page=self.page
        )
        
        self.page.controls.clear()
        self.page.add(vista)
        self.page.update()
    
    def on_caja_abierta(self, caja_id):
        """Callback cuando se abre una caja"""
        self.caja_actual = caja_id
        self.mostrar_ventana_principal()
    
    def mostrar_ventana_principal(self):
        """Muestra la ventana principal"""
        from componente_ventana_principal import VentanaPrincipal
        
        vista = VentanaPrincipal(
            page=self.page,
            db_manager=self.db,
            caja_id=self.caja_actual,
            on_nueva_venta_teclado=lambda: self.mostrar_nueva_venta("descripcion"),
            on_nueva_venta_lector=lambda: self.mostrar_nueva_venta("codigo"),
            on_gestion_articulos=self.mostrar_gestion_articulos,
            on_cerrar_caja=self.mostrar_cerrar_caja
        )
        self.vista_actual = vista  # 👈 guardamos la instancia actual
        self.page.controls.clear()
        self.page.add(vista)
        self.page.update()
    
    def mostrar_nueva_venta(self, filter_mode="descripcion"):
        """Abre modal de nueva venta"""
        from componente_nueva_venta import NuevaVentaView
        from componente_ventana_principal import VentanaPrincipal  # 👈 IMPORTA AQUÍ

        def cerrar_modal():
            """Cierra correctamente el modal y limpia overlay"""
            print("Cerrando modal correctamente...")
            try:
                if modal in self.page.overlay:
                    self.page.overlay.remove(modal)
                self.page.update()
            except Exception as err:
                print(f"Error al cerrar modal: {err}")

            from componente_ventana_principal import VentanaPrincipal
            if isinstance(self.vista_actual, ft.Container) and hasattr(self.vista_actual, "cargar_ventas"):
                print("✅ Refrescando lista de ventas en ventana principal...")
                try:
                    self.vista_actual.cargar_ventas()
                    print("✅ cargar_ventas() ejecutado correctamente")
                except Exception as err:
                    print(f"❌ Error al refrescar ventas: {err}")
            else:
                print("⚠️ No se encontró método cargar_ventas, recargando toda la vista principal...")
                self.mostrar_ventana_principal()


        modal = NuevaVentaView(
            db_manager=self.db,
            caja_id=self.caja_actual,
            on_confirmar=cerrar_modal,
            on_cerrar=cerrar_modal,
            filter_mode=filter_mode,
            page=self.page
        )

        self.page.overlay.clear()
        self.page.overlay.append(modal)
        self.page.update()
        print("Modal agregado al overlay correctamente")

        
    def mostrar_gestion_articulos(self):
        """Muestra la ventana de gestión de artículos"""
        from componente_gestion_articulos import GestionArticulosView
        
        vista = GestionArticulosView(
            db_manager=self.db,
            on_volver=self.mostrar_ventana_principal,
            page=self.page
        )
        
        self.page.controls.clear()
        self.page.add(vista)
        self.page.update()
    
    def mostrar_cerrar_caja(self):
        """Muestra el modal de cierre de caja"""
        from componente_cerrar_caja import CerrarCajaModal
        
        def on_cerrar(dialog=None):
            if dialog:
                dialog.open = False
            self.page.update()
            self.caja_actual = None
            self.mostrar_abrir_caja()
        
        modal = CerrarCajaModal(
            db_manager=self.db,
            caja_id=self.caja_actual,
            on_caja_cerrada=lambda: on_cerrar(modal),
            page=self.page
        )
        
        self.page.overlay.append(modal)
        self.page.update()

def main(page: ft.Page):
    app = LibreriaApp(page)

if __name__ == "__main__":
    ft.app(target=main)
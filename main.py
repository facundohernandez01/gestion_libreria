import flet as ft
from database_manager import DatabaseManager

# Importar componentes
# from componente_abrir_caja import AbrirCajaView
# from componente_ventana_principal import VentanaPrincipal
# from componente_gestion_articulos import GestionArticulosView
# from componente_cerrar_caja import CerrarCajaModal

class LibreriaApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.title = "Sistema de Gestión - Librería Kiosko"
        self.page.window_width = 1200
        self.page.window_height = 800
        # Permitir que la app use fullscreen y sea responsive
        self.page.window_maximized = True
        self.page.vertical_alignment = ft.MainAxisAlignment.START
        self.page.theme_mode = ft.ThemeMode.DARK
        
        # Inicializar base de datos
        self.db = DatabaseManager()
        
        # Estado de la aplicación
        self.caja_actual = None
        self.vista_actual = None
        
        # Inicializar aplicación
        self.iniciar()
    def mostrar_nueva_venta(self, filter_mode: str = None):
        """Muestra la ventana modal para registrar una nueva venta.
        filter_mode puede ser 'codigo' o 'descripcion' (o None)."""
        from componente_nueva_venta import NuevaVentaView

        modal = NuevaVentaView(
            db_manager=self.db,
            caja_id=self.caja_actual,
            on_confirmar=self.mostrar_ventana_principal,  # callback simple
            filter_mode=filter_mode
        )

        # Abrir modal sobre la ventana principal sin reemplazarla
        # usamos overlay para que la ventana principal permanezca visible detrás
        self.page.overlay.append(modal)
        modal.open = True
        self.page.update()
        
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
        
        self.vista_actual = AbrirCajaView(
            db_manager=self.db,
            on_caja_abierta=self.on_caja_abierta
        )
        
        self.page.clean()
        self.page.add(self.vista_actual)
        self.page.update()
    
    def on_caja_abierta(self, caja_id):
        """Callback cuando se abre una caja"""
        self.caja_actual = caja_id
        self.mostrar_ventana_principal()
    
    def mostrar_ventana_principal(self):
        from componente_ventana_principal import VentanaPrincipal

        # Pasamos callbacks para que la VentanaPrincipal abra la modal sin cerrarse
        self.vista_actual = VentanaPrincipal(
            page=self.page,
            caja_actual={"id": self.caja_actual},
            on_nueva_venta_teclado=lambda _: self.mostrar_nueva_venta(filter_mode="descripcion"),
            on_nueva_venta_lector=lambda _: self.mostrar_nueva_venta(filter_mode="codigo"),
            on_gestion_articulos=lambda _: self.mostrar_gestion_articulos(),
            on_cerrar_caja=lambda _: self.mostrar_cerrar_caja()
        )

        self.page.clean()
        self.page.add(self.vista_actual)
        self.page.update()

    
    def mostrar_gestion_articulos(self):
        """Muestra la ventana de gestión de artículos"""
        from componente_gestion_articulos import GestionArticulosView
        
        self.vista_actual = GestionArticulosView(
            db_manager=self.db,
            on_volver=self.mostrar_ventana_principal
        )
        
        self.page.clean()
        self.page.add(self.vista_actual)
        self.page.update()
    
    def mostrar_cerrar_caja(self):
        """Muestra el modal de cierre de caja"""
        from componente_cerrar_caja import CerrarCajaModal
        
        modal = CerrarCajaModal(
            db_manager=self.db,
            caja_id=self.caja_actual,
            on_caja_cerrada=self.on_caja_cerrada
        )
        
        self.page.overlay.append(modal)
        modal.open = True
        self.page.update()
    
    def on_caja_cerrada(self):
        """Callback cuando se cierra la caja"""
        self.caja_actual = None
        self.mostrar_abrir_caja()

def main(page: ft.Page):
    app = LibreriaApp(page)

if __name__ == "__main__":
    ft.app(target=main)
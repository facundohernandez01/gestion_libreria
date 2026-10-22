"""App principal Flet — navegación caja → principal → modales."""
import logging
import os
import sys
from pathlib import Path

# Trabajar siempre junto al ejecutable/script: imprescindible en modo servicio
# de Windows (SCM arranca con cwd = System32).
def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


os.chdir(_base_dir())

import flet as ft

from core.settings import settings
from core.db_factory import crear_acceso_datos
from ui.helpers import abrir_dialogo

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))


class LibreriaApp:
    def __init__(self, page: ft.Page, modo_web: str = "admin"):
        self.page = page
        self.modo_web = modo_web
        self.page.title = f"Sistema de Gestión — {settings.nombre_negocio}"
        self.page.window.maximized = True
        self.page.theme_mode = ft.ThemeMode.DARK

        # Acceso a datos: local (SQLite) o cliente (HTTP FastAPI)
        self.db, self.modo = crear_acceso_datos()
        self.caja_actual = None
        self.vista_actual = None
        self.autenticado = False
        self.usuario = {}
        self.permisos = {}
        self.es_admin = False

        # Atajos de teclado centralizados (ShortcutManager, como el build)
        from utils.shortcuts import ShortcutManager

        self.sm = ShortcutManager(page)
        self.sm.register("q", lambda: self.mostrar_nueva_venta("descripcion"))
        self.sm.register("w", lambda: self.mostrar_nueva_venta("codigo"))

        # Escape cierra el modal abierto (login, ajustes, venta, etc.)
        page.on_keyboard_event = self._on_keyboard

        self.iniciar()

    # ---------- teclado ----------
    def _on_keyboard(self, e):
        key = (getattr(e, "key", "") or "").lower()
        if key == "escape":
            try:
                dialogs = getattr(self.page, "_dialogs", None)
                if dialogs is not None and any(getattr(d, "open", False) for d in dialogs.controls):
                    self.page.pop_dialog()
                    self.page.update()
            except Exception:
                pass
            return
        try:
            self.sm._handle_keypress(e)
        except Exception:
            pass

    # ---------- permisos ----------
    def _puede(self, clave: str) -> bool:
        from core.permisos import tiene

        return tiene(self.permisos, clave, self.es_admin)

    def _denegar(self):
        from ui.helpers import snack

        snack(self.page, "No tenés permiso para esta sección", ok=False)

    # ---------- navegación ----------
    def iniciar(self):
        try:
            primer_uso = bool(self.db.es_primer_uso())
        except AttributeError:
            primer_uso = False
        if primer_uso:
            self.mostrar_primer_uso()
            return
        if not self.autenticado:
            self.mostrar_login()
            return
        if self.modo_web == "stock":
            self.mostrar_ingreso_stock()
            return
        caja = self.db.obtener_caja_abierta()
        if caja:
            self.caja_actual = caja["id"]
            self.mostrar_ventana_principal()
        elif self._puede("CAJA"):
            self.mostrar_abrir_caja()
        else:
            self.caja_actual = 0
            self.mostrar_ventana_principal()

    def _set_vista(self, vista):
        self.vista_actual = vista
        self.page.controls.clear()
        self.page.add(vista)
        self.page.update()

    def mostrar_primer_uso(self):
        from componente_primer_uso import PrimerUsoView
        self._set_vista(PrimerUsoView(db_manager=self.db,
                                      on_finish=self.iniciar, page=self.page))

    def mostrar_login(self):
        from componente_login import LoginView
        self._set_vista(LoginView(db_manager=self.db, on_login=self.on_login,
                                  page=self.page))

    def on_login(self, usuario=None):
        from core.permisos import permisos_todos

        if isinstance(usuario, dict):
            self.usuario = usuario
        else:
            self.usuario = {"usuario": "admin", "rol": "ADMIN",
                            "es_admin": True, "permisos": permisos_todos()}
        self.es_admin = bool(self.usuario.get("es_admin"))
        self.permisos = self.usuario.get("permisos") or {}
        try:
            self.db.set_usuario_actual(self.usuario.get("usuario") or "")
        except Exception:
            pass
        self.autenticado = True
        self.iniciar()

    def cerrar_sesion(self):
        self.autenticado = False
        self.caja_actual = None
        self.usuario = {}
        self.permisos = {}
        self.es_admin = False
        try:
            self.db.set_usuario_actual("")
        except Exception:
            pass
        self.mostrar_login()

    def mostrar_abrir_caja(self):
        if not self._puede("CAJA"):
            self._denegar()
            return
        from componente_abrir_caja import AbrirCajaView
        self._set_vista(AbrirCajaView(db_manager=self.db, on_caja_abierta=self.on_caja_abierta, page=self.page))

    def on_caja_abierta(self, caja_id):
        self.caja_actual = caja_id
        self.mostrar_ventana_principal()

    def mostrar_ventana_principal(self):
        from componente_ventana_principal import VentanaPrincipal
        self._set_vista(VentanaPrincipal(
            page=self.page, db_manager=self.db, caja_id=self.caja_actual,
            on_nueva_venta_teclado=lambda: self.mostrar_nueva_venta("descripcion"),
            on_nueva_venta_lector=lambda: self.mostrar_nueva_venta("codigo"),
            on_gestion_articulos=self.mostrar_gestion_articulos,
            on_cerrar_caja=self.mostrar_cerrar_caja,
            on_compras=self.mostrar_compras,
            on_historial_cajas=self.mostrar_historial_cajas,
            on_ingreso_stock=self.mostrar_ingreso_stock,
            on_salir=self.cerrar_sesion,
            permisos=self.permisos,
            es_admin=self.es_admin,
            on_roles_usuarios=self.mostrar_roles_usuarios,
            modo_cliente=self.modo_web in ("cliente", "stock"),
        ))

    def mostrar_nueva_venta(self, filter_mode="descripcion"):
        if not self._puede("VENTAS"):
            self._denegar()
            return
        # Evitar apilar otra venta si ya hay un diálogo abierto.
        try:
            dialogs = getattr(self.page, "_dialogs", None)
            if dialogs is not None and any(
                    isinstance(d, ft.AlertDialog) and getattr(d, "open", False)
                    for d in dialogs.controls):
                return
        except Exception:
            pass
        from componente_nueva_venta import NuevaVentaView, SeleccionMetodoPagoView

        def cerrar_y_refrescar():
            # refrescar lista si la vista lo soporta, si no recargar
            try:
                if hasattr(self.vista_actual, "cargar_ventas"):
                    self.vista_actual.cargar_ventas()
                else:
                    self.mostrar_ventana_principal()
            except Exception:
                self.mostrar_ventana_principal()

        def abrir_venta(metodo_pago):
            modal = NuevaVentaView(
                db_manager=self.db, caja_id=self.caja_actual,
                on_confirmar=cerrar_y_refrescar, on_cerrar=cerrar_y_refrescar,
                filter_mode=filter_mode, page=self.page, sm_manager=self.sm,
                metodo_pago=metodo_pago)
            abrir_dialogo(self.page, modal)

        selector = SeleccionMetodoPagoView(
            db_manager=self.db, page=self.page, on_metodo=abrir_venta,
            sm_manager=self.sm)
        abrir_dialogo(self.page, selector)

    def mostrar_compras(self):
        if not self._puede("COMPRAS"):
            self._denegar()
            return
        from componente_compras import ComprasView
        self._set_vista(ComprasView(db_manager=self.db,
                                    on_volver=self.mostrar_ventana_principal,
                                    page=self.page))

    def mostrar_historial_cajas(self):
        if not self._puede("HISTORIAL_CAJAS"):
            self._denegar()
            return
        from componente_historial_cajas import HistorialCajasView
        self._set_vista(HistorialCajasView(db_manager=self.db,
                                           on_volver=self.mostrar_ventana_principal,
                                           page=self.page))

    def mostrar_ingreso_stock(self):
        if not self._puede("STOCK"):
            self._denegar()
            return
        from componente_ingreso_stock import IngresoStockView
        volver = (self.cerrar_sesion if self.modo_web == "stock"
                  else self.mostrar_ventana_principal)
        self._set_vista(IngresoStockView(db_manager=self.db,
                                         on_volver=volver,
                                         page=self.page))

    def mostrar_roles_usuarios(self):
        if not self.es_admin:
            self._denegar()
            return
        from componente_roles import RolesUsuariosView
        self._set_vista(RolesUsuariosView(
            db_manager=self.db, on_volver=self.mostrar_ventana_principal,
            page=self.page, usuario_actual=self.usuario.get("usuario") or ""))

    def mostrar_gestion_articulos(self):
        if not self._puede("ARTICULOS"):
            self._denegar()
            return
        from componente_gestion_articulos import GestionArticulosView
        self._set_vista(GestionArticulosView(
            db_manager=self.db, on_volver=self.mostrar_ventana_principal,
            page=self.page, permisos=self.permisos, es_admin=self.es_admin))

    def mostrar_cerrar_caja(self):
        if not self._puede("CAJA"):
            self._denegar()
            return
        from componente_cerrar_caja import CerrarCajaModal

        def on_cerrada():
            self.caja_actual = None
            self.mostrar_abrir_caja()

        # CerrarCajaModal cierra solo; aquí primero cerramos el diálogo abierto
        modal = CerrarCajaModal(db_manager=self.db, caja_id=self.caja_actual,
                                on_caja_cerrada=on_cerrada, page=self.page)
        abrir_dialogo(self.page, modal)


def _modo_desde_ruta(route: str) -> str:
    partes = (route or "").split("?")[0].strip("/").lower().split("/")
    primera = partes[0] if partes else ""
    if primera == "cliente":
        return "cliente"
    if primera == "stock":
        return "stock"
    return "admin"


def main(page: ft.Page):
    LibreriaApp(page, modo_web=_modo_desde_ruta(getattr(page, "route", "")))


def _servir(stop_event=None):
    """Arranca el servidor FastAPI (bloqueante). Usado por el servicio Windows."""
    from server_manager import servir_bloqueante

    try:
        servir_bloqueante(
            host=settings.api_host,
            port=settings.api_port,
            stop_event=stop_event,
        )
    except Exception as ex:  # noqa: BLE001
        _log_servicio(ex)
        raise


def _run_windows_service():
    """Host del servicio Windows (SCM). No abre ninguna ventana."""
    from windows_service import run_service

    run_service(_servir)


def _log_servicio(exc: BaseException) -> None:
    try:
        import traceback

        from utils.paths import base_dir

        with open(base_dir() / "servicio.log", "a", encoding="utf-8") as fh:
            fh.write(traceback.format_exc() + "\n")
    except Exception:
        pass


def _cli_servicio(accion) -> None:
    try:
        accion()
    except Exception as ex:  # noqa: BLE001
        _log_servicio(ex)
        raise


if __name__ == "__main__":
    if "--service" in sys.argv:
        try:
            _run_windows_service()
        except Exception as ex:  # noqa: BLE001
            _log_servicio(ex)
            raise
    elif "--server" in sys.argv:
        _servir()
    elif "--web" in sys.argv:
        ft.run(main, view=ft.AppView.WEB_BROWSER,
               host=getattr(settings, "web_host", "0.0.0.0"),
               port=getattr(settings, "web_port", 8550))
    elif "--install-service" in sys.argv:
        from windows_service import instalar

        _cli_servicio(lambda: instalar(auto_start=True, iniciar_ahora=True))
    elif "--start-service" in sys.argv:
        from windows_service import iniciar

        _cli_servicio(iniciar)
    elif "--stop-service" in sys.argv:
        from windows_service import detener

        _cli_servicio(detener)
    elif "--uninstall-service" in sys.argv:
        from windows_service import desinstalar

        _cli_servicio(desinstalar)
    else:
        ft.run(main)

"""Tema centralizado Kiosmico: paleta neón, estilos y helpers de brillo."""
from pathlib import Path

import flet as ft

from ui.paleta import N

VERDE = N.GREEN_700
VERDE_CLARO = N.GREEN_400
ROJO = N.RED_700
AZUL = N.BLUE_700
AZUL_OSCURO = N.BLUE_900
FONDO_CARD = ft.Colors.with_opacity(0.55, N.DEEP)

GRADIENTE_NEON = ft.LinearGradient(
    begin=ft.Alignment.CENTER_LEFT, end=ft.Alignment.CENTER_RIGHT,
    colors=[N.BLUE_700, N.VIOLET, N.PINK])
GRADIENTE_FONDO = ft.LinearGradient(
    begin=ft.Alignment.TOP_LEFT, end=ft.Alignment.BOTTOM_RIGHT,
    colors=[N.VOID, N.DEEP, "#160A3A"])


def sombra_neon(color=N.CYAN, blur=24, opacidad=0.35):
    """Resplandor suave de color alrededor de un contenedor."""
    return ft.BoxShadow(blur_radius=blur, spread_radius=0,
                        color=ft.Colors.with_opacity(opacidad, color))


def _estilo(bg, brillo):
    return ft.ButtonStyle(
        bgcolor=bg, color=ft.Colors.WHITE, elevation=6,
        shadow_color=ft.Colors.with_opacity(0.6, brillo),
        shape=ft.RoundedRectangleBorder(radius=12))


BTN_PRIMARIO = _estilo(N.BLUE_700, N.CYAN)
BTN_EXITO = _estilo(N.GREEN_700, N.MINT)
BTN_PELIGRO = _estilo(N.RED_700, N.PINK)
BTN_INFO = _estilo(N.BLUE_700, N.CYAN)

TITULO = {"size": 20, "weight": ft.FontWeight.BOLD}
SUBTITULO = {"size": 13, "color": N.GREY_400}
MONTO_GRANDE = {"size": 26, "weight": ft.FontWeight.BOLD, "color": N.GREEN_400}


def tema_kiosmico() -> ft.Theme:
    """Tema oscuro global: cian como color principal, violeta y rosa de apoyo."""
    return ft.Theme(color_scheme=ft.ColorScheme(
        primary=N.CYAN, on_primary=N.VOID, secondary=N.VIOLET,
        tertiary=N.PINK, error=N.RED_400, surface=N.DEEP,
        on_surface=N.TEXT, outline=N.BLUE_GREY_600))


def aplicar_tema(page: ft.Page) -> None:
    page.theme_mode = ft.ThemeMode.DARK
    page.theme = tema_kiosmico()
    page.dark_theme = tema_kiosmico()
    page.bgcolor = N.VOID


def logo_widget(size: int = 40):
    """Logo K con cohete si existe img/kiosmico_logo.png; si no, un ícono."""
    ruta = Path(__file__).resolve().parent.parent / "img" / "kiosmico_logo.png"
    if ruta.is_file():
        return ft.Image(src=str(ruta), width=size, height=size)
    return ft.Icon(ft.Icons.ROCKET_LAUNCH, size=size, color=N.CYAN)

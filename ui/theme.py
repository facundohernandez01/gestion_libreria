"""Tema centralizado (paleta + estilos). Mejora UI/UX: un solo lugar para colores."""
import flet as ft

VERDE = ft.Colors.GREEN_700
VERDE_CLARO = ft.Colors.GREEN_400
ROJO = ft.Colors.RED_700
AZUL = ft.Colors.BLUE_700
AZUL_OSCURO = ft.Colors.BLUE_900
FONDO_CARD = ft.Colors.with_opacity(0.08, ft.Colors.WHITE)

BTN_PRIMARIO = ft.ButtonStyle(bgcolor=VERDE, color=ft.Colors.WHITE,
                              shape=ft.RoundedRectangleBorder(radius=8))
BTN_PELIGRO = ft.ButtonStyle(bgcolor=ROJO, color=ft.Colors.WHITE,
                             shape=ft.RoundedRectangleBorder(radius=8))
BTN_INFO = ft.ButtonStyle(bgcolor=AZUL, color=ft.Colors.WHITE,
                          shape=ft.RoundedRectangleBorder(radius=8))

TITULO = {"size": 20, "weight": ft.FontWeight.BOLD}
SUBTITULO = {"size": 13, "color": ft.Colors.GREY_400}
MONTO_GRANDE = {"size": 26, "weight": ft.FontWeight.BOLD, "color": VERDE_CLARO}

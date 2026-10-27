"""Escaneo de códigos con una app externa (Binary Eye) desde la web /stock.

En la red local sin HTTPS el navegador no deja usar la cámara. Binary Eye
(Android, Play Store) se abre con un enlace, escanea con su propia cámara y al
terminar abre la URL de retorno ``http://<servidor>/stock?codigo=<lectura>``.
Esa visita entra directo a la pantalla de ingreso con el código ya cargado
(la sesión recordada evita volver a loguearse).
"""
from __future__ import annotations

import os
import socket
import sys
from urllib.parse import parse_qs, quote, urlparse

import flet as ft

PAQUETE = "de.markusfisch.android.binaryeye"
URL_PLAY = f"https://play.google.com/store/apps/details?id={PAQUETE}"


def _param(page: ft.Page, nombre: str) -> str | None:
    for fuente in (getattr(page, "route", None), getattr(page, "url", None)):
        try:
            valores = parse_qs(urlparse(str(fuente)).query).get(nombre)
            if valores and valores[0]:
                return valores[0]
        except Exception:
            pass
    try:
        valor = page.query.get(nombre)
        if valor:
            return str(valor)
    except Exception:
        pass
    return None


def _ip_local_hacia(destino: str) -> str:
    """IP de este equipo en la interfaz que llega a ``destino`` (sin enviar nada)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sk:
            sk.connect((destino, 9))
            return sk.getsockname()[0]
    except OSError:
        return ""


def _puerto_web(page: ft.Page) -> int:
    """Puerto con el que se sirve la web.

    La UI web va montada en la API (puerto ``api_port``, 8000 por defecto); solo
    si se lanza sola con ``--web`` se usa ``web_port``.
    """
    try:
        u = urlparse(str(getattr(page, "url", "") or ""))
        if u.scheme in ("http", "https") and u.port:
            return int(u.port)
    except ValueError:
        pass
    try:
        from core.settings import settings

        api = sys.modules.get("api_server")
        if api is not None and getattr(api, "_flet_web_montado", False):
            try:
                from server_manager import server_manager

                if getattr(server_manager, "activo", False):
                    return int(server_manager.port)
            except Exception:
                pass
            return int(settings.api_port)
        if os.getenv("FLET_SERVER_PORT"):
            return int(os.environ["FLET_SERVER_PORT"])
        if "--web" in sys.argv:
            return int(settings.web_port)
        return int(settings.api_port)
    except Exception:
        return 8000


def origen(page: ft.Page) -> str:
    """URL base (http://IP:puerto) con la que el celular llega al servidor.

    ``page.url`` en el servidor web de Flet suele venir vacío o como
    0.0.0.0/localhost. Se puede forzar con la variable URL_PUBLICA_WEB
    (por ejemplo http://192.168.1.50:8000).
    """
    forzada = os.getenv("URL_PUBLICA_WEB", "").strip().rstrip("/")
    if forzada.startswith(("http://", "https://")):
        return forzada
    u = urlparse(str(getattr(page, "url", "") or ""))
    if (u.scheme in ("http", "https") and u.hostname
            and u.hostname not in ("0.0.0.0", "127.0.0.1", "localhost", "::")):
        return f"{u.scheme}://{u.netloc}"
    ip = ""
    for destino in (str(getattr(page, "client_ip", "") or ""), "8.8.8.8"):
        if destino:
            ip = _ip_local_hacia(destino)
        if ip and not ip.startswith("127."):
            break
        ip = ""
    return f"http://{ip}:{_puerto_web(page)}" if ip else ""


def es_android(page: ft.Page) -> bool:
    return "android" in str(getattr(page, "client_user_agent", "") or "").lower()


def url_app_escaner(page: ft.Page, intent: bool = True) -> str:
    """Enlace que abre Binary Eye y le pide devolver el código a /stock.

    ``intent=True`` usa el formato ``intent://`` de Chrome, que abre la Play
    Store si la app no está instalada. ``intent=False`` es ``binaryeye://``.
    """
    ret = quote(f"{origen(page)}/stock?codigo=", safe="") + "{RESULT}"
    if intent:
        fallback = quote(URL_PLAY, safe="")
        return (f"intent://scan?ret={ret}#Intent;scheme=binaryeye;"
                f"package={PAQUETE};S.browser_fallback_url={fallback};end")
    return f"binaryeye://scan?ret={ret}"


def leer_retorno(page: ft.Page) -> str | None:
    """Código leído si la visita viene de Binary Eye (``/stock?codigo=...``)."""
    codigo = _param(page, "codigo")
    if not codigo:
        return None
    codigo = "".join(c for c in codigo.strip() if c.isprintable())[:64]
    return codigo or None

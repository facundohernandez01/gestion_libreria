"""Configuración de HTTPS LAN: Caddy en 443 -> Uvicorn solo loopback.

Con INTRASHOP_ENFORCE_HTTPS=1:
* El backend no escucha en ninguna interfaz de la LAN.
* Uvicorn acepta X-Forwarded-* únicamente desde Caddy en localhost.
* Todo acceso HTTP que el proxy no haya marcado como HTTPS se rechaza.
* El único URL publicado es POS_PUBLIC_URL=https://pos.home.arpa.

No confiar nunca en un proxy externo ni usar forwarded_allow_ips='*'.
"""
from __future__ import annotations

import os
from urllib.parse import urlsplit


def perfil_nativo():
    if os.getenv("POS_API_ONLY") != "1":
        return None
    from services.native_https import load
    return load()


def puerto_backend(port):
    return 443 if perfil_nativo() else port


def habilitado() -> bool:
    if perfil_nativo():
        return True
    return os.getenv("INTRASHOP_ENFORCE_HTTPS", "").strip().lower() in (
        "1", "true", "yes", "on",
    )


def url_publica() -> str | None:
    native = perfil_nativo()
    if native:
        return native["url"]
    if not habilitado():
        return None
    value = os.getenv("POS_PUBLIC_URL", "").strip().rstrip("/")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https" or not parsed.hostname
        or parsed.username or parsed.password
        or parsed.query or parsed.fragment or parsed.path not in ("", "/")
    ):
        raise RuntimeError(
            "Configurá POS_PUBLIC_URL=https://pos.home.arpa cuando "
            "INTRASHOP_ENFORCE_HTTPS=1. No incluyas rutas ni credenciales."
        )
    return value


def host_backend(host_solicitado: str) -> str:
    native = perfil_nativo()
    if native:
        return native["ip"]
    if not habilitado():
        return host_solicitado
    # Obliga a pasar por el terminador TLS local. No alcanza con un firewall.
    url_publica()  # validar config antes del primer socket de escucha
    return "127.0.0.1"


def opciones_uvicorn() -> dict:
    native = perfil_nativo()
    if native:
        return {"proxy_headers": False, "ssl_certfile": native["cert"], "ssl_keyfile": native["key"]}
    if habilitado():
        return {
            "proxy_headers": True,
            "forwarded_allow_ips": "127.0.0.1,::1",
        }
    return {"proxy_headers": False}


def url_visible(ip_lan: str, port: int) -> str:
    return url_publica() or f"http://{ip_lan}:{port}"

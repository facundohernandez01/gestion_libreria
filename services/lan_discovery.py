"""Detección opcional de equipos de la LAN local; nunca vincula tótems.

Ping ICMP (sin escaneo de puertos) y tabla ARP/vecinos, únicamente la /24
del servidor. No hay tráfico hacia Internet ni redes arbitrarias ingresadas
por el usuario. El administrador confirma IP y QR por separado.
"""
from __future__ import annotations

import concurrent.futures
import ipaddress
import json
import platform
import re
import socket
import subprocess
from typing import Callable

MAX_HOSTS = 254


def _subnet_servidor(ip_local: str) -> ipaddress.IPv4Network:
    address = ipaddress.IPv4Address(ip_local)
    if not address.is_private or address.is_loopback or address.is_link_local:
        raise ValueError("La IP del servidor debe pertenecer a una red privada LAN.")
    # En redes /16 o /8 se limita voluntariamente al segmento /24 local.
    return ipaddress.IPv4Network(f"{address}/24", strict=False)


def _arp_conocidos(red: ipaddress.IPv4Network) -> set[str]:
    conocidos: set[str] = set()
    # Linux: información pasiva del kernel (sin privilegios de root).
    try:
        proc = subprocess.run(
            ["ip", "-4", "neigh", "show"], capture_output=True, text=True,
            timeout=2, check=False,
        )
        if proc.returncode == 0:
            for line in proc.stdout.splitlines():
                words = line.split()
                if not words or "FAILED" in words or "INCOMPLETE" in words:
                    continue
                try:
                    addr = ipaddress.IPv4Address(words[0])
                    if addr in red:
                        conocidos.add(str(addr))
                except ipaddress.AddressValueError:
                    pass
    except (OSError, subprocess.TimeoutExpired):
        pass
    return conocidos


def _ping(ip: str) -> bool:
    if platform.system() == "Windows":
        cmd = ["ping", "-n", "1", "-w", "700", ip]
    else:
        cmd = ["ping", "-n", "-c", "1", "-W", "1", ip]
    try:
        result = subprocess.run(
            cmd, capture_output=True, timeout=2.5, check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def detectar_lan(ip_local: str, *, max_workers: int = 24,
                 callback: Callable[[int, int], None] | None = None) -> dict:
    """Detección manual y acotada. Solo direcciones LAN, no busca servicios.

    El resultado significa 'IP que responde' o 'vecino del servidor'; no
    demuestra que sea una PC, que sea confiable ni que ejecute IntraShop.
    """
    red = _subnet_servidor(ip_local)
    ips = [str(ip) for ip in red.hosts() if str(ip) != ip_local]
    if len(ips) > MAX_HOSTS:
        raise ValueError("El segmento tiene demasiadas direcciones.")
    conocidos = _arp_conocidos(red)
    encontrados: dict[str, str] = {ip: "Vecino conocido" for ip in conocidos}
    completed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(max_workers, 24)) as pool:
        futures = {pool.submit(_ping, ip): ip for ip in ips}
        for task in concurrent.futures.as_completed(futures):
            ip = futures[task]
            completed += 1
            if task.result():
                encontrados[ip] = "Responde a ping"
            if callback and (completed % 30 == 0 or completed == len(ips)):
                callback(completed, len(ips))
    return {
        "subred": str(red), "servidor": ip_local,
        "equipos": [
            {"ip": ip, "detalle": encontrados[ip]}
            for ip in sorted(encontrados, key=lambda v: ipaddress.IPv4Address(v))
            if ip != ip_local
        ],
        "alcance": "IPs detectadas; no prueba identidad ni titularidad del dispositivo",
    }

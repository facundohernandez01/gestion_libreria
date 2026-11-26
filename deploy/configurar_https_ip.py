#!/usr/bin/env python3
"""Asistente de HTTPS local por IP, sin DNS ni edición manual de .env.

Diseñado para Ubuntu/Kubuntu con Caddy como servicio. Se ejecuta como
usuario normal; solo instalación de paquetes/config Caddy usa sudo. Nunca
modifica libreria.db, secretos MP, claves de POS ni la CA privada.

Ejemplo: python3 deploy/configurar_https_ip.py
"""
from __future__ import annotations

import argparse
import ipaddress
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
from datetime import datetime


ROOT = Path(__file__).resolve().parents[1]
CADDYFILE = Path("/etc/caddy/Caddyfile")
CA_CERT = Path("/var/lib/caddy/.local/share/caddy/pki/authorities/local/root.crt")


def detectar_ip_lan() -> str:
    """Detectar IP LAN principal sin enviar datos por la red."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("192.0.2.1", 9))  # TEST-NET-1, no se manda tráfico
            return s.getsockname()[0]
        except OSError:
            return ""


def validar_ip(value: str) -> str:
    try:
        ip = ipaddress.ip_address(value.strip())
    except ValueError as exc:
        raise ValueError("La dirección no es una IPv4 válida.") from exc
    if not isinstance(ip, ipaddress.IPv4Address):
        raise ValueError("Usá la dirección IPv4 privada del POS Server.")
    if not ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_unspecified:
        raise ValueError("Usá una IP privada LAN (por ejemplo, 192.168.1.100).")
    # Sin zona / interfaz se debe mantener una sola dirección verificable.
    return str(ip)


def render_caddy(ip: str, backend_port: int = 8000) -> str:
    ip = validar_ip(ip)
    if not 1024 <= backend_port <= 65535:
        raise ValueError("El puerto interno de FastAPI debe ser 1024–65535.")
    return (
        "# Generado por IntraShop: HTTPS sin DNS, IP fija de esta instalación\n"
        "# La CA privada permanece SOLO en el servidor. No compartir root.key.\n"
        f"https://{ip} {{\n"
        "    tls internal\n"
        "    encode zstd gzip\n"
        "    header {\n"
        "        X-Content-Type-Options nosniff\n"
        "        Referrer-Policy same-origin\n"
        "        X-Frame-Options DENY\n"
        "    }\n"
        f"    reverse_proxy 127.0.0.1:{backend_port}\n"
        "}\n"
    )


def actualizar_env(contenido: str, ip: str) -> str:
    """Conservar el resto del .env y no crear ni imprimir API_KEY."""
    target = {
        "INTRASHOP_ENFORCE_HTTPS": "1",
        "POS_PUBLIC_URL": f"https://{validar_ip(ip)}",
    }
    lines: list[str] = []
    for line in contenido.splitlines():
        key = line.split("=", 1)[0].strip()
        if key in target and not line.lstrip().startswith("#"):
            continue
        lines.append(line)
    if lines and lines[-1].strip():
        lines.append("")
    lines.extend(f"{key}={value}" for key, value in target.items())
    return "\n".join(lines) + "\n"


def _run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(args, check=check, text=True)


def configurar(ip: str, port: int = 8000, *, confirmar: bool = True) -> dict:
    """Configura primero Caddy; solo activa FastAPI HTTPS si Caddy funcionó."""
    ip = validar_ip(ip)
    if sys.platform != "linux":
        raise RuntimeError(
            "Este asistente instala Caddy en Ubuntu/Linux. "
            "Para Windows hace falta el instalador correspondiente."
        )
    config = render_caddy(ip, port)
    if not shutil.which("sudo"):
        raise RuntimeError("Se necesita sudo para instalar/configurar Caddy.")
    if confirmar:
        print(f"\nHTTPS gratuito para IntraShop: https://{ip}/intrashop/")
        print("No se requiere DNS, dominio público ni edición manual de .env.")
        print("Se configurará Caddy en el puerto 443 de ESTA computadora.")
        print("Se guardará una copia de la configuración Caddy existente si la hubiera.")
        print("No se modificará la base de datos ni se eliminarán QR.")
        if input("¿Continuar? [s/N] ").strip().lower() not in ("s", "si", "sí"):
            raise RuntimeError("Cancelado; no se modificó la configuración.")
    if not shutil.which("caddy"):
        print("Instalando Caddy; Ubuntu solicitará contraseña administrativa...")
        _run(["sudo", "apt-get", "update"])
        _run(["sudo", "apt-get", "install", "-y", "caddy"])
    if not shutil.which("caddy"):
        raise RuntimeError("Caddy no se instaló correctamente.")

    with tempfile.TemporaryDirectory(prefix="intrashop-https-") as td:
        staged = Path(td) / "Caddyfile"
        staged.write_text(config, encoding="utf-8")
        _run(["caddy", "validate", "--config", str(staged), "--adapter", "caddyfile"])
        # No pisar una configuración de terceros silenciosamente.
        if CADDYFILE.exists():
            old = _run_capture(["sudo", "cat", str(CADDYFILE)])
            if ("# Generado por IntraShop:" not in old
                    and "Welcome to Caddy" not in old
                    and not _es_default_caddy(old)):
                if confirmar:
                    answer = input(
                        "Caddy ya tiene una configuración AJENA a IntraShop. "
                        "¿Reemplazarla (se guardará un backup)? [s/N] "
                    ).strip().lower()
                    if answer not in ("s", "si", "sí"):
                        raise RuntimeError("No se reemplazó la configuración existente.")
                else:
                    raise RuntimeError("Caddyfile preexistente no pertenece a IntraShop.")
            backup = str(CADDYFILE) + ".backup-" + datetime.now().strftime("%Y%m%d-%H%M%S")
            _run(["sudo", "cp", "-p", str(CADDYFILE), backup])
            print("Copia de configuración anterior:", backup)
        _run(["sudo", "install", "-m", "0644", str(staged), str(CADDYFILE)])
        try:
            _run(["sudo", "caddy", "validate", "--config", str(CADDYFILE)])
            _run(["sudo", "systemctl", "enable", "--now", "caddy"])
            _run(["sudo", "systemctl", "restart", "caddy"])
        except subprocess.CalledProcessError:
            # Si algo falla, restaurar config anterior si había backup.
            if "backup" in locals():
                _run(["sudo", "cp", "-p", backup, str(CADDYFILE)], check=False)
                _run(["sudo", "systemctl", "restart", "caddy"], check=False)
            raise

    env_path = ROOT / ".env"
    original = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    updated = actualizar_env(original, ip)
    if env_path.exists():
        env_backup = env_path.with_name(".env.backup-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
        shutil.copy2(env_path, env_backup)
        print("Copia del .env:", env_backup.name)
    fd, temp_name = tempfile.mkstemp(prefix=".env-intrashop-", dir=ROOT)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            fp.write(updated)
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, env_path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)

    print("\nHTTPS configurado. Reiniciá POS Server para activarlo.")
    print("URL de tienda:", f"https://{ip}/intrashop/")
    print("URL de POS:", f"https://{ip}")
    print("Para POS clientes y tótems hay que confiar una vez en la CA del servidor.")
    print("Ruta habitual del certificado público:", CA_CERT)
    print("NUNCA copiar el archivo root.key ni desactivar verificación TLS.")
    return {"url": f"https://{ip}", "env": str(env_path), "caddyfile": str(CADDYFILE)}


def _run_capture(args: list[str]) -> str:
    return subprocess.run(args, capture_output=True, text=True, check=True).stdout


def _es_default_caddy(data: str) -> bool:
    # Paquete Ubuntu: site :80, raíz /usr/share/caddy, respuesta "Hello, world!".
    return ":80 {" in data and "/usr/share/caddy" in data


def main(argv=None):
    parser = argparse.ArgumentParser(description="HTTPS IntraShop sin DNS ni pago")
    parser.add_argument("--ip", help="IP privada del POS Server; por defecto detección")
    parser.add_argument("--port", type=int, default=8000, help="Puerto interno FastAPI")
    parser.add_argument("--mostrar-config", action="store_true",
                        help="Mostrar configuración Caddy y salir sin cambios")
    args = parser.parse_args(argv)
    proposed = args.ip or detectar_ip_lan()
    if not proposed:
        print("No se detectó IP LAN. Ejecutá con --ip 192.168.1.100", file=sys.stderr)
        return 2
    try:
        ip = validar_ip(proposed)
        if args.mostrar_config:
            print(render_caddy(ip, args.port), end="")
            print("\n.env generado (sin escribir):")
            print(actualizar_env("", ip), end="")
        else:
            configurar(ip, args.port)
    except (ValueError, RuntimeError, subprocess.CalledProcessError, OSError) as exc:
        print("No se pudo configurar HTTPS:", exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

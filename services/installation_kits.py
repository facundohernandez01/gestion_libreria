"""Preparación de dispositivos IntraShop sin secretos reutilizables en kits.

El kit es material PUBLICO: CA del propio comercio, huella e instrucciones.
Nunca contiene contraseñas, API keys, token de caja, cookies ni códigos QR
de cobro. La identidad se activa luego desde POS Server, con código efímero.

Los instaladores se descubren únicamente si el build REAL existe en
distribution/builds/. No se anuncian URLs de descarga ficticias.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import ssl
import sys
import tempfile
import shutil
from pathlib import Path
from urllib.parse import urlsplit
from zipfile import ZIP_DEFLATED, ZipFile

BASE = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
BUILD_DIR = BASE / "distribution" / "builds"
CA_EXPORTED = Path.home() / ".local/share/intrashop/certificados/intrashop-root-ca.crt"
ROLES = {
    "pos": "Terminal de caja POS",
    "servidor": "POS Server",
    "totem": "Tótem IntraShop",
}
ARTIFACT_PREFIXES = {
    "pos": ("kiosmico", "pos-"),
    "servidor": ("intrashopserver", "pos-server-"),
    "totem": ("intrashop-", "intrashop_"),
}
ARTIFACT_SUFFIXES = (".msi", ".exe", ".zip", ".deb", ".appimage", ".tar.gz")


def validar_url_servidor(url: str) -> str:
    """Solo HTTPS con IP de LAN privada, nunca host externo ni credenciales."""
    parsed = urlsplit((url or "").strip())
    if (
        parsed.scheme != "https" or not parsed.hostname
        or parsed.username is not None or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query or parsed.fragment or parsed.port not in (None, 443)
    ):
        raise ValueError("El kit requiere una URL HTTPS de IP LAN, sin claves ni rutas.")
    try:
        addr = ipaddress.ip_address(parsed.hostname)
    except ValueError as exc:
        raise ValueError("Para este kit indicá la IP privada de POS Server.") from exc
    if (not isinstance(addr, ipaddress.IPv4Address) or not addr.is_private
            or addr.is_loopback or addr.is_link_local or addr.is_unspecified):
        raise ValueError("El equipo servidor debe tener una IPv4 privada válida.")
    return f"https://{addr}"


def datos_ca(archivo: Path = CA_EXPORTED) -> tuple[bytes, str]:
    """Lee exclusivamente el certificado raíz PÚBLICO, jamás la clave privada."""
    path = Path(archivo)
    if path.is_symlink() or not path.is_file():
        raise ValueError("No hay una CA pública exportada. Configurá HTTPS local primero.")
    data = path.read_bytes()
    if len(data) > 32768 or b"PRIVATE KEY" in data or b"BEGIN CERTIFICATE" not in data:
        raise ValueError("El archivo no es un certificado público de CA válido.")
    try:
        der = ssl.PEM_cert_to_DER_cert(data.decode("ascii"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("El archivo CA es inválido.") from exc
    return data, hashlib.sha256(der).hexdigest().upper()


def listar_instaladores(carpeta: Path = BUILD_DIR) -> dict[str, list[dict]]:
    """Detectar artefactos de build reales y conocidos, sin rutas arbitrarias."""
    result: dict[str, list[dict]] = {key: [] for key in ROLES}
    folder = Path(carpeta)
    if not folder.is_dir():
        return result
    for file in sorted(folder.iterdir()):
        if file.is_symlink() or not file.is_file():
            continue
        name = file.name.casefold()
        if (not any(name.endswith(ext) for ext in ARTIFACT_SUFFIXES)
                or not re.fullmatch(r"[a-zA-Z0-9._ -]+", file.name)):
            continue
        for role, prefixes in ARTIFACT_PREFIXES.items():
            if any(name.startswith(prefix) for prefix in prefixes):
                result[role].append({
                    "nombre": file.name,
                    "bytes": file.stat().st_size,
                    "ruta": str(file.resolve()),
                })
                break
    return result


def crear_kit_conexion(
    destino: Path, url: str, rol: str, *,
    certificado: Path = CA_EXPORTED,
) -> dict:
    """Generar ZIP de conexión sin credenciales, con certificado y huella.

    Se crea en una carpeta que el operador elige con la GUI local. Nunca
    se publica automáticamente en una URL anónima de la LAN.
    """
    if rol not in ROLES or rol == "servidor":
        raise ValueError("El kit de conexión corresponde a POS cliente o tótem.")
    safe_url = validar_url_servidor(url)
    pem, sha = datos_ca(certificado)
    dest = Path(destino).expanduser()
    if dest.suffix.lower() != ".zip":
        raise ValueError("Elegí un archivo ZIP de destino.")
    if dest.is_symlink():
        raise ValueError("No se permite escribir a un enlace simbólico.")
    if not dest.parent.is_dir():
        raise ValueError("No existe la carpeta de destino.")
    manifest = {
        "schema": "intrashop-client-kit/v1",
        "tipo": rol,
        "servidor": safe_url,
        "catalogo": safe_url + "/intrashop/",
        "ca_publica": "intrashop-root-ca.crt",
        "ca_sha256": sha,
        "requiere_aprobacion_ca": True,
        "requiere_emparejamiento_pos_server": True,
        "credenciales_incluidas": False,
    }
    text = (
        "INTRASHOP - CONECTAR ESTE EQUIPO\n\n"
        f"Perfil: {ROLES[rol]}\n"
        f"Servidor: {safe_url}\n"
        f"Tienda: {safe_url}/intrashop/\n\n"
        "1. Confirmar con el administrador del comercio que la huella\n"
        "   del certificado coincida con la que muestra POS Server:\n"
        f"   {sha}\n"
        "2. Autorizar la CA pública en este dispositivo usando el\n"
        "   instalador confiable correspondiente a Windows/Linux.\n"
        "   NO marcar excepciones HTTPS ni deshabilitar certificados.\n"
        "3. Conectar la app al servidor HTTPS indicado arriba.\n"
        "4. Autorizar el tótem con un código temporal generado desde\n"
        "   POS Server. Para POS cliente, iniciar sesión con usuario\n"
        "   y permisos de caja de ese comercio.\n\n"
        "Este ZIP NO contiene ni ejecuta instaladores ni guarda claves.\n"
        "No contiene contraseñas, API keys, tokens de Mercado Pago\n"
        "ni códigos de vinculación en la URL.\n"
    )
    with ZipFile(dest, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("conexion.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        archive.writestr("intrashop-root-ca.crt", pem)
        archive.writestr("INSTRUCCIONES.txt", text)
        if rol == "totem":
            # Acceso directo web Windows sin instalar Tauri ni claves.
            # El navegador igualmente necesita confiar en la CA del comercio.
            archive.writestr(
                "Abrir-IntraShop.url",
                "[InternetShortcut]" + chr(13) + chr(10)
                + "URL=" + safe_url + "/intrashop/" + chr(13) + chr(10),
            )
    return {"archivo": str(dest), "url": safe_url, "sha256_ca": sha, "perfil": rol}


def importar_suite(archivo: Path, destino: Path = BUILD_DIR) -> int:
    """Importar el artefacto oficial elegido localmente; verificar integridad.
    
    El manifiesto no constituye una firma digital. Nunca ejecutar el contenido.
    """
    destino = Path(destino)
    if destino.is_symlink():
        raise ValueError("Carpeta de distribución inválida.")
    destino.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(archivo) as archive, tempfile.TemporaryDirectory(dir=destino.parent) as temp:
        entries = archive.infolist()
        if len(entries) > 100:
            raise ValueError("Demasiadas entradas en el paquete.")
        prefix = "distribution/builds/"
        manifests = [e for e in entries if e.filename == prefix + "manifest.json"]
        if len(manifests) != 1 or manifests[0].file_size > 65536:
            raise ValueError("No es un artefacto IntraShop Suite válido.")
        manifest = json.loads(archive.read(manifests[0]))
        if manifest.get("schema") != "intrashop-suite/v1":
            raise ValueError("Versión de distribución no admitida.")
        records = manifest.get("artifacts")
        if not isinstance(records, list) or not 6 <= len(records) <= 24:
            raise ValueError("Manifiesto incompleto.")
        staged = Path(temp) / "builds"
        staged.mkdir()
        names = set()
        roles = set()
        total = 0
        for row in records:
            name = row["file"]
            role = row["role"]
            platform = row["platform"]
            if (not isinstance(name, str) or not re.fullmatch(r"[a-zA-Z0-9._ -]+", name)
                    or name.casefold() in names or role not in ROLES
                    or platform not in ("windows", "linux")
                    or not name.casefold().startswith(ARTIFACT_PREFIXES[role])
                    or not name.casefold().endswith(ARTIFACT_SUFFIXES)):
                raise ValueError("Nombre o perfil inválido.")
            names.add(name.casefold())
            roles.add((role, platform))
            matches = [e for e in entries if e.filename == prefix + name]
            size = row["bytes"]
            if len(matches) != 1 or type(size) is not int or not 0 < size <= 2 * 1024**3 or matches[0].file_size != size:
                raise ValueError("Compilación incompleta: " + name)
            total += size
            if total > 8 * 1024**3:
                raise ValueError("Paquete demasiado grande.")
            digest = hashlib.sha256()
            written = 0
            with archive.open(matches[0]) as source, (staged / name).open("xb") as target:
                while chunk := source.read(1024 * 1024):
                    written += len(chunk)
                    if written > size:
                        raise ValueError("Tamaño inesperado.")
                    digest.update(chunk)
                    target.write(chunk)
            if written != size or digest.hexdigest() != row["sha256"]:
                raise ValueError("SHA-256 incorrecto: " + name)
        if roles != {(r, p) for r in ROLES for p in ("windows", "linux")}:
            raise ValueError("Faltan compilaciones para algún perfil.")
        (staged / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        # Replace the set as a unit; don't mix versions.
        previous = Path(temp) / "previous"
        if destino.exists():
            destino.rename(previous)
        try:
            staged.rename(destino)
        except OSError:
            if previous.exists():
                previous.rename(destino)
            raise
    return len(records)

"""Confianza TLS privada del cliente, sin modificar certificados del sistema."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import ssl
import tempfile
from pathlib import Path
from zipfile import ZipFile

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from services.installation_kits import validar_url_servidor

TRUST_FILE = Path.home() / ".config" / "intrashop" / "pos_trust.json"


def leer_kit(path: Path) -> tuple[str, str, str]:
    """Leer solo dos entradas acotadas; nunca extraer archivos del ZIP."""
    with ZipFile(path) as archive:
        for name, limit in (("conexion.json", 16384), ("intrashop-root-ca.crt", 32768)):
            entries = [i for i in archive.infolist() if i.filename == name]
            if len(entries) != 1 or entries[0].file_size > limit:
                raise ValueError("Kit de conexión inválido")
        manifest = json.loads(archive.read("conexion.json"))
        pem = archive.read("intrashop-root-ca.crt").decode("ascii")
    if manifest.get("schema") != "intrashop-client-kit/v1" or manifest.get("tipo") != "pos":
        raise ValueError("Seleccioná un kit de conexión para POS")
    url = validar_url_servidor(manifest["servidor"])
    fingerprint = _fingerprint(pem)
    if not hmac.compare_digest(fingerprint, str(manifest.get("ca_sha256", "")).upper()):
        raise ValueError("El certificado no coincide con el kit")
    return url, pem, fingerprint


def _fingerprint(pem: str) -> str:
    if pem.count("-----BEGIN CERTIFICATE-----") != 1 or "PRIVATE KEY" in pem:
        raise ValueError("Se requiere un único certificado público")
    cert = x509.load_pem_x509_certificate(pem.encode("ascii"))
    if not cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
        raise ValueError("El certificado no corresponde a una CA")
    return cert.fingerprint(hashes.SHA256()).hex().upper()


def guardar_confianza(url: str, pem: str, huella_confirmada: str, *, destino=None):
    """La huella debe verificarse por separado en la consola del comercio."""
    url = validar_url_servidor(url)
    fingerprint = _fingerprint(pem)
    if not hmac.compare_digest(fingerprint, huella_confirmada.replace(" ", "").replace(":", "").upper()):
        raise ValueError("La huella no coincide con POS Server")
    path = Path(destino or TRUST_FILE)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({"url": url, "ca": pem, "sha256": fingerprint}, stream)
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def opciones_http(url: str, *, origen=None) -> dict:
    """No usar proxies ambientales ni degradar una conexión vinculada a HTTP."""
    path = Path(origen or TRUST_FILE)
    if not path.exists():
        return {"trust_env": False}
    data = json.loads(path.read_text(encoding="utf-8"))
    if url.rstrip("/") != data["url"]:
        raise ValueError("La dirección no coincide con el comercio autorizado. Importá su kit de conexión.")
    if not hmac.compare_digest(_fingerprint(data["ca"]), data["sha256"]):
        raise ValueError("El certificado local de confianza está dañado")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_verify_locations(cadata=data["ca"])
    return {"verify": context, "trust_env": False}

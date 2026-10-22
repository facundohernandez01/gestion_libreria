"""Cliente WSAA (autenticación AFIP) — reconstruido del build.

Maneja la autenticación mediante certificados digitales y obtención de Token/Sign.
Incluye un SSLAdapter con ``DEFAULT@SECLEVEL=1`` para evitar DH_KEY_TOO_SMALL.
"""
from __future__ import annotations

import base64
import ssl
from datetime import datetime, timedelta

import requests
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs7
from lxml import etree
from requests import Session
from zeep import Client
from zeep.transports import Transport

import configwsfe as config

ctx = ssl.create_default_context()
ctx.set_ciphers("DEFAULT@SECLEVEL=1")
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


class SSLAdapter(requests.adapters.HTTPAdapter):
    """Adaptador para inyectar el contexto SSL con SECLEVEL=1."""

    def init_poolmanager(self, *args, **kwargs):
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, *args, **kwargs):
        kwargs["ssl_context"] = ctx
        return super().proxy_manager_for(*args, **kwargs)


class WSAAClient:
    """Cliente para autenticación con WSAA de AFIP."""

    def __init__(self):
        self.url = config.WSAA_URL
        self.cert_file = config.CERT_FILE
        self.key_file = config.KEY_FILE
        self.service = "wsfe"
        self.token = None
        self.sign = None
        self.expiration = None

    def crear_tra(self) -> str:
        """Crea el TRA (Ticket de Requerimiento de Acceso) en formato XML."""
        unique_id = int(datetime.now().timestamp())
        generation_time = datetime.now() - timedelta(minutes=10)
        expiration_time = datetime.now() + timedelta(hours=12)
        gen_time_str = generation_time.strftime("%Y-%m-%dT%H:%M:%S-03:00")
        exp_time_str = expiration_time.strftime("%Y-%m-%dT%H:%M:%S-03:00")
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<loginTicketRequest version="1.0">\n'
            "  <header>\n"
            f"    <uniqueId>{unique_id}</uniqueId>\n"
            f"    <generationTime>{gen_time_str}</generationTime>\n"
            f"    <expirationTime>{exp_time_str}</expirationTime>\n"
            "  </header>\n"
            f"  <service>{self.service}</service>\n"
            "</loginTicketRequest>"
        )

    def firmar_tra(self, tra: str) -> str:
        """Firma el TRA con el certificado usando cryptography (CMS/PKCS7)."""
        try:
            with open(self.cert_file, "rb") as f:
                cert_data = f.read()
            cert = x509.load_pem_x509_certificate(cert_data, default_backend())

            with open(self.key_file, "rb") as f:
                key_data = f.read()
            private_key = serialization.load_pem_private_key(
                key_data, password=None, backend=default_backend()
            )

            tra_bytes = tra.encode("utf-8")
            options = [pkcs7.PKCS7Options.Binary]
            builder = (
                pkcs7.PKCS7SignatureBuilder()
                .set_data(tra_bytes)
                .add_signer(cert, private_key, hashes.SHA256())
            )
            cms_data = builder.sign(serialization.Encoding.DER, options)
            return base64.b64encode(cms_data).decode("utf-8")
        except Exception as e:  # noqa: BLE001
            raise Exception(f"Error al firmar TRA: {str(e)}")

    def login(self) -> dict:
        """Realiza el login y obtiene las credenciales (Token/Sign)."""
        try:
            config.validar_certificados()
            tra = self.crear_tra()
            cms = self.firmar_tra(tra)

            session = Session()
            session.mount("https://", SSLAdapter())
            session.verify = False
            transport = Transport(session=session, timeout=15)
            client = Client(self.url, transport=transport)
            response = client.service.loginCms(cms)

            root = etree.fromstring(response.encode("utf-8"))
            self.token = root.find(".//token").text
            self.sign = root.find(".//sign").text
            header = root.find(".//header")
            if header is not None:
                exp_elem = header.find("expirationTime")
                if exp_elem is not None:
                    self.expiration = exp_elem.text

            return {
                "token": self.token,
                "sign": self.sign,
                "expiration": self.expiration,
                "success": True,
                "message": "Autenticación exitosa",
            }
        except Exception as e:  # noqa: BLE001
            error_msg = str(e)
            if "TA valido" in error_msg or "ya posee" in error_msg.lower():
                return {
                    "success": True,
                    "token": self.token,
                    "sign": self.sign,
                    "expiration": self.expiration,
                    "message": "Ya existe una autenticación vigente.",
                    "reused": True,
                }
            return {"success": False, "message": f"Error en autenticación: {error_msg}"}

    def get_credentials(self) -> dict:
        return {"token": self.token, "sign": self.sign}

    def is_authenticated(self) -> bool:
        return self.token is not None and self.sign is not None

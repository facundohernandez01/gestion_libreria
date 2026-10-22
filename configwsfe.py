"""Configuración AFIP (WSAA/WSFE).

Prioridad de lectura de cada valor:
    1. Tabla `config` de la DB (configurable desde Ajustes)
    2. Variables de entorno / `.env` (vía core.settings)
    3. Defaults

Llamar a ``reload()`` para re-leer la DB en caliente (p. ej. al abrir Ajustes
o al instanciar FacturacionManager).
"""
from __future__ import annotations

import os

try:
    from core.settings import settings as _settings
except Exception:  # pragma: no cover
    _settings = None


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CERT_DIR = os.path.join(BASE_DIR, "certificados")

# Rellenados por reload()
CUIT = ""
PUNTO_VENTA = 1
TIPO_FACTURA = "C"
TESTING = True
CERT_FILE = os.path.join(CERT_DIR, "wsaa.crt")
KEY_FILE = os.path.join(CERT_DIR, "wsaa.key")
WSAA_URL = "https://wsaahomo.afip.gov.ar/ws/services/LoginCms?wsdl"
WSFE_URL = "https://wswhomo.afip.gov.ar/wsfev1/service.asmx?WSDL"


def _db_get(key: str) -> str:
    try:
        from database_manager import DatabaseManager

        val = DatabaseManager().get_config_value(key)
        return (val or "").strip()
    except Exception:
        return ""


def _env(attr: str, env: str, default: str = "") -> str:
    if _settings is not None and getattr(_settings, attr, None) not in (None, ""):
        return str(getattr(_settings, attr)).strip()
    return os.getenv(env, default).strip()


def _env_bool(attr: str, env: str, default: bool) -> bool:
    val = _db_get(env)
    if val:
        return val.lower() in ("1", "true", "yes", "si", "sí", "on")
    if _settings is not None and getattr(_settings, attr, None) is not None:
        return bool(getattr(_settings, attr))
    raw = os.getenv(env, "")
    if raw:
        return raw.strip().lower() in ("1", "true", "yes", "si", "sí", "on")
    return default


def _int(val, default: int = 1) -> int:
    try:
        return int(str(val).strip())
    except (TypeError, ValueError):
        return default


def reload() -> None:
    """Re-lee la configuración AFIP (DB > .env > default)."""
    global CUIT, PUNTO_VENTA, TIPO_FACTURA, TESTING, CERT_FILE, KEY_FILE, WSAA_URL, WSFE_URL

    CUIT = _db_get("AFIP_CUIT") or _env("afip_cuit", "AFIP_CUIT") or _env("cuit", "CUIT")
    PUNTO_VENTA = _int(_db_get("AFIP_PUNTO_VENTA") or _env("afip_punto_venta", "AFIP_PUNTO_VENTA", "1"), 1)
    TIPO_FACTURA = (_db_get("AFIP_TIPO_FACTURA") or _env("afip_tipo_factura", "AFIP_TIPO_FACTURA", "C") or "C").upper()
    TESTING = _env_bool("afip_testing", "AFIP_TESTING", True)

    cert = _db_get("AFIP_CERT_FILE") or _env("afip_cert_file", "AFIP_CERT_FILE")
    key = _db_get("AFIP_KEY_FILE") or _env("afip_key_file", "AFIP_KEY_FILE")
    CERT_FILE = cert or os.path.join(CERT_DIR, "wsaa.crt")
    KEY_FILE = key or os.path.join(CERT_DIR, "wsaa.key")

    if TESTING:
        WSAA_URL = "https://wsaahomo.afip.gov.ar/ws/services/LoginCms?wsdl"
        WSFE_URL = "https://wswhomo.afip.gov.ar/wsfev1/service.asmx?WSDL"
    else:
        WSAA_URL = "https://wsaa.afip.gov.ar/ws/services/LoginCms?wsdl"
        WSFE_URL = "https://servicios1.afip.gov.ar/wsfev1/service.asmx?WSDL"


# Tipos de comprobante
TIPO_CBTE_FACTURA_A = 1
TIPO_CBTE_FACTURA_B = 6
TIPO_CBTE_FACTURA_C = 11

# Conceptos
CONCEPTO_PRODUCTOS = 1
CONCEPTO_SERVICIOS = 2
CONCEPTO_MIXTO = 3

# Tipos de documento
DOC_TIPO_CUIT = 80
DOC_TIPO_DNI = 96
DOC_TIPO_CONSUMIDOR_FINAL = 99

# Alícuotas de IVA
IVA_21_PORCIENTO = 5
IVA_10_5_PORCIENTO = 4
IVA_27_PORCIENTO = 6
IVA_0_PORCIENTO = 3

# Monedas
MONEDA_PESOS = "PES"
MONEDA_DOLARES = "DOL"

APP_TITLE = "Sistema de Facturación AFIP"
APP_WIDTH = 900
APP_HEIGHT = 700


def tipo_cbte_para_factura(tipo: str) -> int:
    """Mapea 'A'/'B'/'C' al código de comprobante de AFIP."""
    return {"A": TIPO_CBTE_FACTURA_A, "B": TIPO_CBTE_FACTURA_B}.get(
        (tipo or "C").upper(), TIPO_CBTE_FACTURA_C
    )


def validar_certificados() -> bool:
    print("=== VERIFICANDO ARCHIVOS DE CERTIFICADOS ===")
    print(f"Ruta del certificado (.crt): {CERT_FILE}")
    print(f"Ruta de la clave (.key): {KEY_FILE}")
    print("✔ Certificado encontrado" if os.path.exists(CERT_FILE) else "✘ ERROR: No se encontró el certificado")
    print("✔ Clave privada encontrada" if os.path.exists(KEY_FILE) else "✘ ERROR: No se encontró la clave privada")
    if not os.path.exists(CERT_FILE):
        raise FileNotFoundError(f"No se encontró el certificado: {CERT_FILE}")
    if not os.path.exists(KEY_FILE):
        raise FileNotFoundError(f"No se encontró la clave privada: {KEY_FILE}")
    print("=== VALIDACIÓN COMPLETA ===\n")
    return True


def get_modo_texto() -> str:
    return "HOMOLOGACIÓN (Testing)" if TESTING else "PRODUCCIÓN"


def get_info_config() -> dict:
    return {
        "modo": get_modo_texto(),
        "cuit": CUIT,
        "punto_venta": PUNTO_VENTA,
        "tipo_factura": TIPO_FACTURA,
        "certificado": CERT_FILE,
        "wsaa_url": WSAA_URL,
        "wsfe_url": WSFE_URL,
    }


reload()

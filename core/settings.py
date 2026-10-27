"""Configuración centralizada (patrón Singleton).

Prioridad de lectura:
  1. Variables de entorno / archivo .env
  2. Tabla `config` de SQLite (compatibilidad con instalación existente)

Uso:
    from core.settings import settings
    token = settings.mp_access_token
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _load_dotenv_if_available() -> None:
    try:
        from utils.paths import base_dir

        env_path = base_dir() / ".env"
    except Exception:
        env_path = None
    try:
        from dotenv import load_dotenv  # type: ignore

        if env_path is not None and env_path.exists():
            load_dotenv(env_path, override=False)
        else:
            load_dotenv()
        return
    except Exception:
        pass
    # Fallback mínimo sin dependencias: parsea .env
    try:
        from pathlib import Path

        path = env_path or Path(".env")
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            if key and key not in __import__("os").environ:
                __import__("os").environ[key] = val.strip().strip("'\"")
    except Exception:
        pass


_load_dotenv_if_available()


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


def _env_bool(key: str, default: bool = False) -> bool:
    val = os.getenv(key, "")
    if not val:
        return default
    return val.strip().lower() in ("1", "true", "yes", "si", "sí", "on")


def _env_int(key: str, default: int = 0) -> int:
    try:
        return int(os.getenv(key, str(default)).strip())
    except (ValueError, AttributeError):
        return default


def _default_db_path() -> str:
    """Ruta absoluta de la DB junto al ejecutable/proyecto."""
    try:
        from utils.paths import db_path

        return db_path()
    except Exception:
        return "libreria.db"


@dataclass
class Settings:
    """Singleton simple de configuración."""

    _instance = None

    app_env: str = field(default="prod")
    db_path: str = field(default="libreria.db")
    log_level: str = field(default="INFO")

    mp_access_token: str = field(default="")
    mp_user_id: str = field(default="")
    mp_external_store_id: str = field(default="")
    mp_external_pos_id: str = field(default="")
    mp_store_id: str = field(default="")
    mp_qr_url: str = field(default="")
    mp_qr_url: str = field(default="")
    mp_timeout_seg: int = field(default=15)
    mp_poll_interval_seg: int = field(default=5)
    mp_poll_timeout_seg: int = field(default=300)

    nombre_negocio: str = field(default="Mi Negocio")
    cuit: str = field(default="")
    direccion_negocio: str = field(default="")
    condicion_iva: str = field(default="Consumidor Final")
    ingresos_brutos: str = field(default="")
    inicio_actividades: str = field(default="")
    recargo_porcentaje: float = field(default=0.0)
    recargo_debito: float = field(default=0.0)
    recargo_credito: float = field(default=0.0)

    # Medios de pago (recargo propio cada uno + poder desactivarlos)
    mp_activo: bool = field(default=True)
    tarjeta_debito_activo: bool = field(default=True)
    tarjeta_credito_activo: bool = field(default=True)
    vuelto_activo: bool = field(default=False)

    afip_cuit: str = field(default="")
    afip_punto_venta: int = field(default=1)
    afip_tipo_factura: str = field(default="C")
    afip_testing: bool = field(default=True)
    afip_cert_file: str = field(default="")
    afip_key_file: str = field(default="")

    facturacion_activa: bool = field(default=True)
    facturacion_tipo: str = field(default="ticket")
    facturacion_prefijo: str = field(default="TK")
    facturacion_dir: str = field(default="comprobantes")

    # Facturación automática por medio de pago (por defecto NO)
    facturar_auto_qr: bool = field(default=False)
    facturar_auto_efectivo: bool = field(default=False)

    # Red / multi-usuario (FastAPI)
    modo_red: str = field(default="local")          # local | servidor | cliente
    server_url: str = field(default="http://127.0.0.1:8000")
    api_key: str = field(default="libreria-lan")
    api_host: str = field(default="0.0.0.0")
    api_port: int = field(default=8000)

    # Versión web (Flet): /cliente y /stock en la LAN
    web_host: str = field(default="0.0.0.0")
    web_port: int = field(default=8550)

    # Directorios de comprobantes (botones de carpeta en Ajustes)
    comprobantes_dir: str = field(default="comprobantes")
    tickets_dir: str = field(default="tickets")

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._loaded = False
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_loaded", False):
            return
        self.reload()
        self._loaded = True

    def _reload(self, from_db: bool = True) -> None:
        _load_dotenv_if_available()
        self.app_env = _env("APP_ENV", "prod")
        self.db_path = _default_db_path()
        self.log_level = _env("LOG_LEVEL", "INFO").upper()

        self.mp_access_token = _env("MP_ACCESS_TOKEN", "")
        self.mp_user_id = _env("MP_USER_ID", "")
        self.mp_external_store_id = _env("MP_EXTERNAL_STORE_ID", "")
        self.mp_external_pos_id = _env("MP_EXTERNAL_POS_ID", "")
        self.mp_store_id = _env("MP_STORE_ID", "")
        self.mp_qr_url = _env("MP_QR_URL", "")
        self.mp_timeout_seg = _env_int("MP_TIMEOUT_SEG", 15)
        self.mp_poll_interval_seg = _env_int("MP_POLL_INTERVAL_SEG", 5)
        self.mp_poll_timeout_seg = _env_int("MP_POLL_TIMEOUT_SEG", 300)

        self.nombre_negocio = _env("NOMBRE_NEGOCIO", "Mi Negocio")
        self.cuit = _env("CUIT", "")
        self.direccion_negocio = _env("DIRECCION_NEGOCIO", "")
        self.condicion_iva = _env("CONDICION_IVA", "Consumidor Final")
        self.ingresos_brutos = _env("INGRESOS_BRUTOS", "")
        self.inicio_actividades = _env("INICIO_ACTIVIDADES", "")
        try:
            self.recargo_porcentaje = float(_env("RECARGO_PORCENTAJE", "0").replace(",", "."))
        except ValueError:
            self.recargo_porcentaje = 0.0
        try:
            self.recargo_debito = float(_env("RECARGO_DEBITO", "0").replace(",", "."))
        except ValueError:
            self.recargo_debito = 0.0
        try:
            self.recargo_credito = float(_env("RECARGO_CREDITO", "0").replace(",", "."))
        except ValueError:
            self.recargo_credito = 0.0

        self.mp_activo = _env_bool("MP_ACTIVO", True)
        self.tarjeta_debito_activo = _env_bool("TARJETA_DEBITO_ACTIVO", True)
        self.tarjeta_credito_activo = _env_bool("TARJETA_CREDITO_ACTIVO", True)
        self.vuelto_activo = _env_bool("VUELTO_ACTIVO", False)

        self.afip_cuit = _env("AFIP_CUIT", "")
        self.afip_punto_venta = _env_int("AFIP_PUNTO_VENTA", 1)
        self.afip_tipo_factura = _env("AFIP_TIPO_FACTURA", "C")
        self.afip_testing = _env("AFIP_TESTING", "True").lower() in ("1", "true", "yes", "sí", "si", "on")
        self.afip_cert_file = _env("AFIP_CERT_FILE", "")
        self.afip_key_file = _env("AFIP_KEY_FILE", "")

        self.facturacion_activa = _env_bool("FACTURACION_ACTIVA", True)
        self.facturacion_tipo = _env("FACTURACION_TIPO", "ticket").lower()
        self.facturacion_prefijo = _env("FACTURACION_PREFIJO", "TK")
        self.facturacion_dir = _env("FACTURACION_DIR", "comprobantes")

        self.facturar_auto_qr = _env_bool("FACTURAR_AUTO_QR", False)
        self.facturar_auto_efectivo = _env_bool("FACTURAR_AUTO_EFECTIVO", False)

        self.modo_red = _env("MODO_RED", "local").strip().lower()
        self.server_url = _env("SERVER_URL", "http://127.0.0.1:8000")
        self.api_key = _env("API_KEY", "libreria-lan")
        self.api_host = _env("API_HOST", "0.0.0.0")
        self.api_port = _env_int("API_PORT", 8000)
        self.web_host = _env("WEB_HOST", "0.0.0.0")
        self.web_port = _env_int("WEB_PORT", 8550)

        self.comprobantes_dir = _env("COMPROBANTES_DIR", "comprobantes")
        self.tickets_dir = _env("TICKETS_DIR", "tickets")

        # La DB (Ajustes) manda sobre .env para las claves gestionadas en Ajustes.
        if from_db:
            self._overlay_db()

    def reload(self, from_db: bool = True) -> None:
        self._reload(from_db=from_db)

    def _db_value(self, clave: str) -> str:
        try:
            from database_manager import DatabaseManager

            v = DatabaseManager().get_config_value(clave)
            return v.strip() if v else ""
        except Exception:
            return ""

    @staticmethod
    def _truthy(v: str) -> bool:
        return str(v).strip().lower() in ("1", "true", "yes", "si", "sí", "on")

    def _overlay_db(self) -> None:
        """Superpone los valores de la DB (Ajustes) a los de .env."""
        def s(attr, clave):
            v = self._db_value(clave)
            if v:
                setattr(self, attr, v)

        def b(attr, clave):
            v = self._db_value(clave)
            if v:
                setattr(self, attr, self._truthy(v))

        def fl(attr, clave):
            v = self._db_value(clave)
            if v:
                try:
                    setattr(self, attr, float(v.replace(",", ".")))
                except ValueError:
                    pass

        def it(attr, clave):
            v = self._db_value(clave)
            if v:
                try:
                    setattr(self, attr, int(float(v)))
                except ValueError:
                    pass

        s("nombre_negocio", "NOMBRE_NEGOCIO")
        s("cuit", "CUIT")
        s("direccion_negocio", "DIRECCION")
        s("condicion_iva", "CONDICION_IVA")
        s("ingresos_brutos", "INGRESOS_BRUTOS")
        s("inicio_actividades", "INICIO_ACTIVIDADES")
        fl("recargo_porcentaje", "RECARGO")
        fl("recargo_debito", "RECARGO_DEBITO")
        fl("recargo_credito", "RECARGO_CREDITO")
        b("mp_activo", "MP_ACTIVO")
        b("tarjeta_debito_activo", "TARJETA_DEBITO_ACTIVO")
        b("tarjeta_credito_activo", "TARJETA_CREDITO_ACTIVO")
        b("vuelto_activo", "VUELTO_ACTIVO")
        s("afip_cuit", "AFIP_CUIT")
        if not self.cuit:
            self.cuit = self.afip_cuit
        if not self.afip_cuit:
            self.afip_cuit = self.cuit
        it("afip_punto_venta", "AFIP_PUNTO_VENTA")
        s("afip_tipo_factura", "AFIP_TIPO_FACTURA")
        b("afip_testing", "AFIP_TESTING")
        s("afip_cert_file", "AFIP_CERT_FILE")
        s("afip_key_file", "AFIP_KEY_FILE")
        b("facturacion_activa", "FACTURACION_ACTIVA")
        s("facturacion_tipo", "FACTURACION_TIPO")
        s("facturacion_prefijo", "FACTURACION_PREFIJO")
        s("facturacion_dir", "FACTURACION_DIR")
        b("facturar_auto_qr", "FACTURAR_AUTO_QR")
        b("facturar_auto_efectivo", "FACTURAR_AUTO_EFECTIVO")
        s("mp_access_token", "ACCESS_TOKEN")
        s("mp_user_id", "USER_ID")
        s("mp_external_store_id", "EXTERNAL_STORE_ID")
        s("mp_external_pos_id", "EXTERNAL_POS_ID")
        s("mp_qr_url", "QR_URL")
        s("modo_red", "MODO_RED")
        s("server_url", "SERVER_URL")
        s("comprobantes_dir", "COMPROBANTES_DIR")
        s("tickets_dir", "TICKETS_DIR")

    @property
    def mp_configurado(self) -> bool:
        return bool(self.mp_access_token and self.mp_user_id)

    def _dir_from_db(self, clave: str) -> str:
        v = self._db_value(clave)
        return v

    @property
    def comprobantes_path(self) -> str:
        """Directorio de comprobantes .txt (ventas no facturadas)."""
        return self._dir_from_db("COMPROBANTES_DIR") or self.comprobantes_dir

    @property
    def tickets_path(self) -> str:
        """Directorio de tickets PDF / facturas emitidas."""
        return self._dir_from_db("TICKETS_DIR") or self.tickets_dir

    def as_dict(self, *, ocultar_secretos: bool = True) -> dict:
        d = {
            "APP_ENV": self.app_env,
            "DB_PATH": self.db_path,
            "MP_USER_ID": self.mp_user_id,
            "MP_EXTERNAL_STORE_ID": self.mp_external_store_id,
            "MP_EXTERNAL_POS_ID": self.mp_external_pos_id,
            "NOMBRE_NEGOCIO": self.nombre_negocio,
            "CUIT": self.cuit,
            "INGRESOS_BRUTOS": self.ingresos_brutos,
            "INICIO_ACTIVIDADES": self.inicio_actividades,
            "CONDICION_IVA": self.condicion_iva,
            "FACTURACION_ACTIVA": self.facturacion_activa,
            "FACTURACION_TIPO": self.facturacion_tipo,
        }
        d["MP_ACCESS_TOKEN"] = "***" if (ocultar_secretos and self.mp_access_token) else self.mp_access_token
        return d


settings = Settings()

"""Servicio Mercado Pago QR estático (fixed_amount) — patrón Service/Singleton.

Centraliza TODA la integración MP:
- crear orden dinámica sobre QR estático (PUT .../orders)
- polling de estado con cancelación cooperativa
- CRUD Store / POS, sincronización de STORE_ID numérico
- descarga de QR

Los tokens SIEMPRE salen de `core.settings` (.env) o de la tabla config (legacy).
Nunca hardcodear tokens en código.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Callable, Optional

import requests

logger = logging.getLogger(__name__)

MP_BASE = "https://api.mercadopago.com"


class MercadoPagoService:
    _instance = None

    def __new__(cls, *a, **kw):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_done = False
        return cls._instance

    def __init__(self, db=None):
        if getattr(self, "_init_done", False):
            return
        self._db = db
        self._ultima_referencia: Optional[str] = None
        self._init_done = True

    # ---------- config ----------
    def _db_or_none(self):
        if self._db is not None:
            return self._db
        try:
            from database_manager import DatabaseManager

            self._db = DatabaseManager()
            return self._db
        except Exception:
            return None

    def credenciales(self) -> tuple[str, str, str, str]:
        """(token, user_id, store_ext, pos_ext) con prioridad .env > DB."""
        from core.settings import settings

        token = settings.mp_access_token or ""
        uid = settings.mp_user_id or ""
        store_ext = settings.mp_external_store_id or ""
        pos_ext = settings.mp_external_pos_id or ""
        db = self._db_or_none()
        if db is not None:
            try:
                token = token or db.get_config_value("ACCESS_TOKEN") or db.get_config_value("MP_ACCESS_TOKEN") or ""
                uid = uid or db.get_config_value("USER_ID") or db.get_config_value("MP_USER_ID") or ""
                store_ext = store_ext or db.get_config_value("EXTERNAL_STORE_ID") or ""
                pos_ext = pos_ext or db.get_config_value("EXTERNAL_POS_ID") or ""
            except Exception:
                pass
        return token, uid, store_ext, pos_ext

    def _headers(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # ---------- órdenes ----------
    def crear_orden(self, monto: float, cb: Optional[Callable[[str], None]] = None,
                    pos_ext: str = "", store_ext: str = "") -> bool:
        token, uid, store_d, pos_d = self.credenciales()
        pos_ext = pos_ext or pos_d
        store_ext = store_ext or store_d
        if not token or not uid or not pos_ext or not store_ext:
            self._log("❌ Faltan credenciales MP (token/uid/store/pos). Ver .env.", cb)
            return False
        try:
            monto_f = round(float(monto), 2)
            if monto_f <= 0:
                self._log("❌ Monto inválido.", cb)
                return False
        except (TypeError, ValueError):
            self._log("❌ Monto inválido.", cb)
            return False

        from core.settings import settings

        self._ultima_referencia = f"ORDER_{int(time.time())}"
        url = f"{MP_BASE}/instore/qr/seller/collectors/{uid}/stores/{store_ext}/pos/{pos_ext}/orders"
        payload = {
            "external_reference": self._ultima_referencia,
            "title": "Venta en local",
            "description": f"Cobro de ${monto_f:.2f}",
            "total_amount": monto_f,
            "items": [{
                "sku_number": "LOCAL001",
                "category": "marketplace",
                "title": "Venta en local",
                "description": "Cobro en mostrador",
                "unit_price": monto_f,
                "quantity": 1,
                "unit_measure": "unit",
                "total_amount": monto_f,
            }],
        }
        self._log(f"🤳 Creando orden QR por ${monto_f:.2f}...", cb)
        try:
            resp = requests.put(url, headers=self._headers(token), json=payload, timeout=settings.mp_timeout_seg)
        except requests.RequestException as e:
            self._log(f"❌ Error de red creando orden: {e}", cb)
            return False
        if resp.status_code == 204:
            self._log("✅ Orden creada. Esperando pago del cliente...", cb)
            return True
        self._log(f"❌ Error creando orden ({resp.status_code}): {resp.text[:300]}", cb)
        return False

    def verificar_estado(self, cb: Optional[Callable[[str], None]] = None,
                         cancelar: Optional[Callable[[], bool]] = None,
                         pos_ext: str = "", timeout: int = 0, intervalo: int = 0) -> bool:
        from core.settings import settings

        token, uid, _, pos_d = self.credenciales()
        pos_ext = pos_ext or pos_d
        timeout = timeout or settings.mp_poll_timeout_seg
        intervalo = intervalo or settings.mp_poll_interval_seg
        if not token or not pos_ext:
            self._log("❌ Sin credenciales para verificar pago.", cb)
            return False
        url = f"{MP_BASE}/instore/qr/seller/collectors/{uid}/pos/{pos_ext}/orders"
        inicio = time.time()
        self._log(f"💳 Esperando pago del QR {pos_ext}...", cb)
        while (time.time() - inicio) < timeout:
            if cancelar and cancelar():
                self._log("❌ Pago cancelado por el usuario.", cb)
                return False
            try:
                resp = requests.get(url, headers=self._headers(token), timeout=settings.mp_timeout_seg)
            except requests.RequestException as e:
                self._log(f"⚠️ Error de red: {e}", cb)
                time.sleep(intervalo)
                continue
            if resp.status_code == 200:
                try:
                    data = resp.json()
                except Exception:
                    time.sleep(intervalo)
                    continue
                estado = data.get("order_status", "unknown")
                pagado = float(data.get("paid_amount") or 0)
                total = float(data.get("total_amount") or 0)
                if estado == "paid" or (total > 0 and pagado >= total):
                    self._log("✅ ¡Pago recibido correctamente!", cb)
                    for p in data.get("payments", [])[:1]:
                        self._log(f"💳 Payment ID: {p.get('id')} | Estado: {p.get('status')}", cb)
                    return True
            elif resp.status_code == 404:
                self._log("📭 Orden cerrada. Verificando último pago...", cb)
                return self.consultar_ultimo_pago(cb)
            elif resp.status_code >= 400:
                self._log(f"⚠️ MP {resp.status_code}: {resp.text[:200]}", cb)
            time.sleep(intervalo)
        self._log("⏰ Tiempo agotado. Orden sigue abierta.", cb)
        return False

    def cancelar_orden(self) -> bool:
        """Solicita a Mercado Pago cerrar la orden QR activa, si la API lo permite."""
        token, uid, store_ext, pos_ext = self.credenciales()
        if not (token and uid and store_ext and pos_ext):
            return False
        from core.settings import settings
        url = f"{MP_BASE}/instore/qr/seller/collectors/{uid}/stores/{store_ext}/pos/{pos_ext}/orders"
        try:
            resp = requests.delete(url, headers=self._headers(token), timeout=settings.mp_timeout_seg)
            if resp.status_code in (200, 202, 204, 404):
                return True
            self._log(f"⚠️ No se pudo cerrar la orden QR ({resp.status_code}): {resp.text[:200]}")
            return False
        except requests.RequestException as exc:
            self._log(f"⚠️ Error de red al cerrar la orden QR: {exc}")
            return False

    def consultar_ultimo_pago(self, cb: Optional[Callable[[str], None]] = None) -> bool:
        token, _, _, _ = self.credenciales()
        if not self._ultima_referencia:
            self._log("⚠️ Sin referencia para buscar pago.", cb)
            return False
        from core.settings import settings

        url = f"{MP_BASE}/v1/payments/search"
        try:
            resp = requests.get(url, headers=self._headers(token),
                                params={"external_reference": self._ultima_referencia},
                                timeout=settings.mp_timeout_seg)
        except requests.RequestException as e:
            self._log(f"⚠️ Error consultando pagos: {e}", cb)
            return False
        if resp.status_code == 200:
            try:
                results = resp.json().get("results", [])
            except Exception:
                return False
            if results:
                pago = results[0]
                self._log(f"💰 Pago: ID={pago.get('id')} Estado={pago.get('status')} Monto=${pago.get('transaction_amount')}", cb)
                return pago.get("status") == "approved"
            self._log("⚠️ Sin pagos con esa referencia.", cb)
        else:
            self._log(f"⚠️ Error {resp.status_code}: {resp.text[:200]}", cb)
        return False

    # ---------- store / pos ----------
    def sincronizar_store_id(self) -> Optional[str]:
        """Resuelve STORE_ID numérico desde EXTERNAL_STORE_ID y lo guarda."""
        from core.settings import settings

        token, uid, store_ext, _ = self.credenciales()
        if not (token and uid and store_ext):
            return None
        try:
            resp = requests.get(f"{MP_BASE}/users/{uid}/stores",
                                headers=self._headers(token), timeout=settings.mp_timeout_seg)
        except requests.RequestException as e:
            logger.warning("sync store: %s", e)
            return None
        if resp.status_code != 200:
            return None
        for s in resp.json().get("results", []):
            if s.get("external_id") == store_ext and s.get("id"):
                db = self._db_or_none()
                if db:
                    db.set_config("STORE_ID", str(s["id"]))
                return str(s["id"])
        return None

    def listar_pos(self) -> list:
        from core.settings import settings

        token, _, _, _ = self.credenciales()
        try:
            resp = requests.get(f"{MP_BASE}/pos", headers=self._headers(token), timeout=settings.mp_timeout_seg)
        except requests.RequestException as e:
            logger.warning("listar_pos: %s", e)
            return []
        if resp.status_code != 200:
            return []
        return resp.json().get("results", [])

    def crear_store_y_pos(self, nombre_negocio: str) -> tuple[str, str, str, str]:
        """Crea Store + POS fixed_amount. Retorna (store_ext, pos_ext, qr_url, error)."""
        from core.settings import settings

        token, uid, _, _ = self.credenciales()
        if not token or not uid:
            return "", "", "", "Faltan MP_ACCESS_TOKEN / MP_USER_ID en .env"
        headers = self._headers(token)
        ts = int(time.time())
        try:
            r = requests.post(f"{MP_BASE}/users/{uid}/stores", headers=headers, json={
                "name": nombre_negocio or "Mi Local",
                "external_id": f"STORE{ts}",
                "location": {"street_number": "123", "street_name": "Principal",
                             "city_name": "Rosario", "state_name": "Santa Fe",
                             "latitude": -32.9468, "longitude": -60.6393,
                             "reference": "Local comercial"},
            }, timeout=settings.mp_timeout_seg)
            if r.status_code not in (200, 201):
                return "", "", "", f"Error creando Store: {r.text[:300]}"
            store_ext = r.json().get("external_id", "")
            store_id = r.json().get("id")
            r2 = requests.post(f"{MP_BASE}/pos", headers=headers, json={
                "name": "Caja Principal", "external_id": f"POS{ts}",
                "store_id": store_id, "fixed_amount": True, "category": 621102,
            }, timeout=settings.mp_timeout_seg)
            if r2.status_code not in (200, 201):
                return "", "", "", f"Error creando POS: {r2.text[:300]}"
            pos_ext = r2.json().get("external_id", "")
            qr_url = (r2.json().get("qr") or {}).get("image", "")
            db = self._db_or_none()
            if db:
                db.set_config("EXTERNAL_STORE_ID", store_ext)
                db.set_config("EXTERNAL_POS_ID", pos_ext)
                if qr_url:
                    db.set_config("QR_URL", qr_url)
            return store_ext, pos_ext, qr_url, ""
        except requests.RequestException as e:
            return "", "", "", f"Error de red: {e}"

    def crear_pos_adicional(self, nombre: str = "POS Adicional") -> tuple[str, str, str]:
        """Crea un POS fixed_amount adicional en el Store existente (STORE_ID).

        Retorna (pos_ext, qr_url, error).
        """
        from core.settings import settings

        token, uid, _, _ = self.credenciales()
        db = self._db_or_none()
        store_id = db.get_config_value("STORE_ID") if db else None
        if not token or not uid or not store_id:
            return "", "", "Faltan credenciales o STORE_ID (cree la tienda primero)"
        ts = int(time.time())
        try:
            r = requests.post(f"{MP_BASE}/pos", headers=self._headers(token), json={
                "name": nombre or "POS Adicional", "external_id": f"POS{ts}",
                "store_id": store_id, "fixed_amount": True, "category": 621102,
            }, timeout=settings.mp_timeout_seg)
        except requests.RequestException as e:
            return "", "", f"Error de red: {e}"
        if r.status_code not in (200, 201):
            return "", "", f"Error creando POS: {r.text[:300]}"
        pos_ext = r.json().get("external_id", "")
        qr_url = (r.json().get("qr") or {}).get("image", "")
        if db:
            db.set_config("EXTERNAL_POS_ID", pos_ext)
            if qr_url:
                db.set_config("QR_URL", qr_url)
        return pos_ext, qr_url, ""

    def descargar_qr(self, destino: str | Path = "img/qr.png") -> tuple[bool, str]:
        from core.settings import settings

        qr_url = settings.mp_qr_url
        db = self._db_or_none()
        if not qr_url and db:
            qr_url = db.get_config_value("QR_URL") or ""
        if not qr_url:
            return False, "Sin QR_URL configurada"
        try:
            r = requests.get(qr_url, timeout=settings.mp_timeout_seg)
            if r.status_code != 200:
                return False, f"HTTP {r.status_code}"
            p = Path(destino)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(r.content)
            return True, str(p)
        except Exception as e:  # noqa: BLE001
            return False, str(e)

    # ---------- util ----------
    @staticmethod
    def _log(msg: str, cb) -> None:
        if cb:
            try:
                cb(msg)
                return
            except Exception:
                pass
        logger.info(msg)


mp_service = MercadoPagoService()

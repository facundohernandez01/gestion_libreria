"""Cliente HTTP para modo multi-usuario (cliente).

Implementa la misma interfaz pública mínima que DatabaseManager para que la app
pueda funcionar indistintamente en modo local o cliente.
"""
from __future__ import annotations

import os
from typing import Any, Optional

import httpx


class ApiClient:
    def __init__(self, base_url: str, api_key: str = "libreria-lan"):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._headers = {"X-API-Key": api_key}

    def _get(self, path, params=None):
        r = httpx.get(self.base_url + path, params=params, headers=self._headers, timeout=15)
        r.raise_for_status()
        return r.json()

    def _post(self, path, json=None, params=None):
        r = httpx.post(self.base_url + path, json=json, params=params, headers=self._headers, timeout=15)
        r.raise_for_status()
        return r.json()

    def autenticar_usuario(self, usuario: str, clave: str):
        try:
            response = httpx.post(self.base_url + "/pos/auth/login",
                json={"usuario": usuario, "clave": clave}, timeout=8)
            if response.status_code != 200:
                return None
            data = response.json()
            from adapters.entregas import set_session
            set_session(data["access_token"])
            return {"usuario": data["usuario"], "nombre": data["usuario"],
                    "rol": "OPERADOR", "es_admin": False,
                    "permisos": data.get("permisos", {}), "activo": True}
        except Exception:
            return None

    def health(self) -> bool:
        try:
            return httpx.get(self.base_url + "/health", timeout=5).status_code == 200
        except Exception:
            return False

    def get_config_value(self, clave: str) -> Optional[str]:
        try:
            data = self._get("/config")
            return data.get(clave)
        except Exception:
            return None

    def set_config(self, clave: str, valor: str) -> None:
        try:
            self._post("/config", json={"clave": clave, "valor": valor})
        except Exception:
            pass

    def get_all_config(self) -> dict:
        try:
            return self._get("/config")
        except Exception:
            return {}

    def buscar_productos(self, termino: str = "", campo: str = "descripcion", limit: int = 200):
        return self._get("/productos", params={"termino": termino, "campo": campo})[:limit]

    def obtener_caja_abierta(self):
        return self._get("/cajas/abierta")

    def abrir_caja(self, importe_apertura: float = 0.0, observaciones: str = ""):
        return self._post("/cajas/abrir", params={"importe_apertura": importe_apertura, "observaciones": observaciones})["id"]

    def cerrar_caja(self, caja_id: int, observaciones: str = ""):
        return self._post(f"/cajas/{caja_id}/cerrar", params={"observaciones": observaciones})

    def crear_venta(self, caja_id, items, metodo_pago="efectivo", comprobante=""):
        r = self._post("/ventas", json={
            "caja_id": caja_id, "items": items,
            "metodo_pago": metodo_pago, "comprobante": comprobante,
        })
        return r["venta_id"], True

    def obtener_ventas_del_dia(self, caja_id: int):
        return self._get(f"/ventas/dia/{caja_id}")

    def obtener_items_venta(self, venta_id: int):
        return self._get(f"/ventas/{venta_id}/items")

    def actualizar_factura_venta(self, venta_id, numero_factura, cae, vencimiento_cae):
        try:
            self._post("/ventas/factura", json={
                "venta_id": venta_id, "numero_factura": str(numero_factura),
                "cae": str(cae), "vencimiento_cae": str(vencimiento_cae),
            })
            return True
        except Exception:
            return False

    def obtener_productos_bajo_stock(self):
        return self._get("/productos/bajo_stock")

    def obtener_top_productos(self, desde_iso: str, hasta_iso: str, limit: int = 10):
        return self._get("/reportes/top_productos",
                         params={"desde": desde_iso, "hasta": hasta_iso, "limit": limit})

    def obtener_ventas_por_dia(self, desde_iso: str, hasta_iso: str):
        return self._get("/reportes/ventas_por_dia",
                         params={"desde": desde_iso, "hasta": hasta_iso})

    # compat con código que espera atributos
    @property
    def db_path(self):
        return self.base_url

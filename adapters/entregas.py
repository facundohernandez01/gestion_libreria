"""Adapter de comandas para POS local y terminales cliente LAN.

Todo acceso a entregas se realiza por la API del servidor: no se abren
archivos SQLite en los clientes. El contrato es independiente del motor SQL.
"""
import httpx
from core.settings import settings


class EntregasAdapter:
    def __init__(self, base_url=None, api_key=None, timeout=8):
        self.base_url = (base_url or settings.server_url).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.api_key
        self.timeout = timeout

    def _request(self, method, path, **kwargs):
        response = httpx.request(
            method, self.base_url + "/tienda/admin/entregas" + path,
            headers={"X-API-Key": self.api_key},
            timeout=self.timeout, **kwargs,
        )
        response.raise_for_status()
        return response.json()

    def listar(self, estado=""):
        return self._request("GET", "", params={"estado": estado})

    def cambiar(self, entrega_id, estado, operador):
        return self._request("PATCH", f"/{int(entrega_id)}",
                             json={"estado": estado, "operador": operador})

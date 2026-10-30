"""Adapter de comandas para POS local y terminales cliente LAN.

Todo acceso a entregas se realiza por la API del servidor: no se abren
archivos SQLite en los clientes. El contrato es independiente del motor SQL.
"""
import httpx
from core.settings import settings


class EntregasAdapter:
    def __init__(self, base_url=None, api_key=None, timeout=8):
        from core.db_factory import modo_actual, _server_url
        modo = modo_actual()
        if base_url:
            url = base_url
        elif modo == "cliente":
            url = _server_url()
        else:
            url = "http://127.0.0.1:" + str(settings.api_port)
        self.base_url = url.rstrip("/")
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

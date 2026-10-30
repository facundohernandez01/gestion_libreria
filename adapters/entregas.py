"""Adapter de comandas para POS local y terminales cliente LAN.

Todo acceso a entregas se realiza por la API del servidor: no se abren
archivos SQLite en los clientes. El contrato es independiente del motor SQL.
"""
import httpx
from core.settings import settings


_session_token = None


def set_session(token):
    global _session_token
    _session_token = token


class EntregasAdapter:
    def __init__(self, base_url=None, api_key=None, timeout=8):
        from core.db_factory import modo_actual, _server_url
        modo = modo_actual()
        self.modo = modo
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
        from core.terminal_identity import terminal_id
        response = httpx.request(
            method, self.base_url + "/tienda/admin/entregas" + path,
            headers={"Authorization": "Bearer " + (_session_token or ""), "X-Terminal-Id": terminal_id()},
            timeout=self.timeout, **kwargs,
        )
        response.raise_for_status()
        return response.json()

    def totems(self):
        if self.modo == "local":
            from intrashop_entregas import list_totems
            return list_totems(operador="POS local")
        return self._request("GET", "/totems")

    def listar(self, estado=""):
        if self.modo == "local":
            from intrashop_entregas import list_orders
            return list_orders(estado=estado, operador="POS local")
        return self._request("GET", "", params={"estado": estado})

    def tomar(self, entrega_id, operador):
        if self.modo == "local":
            from intrashop_entregas import tomar_comanda
            return tomar_comanda(int(entrega_id), operador=operador, x_terminal_id=__import__("core.terminal_identity", fromlist=["terminal_id"]).terminal_id())
        return self._request("POST", f"/{int(entrega_id)}/tomar")

    def liberar(self, entrega_id, operador):
        if self.modo == "local":
            from intrashop_entregas import liberar_comanda
            return liberar_comanda(int(entrega_id), operador=operador, x_terminal_id=__import__("core.terminal_identity", fromlist=["terminal_id"]).terminal_id())
        return self._request("POST", f"/{int(entrega_id)}/liberar")

    def cambiar(self, entrega_id, estado, operador):
        if self.modo == "local":
            from intrashop_entregas import update_order, EntregaUpdate
            return update_order(int(entrega_id), EntregaUpdate(estado=estado, operador=operador), operador=operador, x_terminal_id=__import__("core.terminal_identity", fromlist=["terminal_id"]).terminal_id())
        return self._request("PATCH", f"/{int(entrega_id)}",
                             json={"estado": estado, "operador": operador})

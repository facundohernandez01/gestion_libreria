"""Sesión de operador POS: una sola emisión de bearer por login cliente.

ApiClient.autenticar_usuario() ya realiza /pos/auth/login enviando
X-Terminal-Id, y conserva el token. La UI no debe solicitar una segunda
sesión sin identidad de terminal, pues invalida el acceso a su propia caja.
"""
from __future__ import annotations


def preparar_sesion_operador(modo: str, usuario: str, clave: str,
                             api_port: int | None = None) -> bool:
    from adapters.entregas import set_session
    from adapters import entregas

    if modo == "cliente":
        # No lanzar una segunda petición: ApiClient ya autenticó el usuario
        # con X-Terminal-Id y almacenó el bearer que pertenece a ese equipo.
        return bool(entregas._session_token)

    # POS local clásico: la sesión HTTP se usa para entregas, pero no debe
    # impedir que la GUI local funcione cuando no hay un servidor iniciado.
    if api_port is None:
        from core.settings import settings
        api_port = settings.api_port
    try:
        import httpx
        from core.terminal_identity import terminal_id
        response = httpx.post(
            f"http://127.0.0.1:{api_port}/pos/auth/login",
            json={"usuario": usuario, "clave": clave},
            headers={"X-Terminal-Id": terminal_id()},
            timeout=4,
        )
        if response.status_code == 200:
            set_session(response.json()["access_token"])
        else:
            set_session(None)
    except Exception:
        set_session(None)
    return True

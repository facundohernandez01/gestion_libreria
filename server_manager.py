"""Gestor del servidor FastAPI (modo multi-usuario LAN).

Inicia uvicorn en un hilo/worker propio y expone la URL LAN para compartir.
"""
from __future__ import annotations

import socket
import sys
import threading
import time

import uvicorn

# Imports explícitos: PyInstaller no detecta los módulos que uvicorn carga
# dinámicamente (protocolos/loops/lifespan) en la app compilada.
try:  # noqa: SIM105
    import uvicorn.lifespan.on  # noqa: F401
    import uvicorn.loops.auto  # noqa: F401
    import uvicorn.loops.asyncio  # noqa: F401
    import uvicorn.protocols.http.auto  # noqa: F401
    import uvicorn.protocols.http.h11_impl  # noqa: F401
    import uvicorn.protocols.websockets.auto  # noqa: F401
except Exception:
    pass

# En .exe sin consola (o servicio) sys.stderr puede ser None: desactivar el
# dictConfig de uvicorn para evitar errores de logging.
_HEADLESS = getattr(sys, "frozen", False) or "--service" in sys.argv
_LOG_CONFIG = None if _HEADLESS else uvicorn.config.LOGGING_CONFIG


def ip_lan() -> str:
    """IP LAN de esta máquina (fallback 127.0.0.1)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class ServerManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._server = None
            cls._instance._thread = None
            cls._instance.activo = False
            cls._instance.host = "0.0.0.0"
            cls._instance.port = 8000
        return cls._instance

    def _crear_server(self, host: str, port: int):
        # Importar el objeto ASGI (no el string "api_server:app"): PyInstaller
        # no resuelve imports por string en modo congelado.
        from api_server import app as asgi_app

        config = uvicorn.Config(
            asgi_app, host=host, port=port, log_level="warning",
            reload=False, log_config=_LOG_CONFIG,
        )
        return uvicorn.Server(config)

    def iniciar(self, host: str = "0.0.0.0", port: int = 8000) -> str:
        if self.activo and getattr(self._server, "started", False):
            return self.url()
        self.host, self.port = host, port
        self._server = self._crear_server(host, port)
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()
        # esperar a que levante
        for _ in range(80):
            time.sleep(0.1)
            if getattr(self._server, "started", False):
                break
        if not getattr(self._server, "started", False):
            self.activo = False
            raise RuntimeError(
                f"No se pudo iniciar el servidor en {host}:{port} "
                "(¿puerto ocupado o sin permisos?)"
            )
        self.activo = True
        return self.url()

    def detener(self) -> None:
        server = self._server
        if server is not None:
            server.should_exit = True
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=8)
        self._server = None
        self._thread = None
        self.activo = False

    def url(self) -> str:
        return f"http://{ip_lan()}:{self.port}"

    def url_local(self) -> str:
        return f"http://127.0.0.1:{self.port}"


server_manager = ServerManager()

_bloqueante_server = None


def servir_bloqueante(host: str = "0.0.0.0", port: int = 8000, stop_event=None) -> None:
    """Ejecuta uvicorn bloqueando el hilo actual (para el servicio Windows).

    `stop_event` (threading.Event) permite pedir el apagado ordenado.
    """
    global _bloqueante_server

    from api_server import app as asgi_app

    config = uvicorn.Config(
        asgi_app, host=host, port=port, log_level="warning",
        reload=False, log_config=_LOG_CONFIG,
    )
    server = uvicorn.Server(config)
    _bloqueante_server = server

    if stop_event is not None:
        def _vigilar():
            while not stop_event.is_set():
                stop_event.wait(0.3)
            server.should_exit = True

        threading.Thread(target=_vigilar, daemon=True).start()

    try:
        server.run()
    finally:
        _bloqueante_server = None


def detener_bloqueante() -> None:
    global _bloqueante_server
    if _bloqueante_server is not None:
        _bloqueante_server.should_exit = True


def escanear_servidor(subred: str | None = None, puerto: int = 8000, timeout: float = 0.3) -> list[str]:
    """Escanea la subred LAN buscando un servidor con /health OK."""
    import socket as _socket

    ip = subred or ip_lan()
    base = ".".join(ip.split(".")[:3])
    encontrados: list[str] = []

    def _check(host: str):
        try:
            s = _socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            if s.connect_ex((host, puerto)) == 0:
                try:
                    import httpx

                    r = httpx.get(f"http://{host}:{puerto}/health", timeout=timeout)
                    if r.status_code == 200:
                        encontrados.append(f"http://{host}:{puerto}")
                except Exception:
                    encontrados.append(f"http://{host}:{puerto}")
            s.close()
        except Exception:
            pass

    hilos = []
    for i in range(1, 255):
        t = threading.Thread(target=_check, args=(f"{base}.{i}",), daemon=True)
        t.start()
        hilos.append(t)
    for t in hilos:
        t.join(timeout=timeout + 0.5)
    return encontrados

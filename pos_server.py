"""Servidor POS autónomo: GUI por defecto, CLI con --headless/--service."""
import argparse
import logging
import os

from core.settings import settings
from services.lan_https import host_backend, opciones_uvicorn, puerto_backend


def main() -> None:
    parser = argparse.ArgumentParser(description="Servidor POS independiente")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=settings.api_port)
    parser.add_argument("--headless", "--service", action="store_true",
                        help="Ejecutar sin interfaz gráfica (servicio/terminal)")
    args = parser.parse_args()
    os.environ["POS_API_ONLY"] = "1"
    logging.basicConfig(level=getattr(logging, settings.log_level, logging.INFO))
    # En HTTPS solo Caddy recibe conexiones LAN. Se ignora --host 0.0.0.0
    # para evitar que se exponga accidentalmente el backend por HTTP.
    backend_host = host_backend(args.host)
    if not args.headless:
        from pos_server_gui import ServerConsole
        ServerConsole(host=backend_host, port=args.port).run()
        return
    import uvicorn
    from api_server import app
    uvicorn.run(app, host=backend_host, port=puerto_backend(args.port), log_level="info",
                **opciones_uvicorn())


if __name__ == "__main__":
    main()

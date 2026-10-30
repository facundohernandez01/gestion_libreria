"""Ejecuta la API LAN sin iniciar la interfaz Flet del POS.

Uso: python pos_server.py
     python pos_server.py --host 0.0.0.0 --port 8000

Para instalarlo como servicio se recomienda usar systemd (Linux)
o el Administrador de servicios de Windows con un wrapper como NSSM.
"""
import argparse
import logging

from core.settings import settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Servidor API independiente del POS")
    parser.add_argument("--host", default=settings.api_host)
    parser.add_argument("--port", type=int, default=settings.api_port)
    args = parser.parse_args()
    logging.basicConfig(level=getattr(logging, settings.log_level, logging.INFO))
    import uvicorn
    uvicorn.run("api_server:app", host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()

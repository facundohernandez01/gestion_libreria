"""Servidor POS autónomo: GUI por defecto, CLI con --headless/--service."""
import argparse
import logging
import os

from core.settings import settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Servidor POS independiente")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=settings.api_port)
    parser.add_argument("--headless", "--service", action="store_true",
                        help="Ejecutar sin interfaz gráfica (servicio/terminal)")
    args = parser.parse_args()
    os.environ["POS_API_ONLY"] = "1"
    logging.basicConfig(level=getattr(logging, settings.log_level, logging.INFO))
    if not args.headless:
        from pos_server_gui import ServerConsole
        ServerConsole(host=args.host, port=args.port).run()
        return
    import uvicorn
    from api_server import app
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()

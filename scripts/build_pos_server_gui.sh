#!/usr/bin/env bash
set -euo pipefail
# Compilar desde el entorno Python del proyecto, en el sistema operativo destino.
python -m PyInstaller --noconfirm --clean --onefile --windowed \
  --name IntraShopServer \
  --hidden-import api_server \
  --hidden-import intrashop_api \
  --hidden-import intrashop_entregas \
  --hidden-import pos_auth \
  --hidden-import uvicorn.protocols.http.h11_impl \
  --hidden-import uvicorn.lifespan.on \
  pos_server_gui.py
echo "Binario generado en dist/IntraShopServer (Linux) o dist/IntraShopServer.exe (Windows)"

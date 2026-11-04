# -*- mode: python ; coding: utf-8 -*-
# Ejecutar desde la raíz del repositorio: pyinstaller --noconfirm intrashop-server/backend/pos_server.spec
from pathlib import Path
root = Path(SPECPATH).resolve().parents[1]
dist = root / "intrashop" / "dist"
datas = [(str(dist), "intrashop/dist")] if (dist / "index.html").is_file() else []
a = Analysis(
    [str(root / "pos_server.py")],
    pathex=[str(root)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "uvicorn.loops.auto",
        "uvicorn.loops.asyncio",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.lifespan.on",
    ],
    excludes=["flet", "flet_web", "pandas", "openpyxl", "matplotlib", "tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="pos_server", console=True)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="pos_server")

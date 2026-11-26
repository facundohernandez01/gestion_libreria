"""Build from a clean, allowlisted staging tree; never package live business data."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MODULE_DIRS = ("core", "services", "adapters", "utils", "components", "models", "repositories")
ASSET_DIRS = ("assets", "img")
BLOCKED_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".pem", ".key", ".p12", ".pfx", ".crt", ".cer", ".env", ".zip", ".bak"}
ASSET_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".ico", ".svg", ".gif", ".ttf", ".otf", ".wav", ".mp3"}
def run(*args, cwd):
    subprocess.run(args, cwd=cwd, check=True)
def copy_modules(stage):
    for path in ROOT.glob("*.py"):
        if not path.name.startswith(("test_", "build_", "conftest")):
            shutil.copy2(path, stage / path.name)
    for name in MODULE_DIRS:
        source = ROOT / name
        if not source.is_dir():
            continue
        for path in source.rglob("*.py"):
            if path.is_symlink() or any(x.startswith(".") or x in ("tests", "__pycache__") for x in path.relative_to(source).parts):
                continue
            target = stage / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    for name in ASSET_DIRS:
        source = ROOT / name
        if not source.is_dir():
            continue
        for path in source.rglob("*"):
            if path.is_file() and not path.is_symlink() and path.suffix.lower() in ASSET_SUFFIXES:
                target = stage / path.relative_to(ROOT)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
    shutil.copy2(ROOT / "requirements.txt", stage / "requirements.txt")

def zip_tree(source, destination):
    files = [p for p in source.rglob("*") if p.is_file()]
    if not files:
        raise RuntimeError("Empty build")
    for path in files:
        if path.suffix.lower() in BLOCKED_SUFFIXES or path.name.lower() in {
            "licencia.json", "login_recordado.json", "sesiones_web.json", "device_id.txt", "client_api_key",
        }:
            # PyInstaller may include dependency public CA bundles; these are
            # not merchant certificates. Fail closed until explicitly reviewed.
            if path.name == "cacert.pem" and "certifi" in path.parts:
                continue
            raise RuntimeError(f"Unexpected sensitive file in distribution: {path.name}")
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as out:
        for path in files:
            out.write(path, path.relative_to(source))

def build(role, output, platform):
    with tempfile.TemporaryDirectory(prefix="intrashop-build-") as tmp:
        stage = Path(tmp)
        copy_modules(stage)
        if role == "pos":
            target = "windows" if platform == "windows" else "linux"
            cli = shutil.which("flet")
            if not cli:
                raise RuntimeError("Flet CLI no instalado")
            run(cli, "build", target,
                "--product-name", "Kiosmico", "--org", "com.facundohernandez",
                "--output-dir", "out", "--module-name", "main", cwd=stage)
            zip_tree(stage / "out", output / f"Kiosmico-{platform}-portable.zip")
        else:
            storefront = ROOT / "intrashop" / "dist"
            if not (storefront / "index.html").is_file():
                raise RuntimeError("Build Astro first")
            shutil.copytree(storefront, stage / "intrashop" / "dist")
            # Bundle the static storefront, not the source repository.
            data = [("intrashop/dist", "intrashop/dist")]
            for name in ASSET_DIRS:
                if (stage / name).is_dir():
                    data.append((name, name))
            args = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                    "--onedir", "--name", "IntraShopServer",
                    "--collect-submodules", "uvicorn", "--collect-submodules", "services",
                    "--collect-submodules", "core", "--collect-submodules", "adapters"]
            if platform == "windows":
                args.append("--windowed")
            for source, dest in data:
                args += ["--add-data", f"{source}{os.pathsep}{dest}"]
            run(*args, "pos_server.py", cwd=stage)
            zip_tree(stage / "dist" / "IntraShopServer", output / f"IntraShopServer-{platform}-portable.zip")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("role", choices=["pos", "servidor"])
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--platform", required=True, choices=["windows", "linux"])
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    build(args.role, output, args.platform)

if __name__ == "__main__":
    main()

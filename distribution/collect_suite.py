"""Collect only known build outputs into the directory consumed by the wizard."""
import hashlib
import json
from pathlib import Path
import shutil
import sys

def collect(source, destination):
    destination.mkdir(parents=True, exist_ok=True)
    records = []
    required = {(role, os) for role in ("pos", "servidor", "totem") for os in ("windows", "linux")}
    seen = set()
    for group in source.iterdir():
        if not group.is_dir() or not group.name.startswith("suite-"):
            continue
        role = group.name.split("-")[1]
        os_name = "windows" if "windows" in group.name else "linux"
        if (role, os_name) not in required:
            continue
        for path in group.rglob("*"):
            if not path.is_file() or path.is_symlink():
                continue
            if role == "totem":
                if path.suffix.lower() not in (".exe", ".msi", ".deb", ".appimage"):
                    continue
                name = "IntraShop-" + os_name + "-" + path.name
            else:
                prefix = "Kiosmico-" if role == "pos" else "IntraShopServer-"
                if not path.name.startswith(prefix) or path.suffix != ".zip":
                    continue
                name = path.name
            target = destination / name
            if target.exists():
                raise RuntimeError(f"Duplicate artifact: {name}")
            shutil.copy2(path, target)
            with target.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            records.append({"file": name, "role": role, "platform": os_name, "sha256": digest, "bytes": target.stat().st_size})
            seen.add((role, os_name))
    if seen != required:
        raise RuntimeError(f"Missing builds: {sorted(required-seen)}")
    (destination / "manifest.json").write_text(json.dumps({"schema":"intrashop-suite/v1","artifacts":records}, indent=2), encoding="utf-8")

if __name__ == "__main__":
    collect(Path(sys.argv[1]), Path(sys.argv[2]))

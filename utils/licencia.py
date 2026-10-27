"""Gestión de licencias del software (activación limitada por dispositivo)."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import platform
import subprocess
import time
import uuid
from pathlib import Path

import requests

from utils.paths import base_dir

_API = "https://v0-plugin-marketplace-api.vercel.app"
_ARCHIVO_ESTADO = base_dir() / "licencia.json"
_ARCHIVO_DEVICE = base_dir() / "device_id.txt"
_ARCHIVO_DEMO_LOCK = base_dir() / ".demo_lock"
_TIMEOUT = 15
_DEMO_DIAS = 30
# Clave para firmar el demo local (ofuscada; no es seguridad absoluta).
_DEMO_SECRETO = "kms-demo-2026-" + "x9Qp#mZ!vR" + "-lic"


def _leer_archivo(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _escribir_archivo(path: Path, valor: str) -> None:
    try:
        path.write_text(valor, encoding="utf-8")
    except Exception:
        pass


def _machine_guid_windows() -> str:
    if os.name != "nt":
        return ""
    try:
        out = subprocess.run(
            ["reg", "query", r"HKLM\SOFTWARE\Microsoft\Cryptography",
             "/v", "MachineGuid"],
            capture_output=True, text=True, errors="replace",
            creationflags=0x08000000,
        )
        for line in (out.stdout or "").splitlines():
            if "MachineGuid" in line:
                parts = line.split()
                if parts:
                    return parts[-1].strip()
    except Exception:
        pass
    return ""


def _machine_id_linux() -> str:
    for ruta in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        val = _leer_archivo(Path(ruta))
        if val:
            return val
    return ""


def _disk_serial() -> str:
    try:
        if os.name == "nt":
            out = subprocess.run(
                ["wmic", "diskdrive", "get", "serialnumber"],
                capture_output=True, text=True, errors="replace",
                creationflags=0x08000000,
            )
            lines = [l.strip() for l in (out.stdout or "").splitlines() if l.strip()]
            if len(lines) > 1:
                return lines[1]
        else:
            # Best-effort: primera línea no vacía de lsblk
            out = subprocess.run(
                ["lsblk", "-ndo", "SERIAL"], capture_output=True, text=True, errors="replace")
            for line in (out.stdout or "").splitlines():
                if line.strip():
                    return line.strip()
    except Exception:
        pass
    return ""


def _fingerprint_hardware() -> str:
    partes = [
        platform.system(),
        platform.node(),
        str(uuid.getnode()),
        _machine_guid_windows(),
        _machine_id_linux(),
        _disk_serial(),
        platform.processor(),
        platform.machine(),
    ]
    raw = "|".join(p for p in partes if p)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def obtener_device_id() -> str:
    existente = _leer_archivo(_ARCHIVO_DEVICE)
    if existente:
        return existente
    did = _fingerprint_hardware()
    _escribir_archivo(_ARCHIVO_DEVICE, did)
    return did


def cargar_estado() -> dict:
    try:
        return json.loads(_ARCHIVO_ESTADO.read_text(encoding="utf-8"))
    except Exception:
        return {}


def guardar_estado(data: dict) -> None:
    try:
        _ARCHIVO_ESTADO.write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        pass


def borrar_estado() -> None:
    try:
        _ARCHIVO_ESTADO.unlink()
    except Exception:
        pass


def _firmar_demo(device_id: str, expira: float) -> str:
    msg = f"{device_id}|{expira:.0f}".encode("utf-8")
    return hmac.new(_DEMO_SECRETO.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def demo_usado() -> bool:
    # Lock file o estado previo marcan demo ya utilizado.
    if _ARCHIVO_DEMO_LOCK.exists():
        return True
    st = cargar_estado()
    return bool(st.get("demo_usado"))


def demo_disponible() -> bool:
    return not demo_usado()


def demo_valido() -> bool:
    st = cargar_estado()
    if st.get("mode") != "demo":
        return False
    if st.get("device_id") != obtener_device_id():
        return False
    try:
        expira = float(st.get("demo_expira", 0))
    except (TypeError, ValueError):
        return False
    if time.time() >= expira:
        return False
    sig = st.get("demo_sig", "")
    if not hmac.compare_digest(sig, _firmar_demo(st["device_id"], expira)):
        return False
    return True


def activar_demo() -> tuple[bool, str]:
    if demo_usado():
        # Si hay demo previo expirado, no permitir reactivar.
        if demo_valido():
            return True, "Demo ya activo"
        return False, "El período de demo ya fue utilizado en este equipo"
    device_id = obtener_device_id()
    expira = time.time() + _DEMO_DIAS * 86400
    sig = _firmar_demo(device_id, expira)
    guardar_estado({
        "mode": "demo",
        "device_id": device_id,
        "demo_usado": True,
        "demo_expira": expira,
        "demo_sig": sig,
        "activated": True,
    })
    try:
        _ARCHIVO_DEMO_LOCK.write_text(sig, encoding="utf-8")
    except Exception:
        pass
    return True, f"Demo activado por {_DEMO_DIAS} días"


def esta_activada_local() -> bool:
    st = cargar_estado()
    if st.get("activated") and st.get("license_key"):
        return True
    return demo_valido()


def activar_licencia(license_key: str) -> tuple[bool, str, dict]:
    license_key = (license_key or "").strip()
    if not license_key:
        return False, "Ingresá una license_key", {}
    device_id = obtener_device_id()
    url = f"{_API}/api/licenses/activate"
    try:
        r = requests.post(url, json={"license_key": license_key,
                                     "device_id": device_id},
                          timeout=_TIMEOUT)
    except requests.RequestException as ex:
        return False, f"Error de red: {ex}", {}
    try:
        data = r.json()
    except Exception:
        data = {}
    if r.status_code == 200 and data.get("success"):
        info = data.get("data") or {}
        guardar_estado({
            "license_key": license_key,
            "device_id": device_id,
            "activated": True,
            "activations_count": info.get("activations_count"),
            "max_activations": info.get("max_activations"),
            "remaining": info.get("remaining"),
            "message": info.get("message"),
        })
        return True, info.get("message", "Activación exitosa"), info
    error = data.get("error") or data.get("message") or f"Error HTTP {r.status_code}"
    return False, str(error), data


def verificar_licencia(license_key: str | None = None) -> tuple[bool | None, str, dict]:
    """Devuelve (valid, mensaje, data). valid=None indica error de red."""
    lk = (license_key or cargar_estado().get("license_key") or "").strip()
    if not lk:
        return False, "Sin licencia registrada", {}
    url = f"{_API}/api/licenses/verify"
    try:
        r = requests.get(url, params={"license_key": lk}, timeout=_TIMEOUT)
    except requests.RequestException as ex:
        return None, f"Error de red: {ex}", {}
    try:
        data = r.json()
    except Exception:
        data = {}
    valid = bool(data.get("valid"))
    msg = data.get("message") or ("Licencia válida" if valid else "Licencia inválida")
    if valid:
        st = cargar_estado()
        st.update({
            "license_key": lk,
            "device_id": obtener_device_id(),
            "activated": True,
            "activations_count": data.get("activations_count", st.get("activations_count")),
            "max_activations": data.get("max_activations", st.get("max_activations")),
            "remaining": data.get("remaining", st.get("remaining")),
        })
        guardar_estado(st)
    return valid, str(msg), data
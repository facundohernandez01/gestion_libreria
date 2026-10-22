"""Instalación y control del servidor como servicio de Windows.

El servicio ejecuta el mismo binario con el argumento `--service`; ese modo
levanta únicamente el servidor FastAPI (sin ventana) y arranca automáticamente
con Windows (start= auto).

Requiere permisos de administrador para instalar/quitar el servicio.
Sólo stdlib (ctypes/subprocess): no necesita pywin32.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

SERVICE_NAME = "LibreriaPOS"
SERVICE_DISPLAY_NAME = "Libreria POS - Servidor LAN"
SERVICE_DESCRIPTION = (
    "Servidor HTTP del sistema de gestión de librería/kiosko (multi-usuario LAN)."
)


def is_windows() -> bool:
    return os.name == "nt"


def _check_windows() -> None:
    if not is_windows():
        raise RuntimeError("Los servicios de Windows sólo están disponibles en Windows.")


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _python_exe() -> str:
    exe = Path(sys.executable)
    if not getattr(sys, "frozen", False):
        # Preferir pythonw.exe para no abrir consola al iniciar el servicio.
        pythonw = exe.with_name("pythonw.exe")
        if pythonw.exists():
            return str(pythonw)
    return str(exe)


def bin_path() -> str:
    """Comando que SCM ejecutará para arrancar el servicio."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --service'
    script = _base_dir() / "main.py"
    return f'"{_python_exe()}" "{script}" --service'


def _run(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    flags = 0x08000000 if is_windows() else 0  # CREATE_NO_WINDOW
    proc = subprocess.run(
        args, capture_output=True, text=True, errors="replace", creationflags=flags
    )
    if check and proc.returncode != 0:
        msg = (proc.stdout or "") + (proc.stderr or "")
        raise RuntimeError(msg.strip() or f"Error ejecutando {' '.join(args)}")
    return proc


def esta_instalado() -> bool:
    if not is_windows():
        return False
    try:
        return _run(["sc.exe", "query", SERVICE_NAME], check=False).returncode == 0
    except Exception:
        return False


_STATE_CODES = {
    1: "STOPPED",
    2: "START_PENDING",
    3: "STOP_PENDING",
    4: "RUNNING",
    5: "CONTINUE_PENDING",
    6: "PAUSE_PENDING",
    7: "PAUSED",
}


def _state_raw() -> str:
    if not is_windows():
        return "NOT_INSTALLED"
    try:
        out = _run(["sc.exe", "query", SERVICE_NAME], check=False)
    except Exception:
        return "NOT_INSTALLED"
    if out.returncode != 0:
        return "NOT_INSTALLED"
    # El texto de `sc` está localizado; el código numérico del estado no.
    for line in (out.stdout or "").splitlines():
        m = re.search(r":\s*([1-7])\s+\S+", line)
        if m:
            return _STATE_CODES.get(int(m.group(1)), "UNKNOWN")
    return "UNKNOWN"


def estado() -> str:
    """Estado legible del servicio."""
    raw = _state_raw()
    return {
        "RUNNING": "en ejecución",
        "STOPPED": "detenido",
        "START_PENDING": "iniciando",
        "STOP_PENDING": "deteniéndose",
        "PAUSED": "pausado",
        "NOT_INSTALLED": "no instalado",
        "UNKNOWN": "desconocido",
    }.get(raw, raw.lower())


def esta_corriendo() -> bool:
    return _state_raw() == "RUNNING"


def _esperar(objetivo: str, timeout: float = 15.0) -> bool:
    limite = time.time() + timeout
    while time.time() < limite:
        if _state_raw() == objetivo:
            return True
        time.sleep(0.4)
    return _state_raw() == objetivo


def instalar(auto_start: bool = True, iniciar_ahora: bool = True) -> None:
    """Crea (o recrea) el servicio y opcionalmente lo inicia."""
    _check_windows()

    # Si ya existe, detener y borrar para actualizar el binPath.
    if esta_instalado():
        _run(["sc.exe", "stop", SERVICE_NAME], check=False)
        _esperar("STOPPED", timeout=10)
        _run(["sc.exe", "delete", SERVICE_NAME], check=False)
        time.sleep(1)

    # Reintentar por si el servicio anterior aún está "marcado para eliminar".
    ultimo_error = ""
    for _ in range(6):
        proc = _run([
            "sc.exe", "create", SERVICE_NAME,
            "binPath=", bin_path(),
            "start=", "auto" if auto_start else "demand",
            "DisplayName=", SERVICE_DISPLAY_NAME,
        ], check=False)
        if proc.returncode == 0:
            break
        ultimo_error = ((proc.stdout or "") + (proc.stderr or "")).strip()
        time.sleep(1)
    else:
        raise RuntimeError(ultimo_error or "No se pudo crear el servicio.")

    _run(["sc.exe", "description", SERVICE_NAME, SERVICE_DESCRIPTION], check=False)
    # Reinicio automático ante fallos (5s, 10s, 30s).
    _run([
        "sc.exe", "failure", SERVICE_NAME,
        "reset=", "86400",
        "actions=", "restart/5000/restart/10000/restart/30000/",
    ], check=False)

    if iniciar_ahora:
        iniciar()


def iniciar() -> bool:
    _check_windows()
    if not esta_instalado():
        raise RuntimeError("El servicio no está instalado. Use 'Instalar' primero.")
    if _state_raw() == "RUNNING":
        return True
    proc = _run(["sc.exe", "start", SERVICE_NAME], check=False)
    if proc.returncode != 0 and _state_raw() != "RUNNING":
        msg = (proc.stdout or "") + (proc.stderr or "")
        raise RuntimeError(msg.strip() or "No se pudo iniciar el servicio.")
    return _esperar("RUNNING", timeout=20)


def detener() -> bool:
    _check_windows()
    if not esta_instalado():
        return False
    if _state_raw() == "STOPPED":
        return True
    proc = _run(["sc.exe", "stop", SERVICE_NAME], check=False)
    if proc.returncode != 0 and _state_raw() not in ("STOPPED", "STOP_PENDING"):
        msg = (proc.stdout or "") + (proc.stderr or "")
        raise RuntimeError(msg.strip() or "No se pudo detener el servicio.")
    return _esperar("STOPPED", timeout=20)


def desinstalar() -> None:
    _check_windows()
    if not esta_instalado():
        return
    try:
        detener()
    except Exception:
        pass
    _run(["sc.exe", "delete", SERVICE_NAME], check=False)
    time.sleep(0.8)


# ---------------------------------------------------------------------------
# Operaciones elevadas (UAC)
# ---------------------------------------------------------------------------
def _elevar(flag: str, listo, timeout: float = 45.0) -> bool:
    """Ejecuta `--flag` en un proceso elevado y espera a que `listo()` sea True."""
    _check_windows()
    import ctypes

    if getattr(sys, "frozen", False):
        exe = sys.executable
        params = flag
    else:
        exe = _python_exe()
        params = f'"{_base_dir() / "main.py"}" {flag}'

    resultado = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", exe, params, str(_base_dir()), 1
    )
    if resultado <= 32:
        raise RuntimeError(
            "Se canceló la solicitud de permisos de administrador "
            f"(código {resultado})."
        )

    limite = time.time() + timeout
    while time.time() < limite:
        try:
            if listo():
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return bool(listo())


def instalar_con_elevacion(auto_start: bool = True) -> bool:
    """Instala el servicio pidiendo permisos de administrador (UAC)."""
    return _elevar("--install-service", lambda: esta_corriendo(), timeout=60)


def iniciar_con_elevacion() -> bool:
    return _elevar("--start-service", lambda: esta_corriendo())


def detener_con_elevacion() -> bool:
    return _elevar("--stop-service", lambda: not esta_corriendo())


def desinstalar_con_elevacion() -> bool:
    return _elevar("--uninstall-service", lambda: not esta_instalado())


# ---------------------------------------------------------------------------
# Host del servicio (protocolo SCM vía ctypes)
# ---------------------------------------------------------------------------
if is_windows():
    import ctypes
    from ctypes import wintypes

    SERVICE_WIN32_OWN_PROCESS = 0x00000010
    SERVICE_ACCEPT_STOP = 0x00000001
    SERVICE_CONTROL_STOP = 0x00000001
    SERVICE_RUNNING = 0x00000004
    SERVICE_STOP_PENDING = 0x00000003
    SERVICE_STOPPED = 0x00000001

    class SERVICE_STATUS(ctypes.Structure):
        _fields_ = [
            ("dwServiceType", wintypes.DWORD),
            ("dwCurrentState", wintypes.DWORD),
            ("dwControlsAccepted", wintypes.DWORD),
            ("dwWin32ExitCode", wintypes.DWORD),
            ("dwServiceSpecificExitCode", wintypes.DWORD),
            ("dwCheckPoint", wintypes.DWORD),
            ("dwWaitHint", wintypes.DWORD),
        ]

    HANDLER_FUNCTION = ctypes.WINFUNCTYPE(wintypes.DWORD, wintypes.DWORD)
    SERVICE_MAIN_FUNCTION = ctypes.WINFUNCTYPE(
        None, wintypes.DWORD, ctypes.POINTER(wintypes.LPWSTR)
    )

    class SERVICE_TABLE_ENTRY(ctypes.Structure):
        _fields_ = [
            ("lpServiceName", wintypes.LPWSTR),
            ("lpServiceProc", SERVICE_MAIN_FUNCTION),
        ]

    def run_service(serve_callable) -> None:
        """Ejecuta `serve_callable(stop_event)` como servicio Windows."""
        _check_windows()

        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        advapi32.RegisterServiceCtrlHandlerW.argtypes = [wintypes.LPCWSTR, HANDLER_FUNCTION]
        advapi32.RegisterServiceCtrlHandlerW.restype = wintypes.HANDLE
        advapi32.SetServiceStatus.argtypes = [wintypes.HANDLE, ctypes.POINTER(SERVICE_STATUS)]
        advapi32.SetServiceStatus.restype = wintypes.BOOL
        advapi32.StartServiceCtrlDispatcherW.argtypes = [
            ctypes.POINTER(SERVICE_TABLE_ENTRY)
        ]
        advapi32.StartServiceCtrlDispatcherW.restype = wintypes.BOOL

        status = SERVICE_STATUS()
        status.dwServiceType = SERVICE_WIN32_OWN_PROCESS
        status.dwCurrentState = SERVICE_STOPPED
        status.dwControlsAccepted = 0
        status.dwWin32ExitCode = 0
        status.dwServiceSpecificExitCode = 0
        status.dwCheckPoint = 0
        status.dwWaitHint = 0

        stop_event = threading.Event()
        handle: list = [None]

        def _set_status(state: int, accepted: int = 0) -> None:
            status.dwCurrentState = state
            status.dwControlsAccepted = accepted
            status.dwCheckPoint = 0
            status.dwWaitHint = 0
            if handle[0]:
                advapi32.SetServiceStatus(handle[0], ctypes.byref(status))

        def _handler(control: int) -> int:
            if control == SERVICE_CONTROL_STOP:
                _set_status(SERVICE_STOP_PENDING)
                stop_event.set()
            return 0

        handler = HANDLER_FUNCTION(_handler)

        def _service_main(argc, argv) -> None:
            handle[0] = advapi32.RegisterServiceCtrlHandlerW(SERVICE_NAME, handler)
            if not handle[0]:
                return
            _set_status(SERVICE_RUNNING, SERVICE_ACCEPT_STOP)

            worker = threading.Thread(
                target=serve_callable, args=(stop_event,), daemon=True
            )
            worker.start()
            worker.join()

            _set_status(SERVICE_STOPPED)

        service_main = SERVICE_MAIN_FUNCTION(_service_main)
        table = (SERVICE_TABLE_ENTRY * 2)()
        table[0].lpServiceName = SERVICE_NAME
        table[0].lpServiceProc = service_main

        if not advapi32.StartServiceCtrlDispatcherW(table):
            err = ctypes.get_last_error()
            raise OSError(
                err,
                f"No se pudo conectar con el Administrador de servicios "
                f"(error {err}). Inicie el programa con --service sólo desde SCM.",
            )
else:
    def run_service(serve_callable) -> None:
        raise RuntimeError("Servicio Windows no disponible en este sistema.")

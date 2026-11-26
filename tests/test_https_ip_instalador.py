"""HTTPS IntraShop por IP LAN sin DNS ni cambios a libreria.db."""
from pathlib import Path
import subprocess

import pytest

from deploy.configurar_https_ip import (
    render_caddy, actualizar_env, validar_ip,
)


def test_caddy_lan_ip_sin_dns_y_sin_exposicion_del_backend():
    content = render_caddy("192.168.1.100")
    assert "https://192.168.1.100 {" in content
    assert "tls internal" in content
    assert "reverse_proxy 127.0.0.1:8000" in content
    assert "pos.home.arpa" not in content
    assert "http://" not in content
    assert ":8000 {" not in content


def test_script_caddy_rechaza_ip_publica_o_invalida():
    for ip in ("8.8.8.8", "127.0.0.1", "169.254.10.2", "0.0.0.0",
               "2001:db8::1", "servidor", "192.168.0.1; rm -rf /"):
        with pytest.raises(ValueError):
            validar_ip(ip)
    assert validar_ip("  10.2.3.4  ") == "10.2.3.4"
    with pytest.raises(ValueError):
        render_caddy("192.168.1.100", 80)


def test_instalador_genera_env_sin_borrar_secretos_ni_duplicar_variables():
    old = (
        "# Datos que el instalador debe preservar\n"
        "API_KEY=abc-privada\n"
        "INTRASHOP_ENFORCE_HTTPS=0\n"
        "POS_PUBLIC_URL=http://antiguo\n"
        "MP_ACCESS_TOKEN=secreto-no-exponer\n"
    )
    result = actualizar_env(old, "192.168.1.33")
    assert result.count("INTRASHOP_ENFORCE_HTTPS=") == 1
    assert result.count("POS_PUBLIC_URL=") == 1
    assert "INTRASHOP_ENFORCE_HTTPS=1" in result
    assert "POS_PUBLIC_URL=https://192.168.1.33" in result
    assert "API_KEY=abc-privada" in result
    assert "MP_ACCESS_TOKEN=secreto-no-exponer" in result
    assert "# Datos que el instalador debe preservar" in result


def test_instalador_tiene_preview_no_mutante():
    root = Path(__file__).resolve().parents[1]
    script = root / "deploy" / "configurar_https_ip.py"
    result = subprocess.run(
        ["python", str(script), "--ip", "192.168.8.42", "--mostrar-config"],
        text=True, capture_output=True, check=True,
    )
    assert "https://192.168.8.42" in result.stdout
    assert ".env generado (sin escribir)" in result.stdout
    assert "tls internal" in result.stdout


def test_gui_usa_asistente_por_ip_sin_sudo_root_y_sin_tocar_db():
    root = Path(__file__).resolve().parents[1]
    gui = (root / "pos_server_gui.py").read_text(encoding="utf-8")
    installer = (root / "deploy" / "configurar_https_ip.py").read_text(encoding="utf-8")
    assert '("HTTPS local", self.configure_https_ip)' in gui
    assert 'def configure_https_ip(self):' in gui
    assert '"--ip", ip' in gui
    assert 'input("¿Continuar? [s/N] ")' in installer
    assert '"caddy", "validate"' in installer
    assert '"sudo", "install"' in installer
    assert 'libreria.db' not in installer
    assert 'sudo", sys.executable' not in gui

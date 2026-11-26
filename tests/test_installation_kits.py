"""Kits públicos y asistente de distribución sin claves privadas."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zipfile import ZipFile
import hashlib
import json
import os

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from services.installation_kits import (
    crear_kit_conexion, datos_ca, listar_instaladores, validar_url_servidor,
)


@pytest.fixture
def ca_publica(tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "IntraShop local CA - test"),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc) - timedelta(days=1))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=7))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(key, hashes.SHA256())
    )
    public = cert.public_bytes(serialization.Encoding.PEM)
    path = tmp_path / "intrashop-root-ca.crt"
    path.write_bytes(public)
    return path, public, cert.fingerprint(hashes.SHA256()).hex().upper()


def test_kit_de_tótem_contiene_ca_publica_pero_ningun_secreto(ca_publica, tmp_path):
    ca, public, fingerprint = ca_publica
    dst = tmp_path / "conexion-totem.zip"
    res = crear_kit_conexion(
        dst, "https://192.168.1.10", "totem", certificado=ca,
    )
    assert res["url"] == "https://192.168.1.10"
    assert res["sha256_ca"] == fingerprint
    with ZipFile(dst) as archive:
        assert set(archive.namelist()) == {
            "conexion.json", "intrashop-root-ca.crt", "INSTRUCCIONES.txt",
        }
        assert archive.read("intrashop-root-ca.crt") == public
        manifest = json.loads(archive.read("conexion.json"))
        assert manifest["servidor"] == "https://192.168.1.10"
        assert manifest["catalogo"] == "https://192.168.1.10/intrashop/"
        assert manifest["ca_sha256"] == fingerprint
        assert manifest["credenciales_incluidas"] is False
        assert "api_key" not in json.dumps(manifest).lower()
        assert "token" not in json.dumps(manifest).lower()
        assert "pairing_code" not in json.dumps(manifest).lower()


def test_kit_para_pos_cliente_sin_api_key(ca_publica, tmp_path):
    ca, _, _ = ca_publica
    destino = tmp_path / "pos-kit.zip"
    crear_kit_conexion(destino, "https://10.2.3.4", "pos", certificado=ca)
    with ZipFile(destino) as archive:
        data = json.loads(archive.read("conexion.json"))
        assert data["tipo"] == "pos"
        assert data["requiere_emparejamiento_pos_server"] is True


@pytest.mark.parametrize("url", [
    "", "http://192.168.1.10", "https://example.com",
    "https://8.8.8.8", "https://127.0.0.1",
    "https://192.168.1.2:8000", "https://192.168.1.2:abc",
    "https://user:pass@192.168.1.10", "https://192.168.1.2/secret",
    "https://192.168.1.2?key=secret",
    "https://192.168.1.2#fragment",
    "https://[::1]",
])
def test_no_generar_kits_con_destinos_inseguros(url, ca_publica, tmp_path):
    ca, _, _ = ca_publica
    with pytest.raises(ValueError):
        crear_kit_conexion(tmp_path / "bad.zip", url, "totem", certificado=ca)
    assert not (tmp_path / "bad.zip").exists()


def test_certificado_privado_nunca_es_exportado(tmp_path):
    cert = tmp_path / "root.key"
    cert.write_text(
        "-----BEGIN PRIVATE KEY-----\nSECRETO\n-----END PRIVATE KEY-----\n",
        encoding="ascii",
    )
    with pytest.raises(ValueError):
        datos_ca(cert)


def test_listado_builds_solo_artefactos_reales(tmp_path):
    empty = listar_instaladores(tmp_path / "no-existe")
    assert all(not rows for rows in empty.values())
    root = tmp_path / "builds"
    root.mkdir()
    for name in ("IntraShop-0.1.0-setup.exe", "IntraShopServer-0.1.0.msi",
                 "Kiosmico-0.1.0.exe", "descarga-falsa.exe", "IntraShop-evil.sh"):
        (root / name).write_bytes(b"build-placeholder-for-test")
    symlink = root / "IntraShop-no-verificado.exe"
    symlink.symlink_to(root / "IntraShop-0.1.0-setup.exe")
    result = listar_instaladores(root)
    assert [item["nombre"] for item in result["totem"]] == ["IntraShop-0.1.0-setup.exe"]
    assert [item["nombre"] for item in result["pos"]] == ["Kiosmico-0.1.0.exe"]
    assert [item["nombre"] for item in result["servidor"]] == ["IntraShopServer-0.1.0.msi"]


def test_gui_no_ofrece_descarga_ficticia_ni_clave_global():
    root = Path(__file__).resolve().parents[1]
    gui = (root / "pos_server_gui.py").read_text(encoding="utf-8")
    assert "def distribution_wizard(self):" in gui
    assert '"Instalar / conectar equipos"' in gui
    assert 'kits.listar_instaladores()' in gui
    assert "Exportar kit de conexión" in gui
    assert "self._autorizar_kit_instalacion()" in gui
    assert "actor.get(\"es_admin\")" in gui
    assert "self._admin_unlock_until" in gui
    assert "https://" in gui
    assert "api_key" not in (
        root / "services/installation_kits.py"
    ).read_text().split('manifest = {')[1].split('}')[0].lower()

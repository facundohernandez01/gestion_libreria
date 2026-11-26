"""Private CA and native Uvicorn TLS; no external proxy or system trust changes."""
from __future__ import annotations
import datetime as dt
import ipaddress
import json
import os
import ssl
import tempfile
from pathlib import Path
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID

ROOT = Path.home() / ".config" / "intrashop" / "server-tls"
PROFILE = ROOT / "profile.json"

def private_ip(value):
    ip = ipaddress.IPv4Address(value)
    if not any(ip in ipaddress.IPv4Network(net) for net in ("10.0.0.0/8","172.16.0.0/12","192.168.0.0/16")):
        raise ValueError("Se requiere una IPv4 privada de este servidor.")
    return ip

def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)

def prepare(ip, *, root=ROOT):
    ip = private_ip(ip)
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    now = dt.datetime.now(dt.timezone.utc)
    ca_key_path, ca_path = root / "root.key", root / "root.crt"
    if ca_path.exists() != ca_key_path.exists():
        raise RuntimeError("CA incompleta: restaurá el respaldo, no se reemplazará automáticamente.")
    if ca_path.exists():
        ca = x509.load_pem_x509_certificate(ca_path.read_bytes())
        key = serialization.load_pem_private_key(ca_key_path.read_bytes(), password=None)
        if ca.not_valid_after_utc <= now + dt.timedelta(days=400):
            raise RuntimeError("La CA requiere renovación planificada.")
        if ca.public_key().public_numbers() != key.public_key().public_numbers():
            raise RuntimeError("CA y clave no coinciden.")
    else:
        key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "IntraShop LAN CA")])
        ca = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
              .public_key(key.public_key()).serial_number(x509.random_serial_number())
              .not_valid_before(now-dt.timedelta(minutes=5)).not_valid_after(now+dt.timedelta(days=3650))
              .add_extension(x509.BasicConstraints(ca=True,path_length=0),critical=True)
              .add_extension(x509.KeyUsage(False,False,False,False,False,True,True,False,False),critical=True)
              .sign(key,hashes.SHA256()))
        atomic_write(ca_key_path,key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        atomic_write(ca_path,ca.public_bytes(serialization.Encoding.PEM))
    leaf_key = rsa.generate_private_key(public_exponent=65537,key_size=2048)
    leaf = (x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,str(ip))]))
        .issuer_name(ca.subject).public_key(leaf_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now-dt.timedelta(minutes=5)).not_valid_after(now+dt.timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=False,path_length=None),critical=True)
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ip)]),critical=False)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),critical=False)
        .add_extension(x509.KeyUsage(True,False,True,False,False,False,False,False,False),critical=True)
        .sign(key,hashes.SHA256()))
    cert_path, key_path = root/"server.crt",root/"server.key"
    atomic_write(key_path,leaf_key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    atomic_write(cert_path,leaf.public_bytes(serialization.Encoding.PEM))
    ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert_path,key_path)
    return {"ip":str(ip),"url":f"https://{ip}","ca":str(ca_path),"cert":str(cert_path),"key":str(key_path)}

def activate(profile, *, path=PROFILE):
    atomic_write(Path(path),json.dumps({"ip":profile["ip"]}).encode())

def load(*, path=PROFILE):
    path=Path(path)
    if not path.exists():
        return None
    ip=private_ip(json.loads(path.read_text())["ip"])
    root=path.parent
    cert,key,ca=root/"server.crt",root/"server.key",root/"root.crt"
    if not all(p.is_file() for p in (cert,key,ca)):
        raise RuntimeError("HTTPS configurado pero faltan certificados; no se iniciará HTTP.")
    return {"ip":str(ip),"url":f"https://{ip}","ca":str(ca),"cert":str(cert),"key":str(key)}

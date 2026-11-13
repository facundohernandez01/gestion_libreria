"""Regresión: la exportación remota nunca pisa backups existentes."""
import io

import httpx
import pytest

from api_client import ApiClient


def test_no_sobrescribe_archivo_existente(tmp_path):
    destino = tmp_path / "backup.db"
    destino.write_bytes(b"backup anterior")
    cliente = ApiClient("http://127.0.0.1:1", "test")
    with pytest.raises(FileExistsError):
        cliente.exportar_backup_servidor(destino)
    assert destino.read_bytes() == b"backup anterior"


def test_error_http_no_deja_archivos_temporales(tmp_path, monkeypatch):
    cliente = ApiClient("http://127.0.0.1:1", "test")
    monkeypatch.setattr(cliente, "_admin_headers", lambda: {"Authorization": "Bearer test"})

    def handler(request):
        return httpx.Response(503, text="servidor no disponible")

    original_stream = httpx.stream
    transport = httpx.MockTransport(handler)

    def stream(method, url, **kwargs):
        return httpx.Client(transport=transport).stream(method, url, **kwargs)

    monkeypatch.setattr(httpx, "stream", stream)
    destino = tmp_path / "backup.db"
    with pytest.raises(httpx.HTTPStatusError):
        cliente.exportar_backup_servidor(destino)
    assert not destino.exists()
    assert list(tmp_path.iterdir()) == []

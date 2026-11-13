"""Backups: límite y transmisión sin cargar el archivo entero en RAM."""
import ast
from pathlib import Path

import httpx
from api_client import ApiClient

ROOT = Path(__file__).resolve().parents[1]


def _function(path, name):
    source = (ROOT / path).read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name
    )
    return ast.get_source_segment(source, node)


def test_exportacion_servidor_usa_file_response_y_limpia_archivo():
    code = _function("api_server.py", "api_exportar_backup")
    assert "FileResponse(" in code
    assert "BackgroundTask(temporal.cleanup)" in code
    assert "read_bytes()" not in code


def test_validacion_servidor_limita_durante_stream():
    code = _function("api_server.py", "api_validar_backup")
    assert "async for bloque in request.stream()" in code
    assert "recibido > MAX_BACKUP_BYTES" in code
    assert "archivo.write_bytes(payload)" not in code


def test_cliente_envia_fragmentos_y_no_revela_secretos(tmp_path, monkeypatch):
    origen = tmp_path / "copia.db"
    origen.write_bytes(b"A" * (1024 * 1024 * 2 + 17))
    cliente = ApiClient("http://127.0.0.1:8000", "TEST-KEY")
    monkeypatch.setattr(
        cliente, "_admin_headers", lambda: {"Authorization": "Bearer TEST-SESSION"},
    )
    recibidos = []

    def fake_post(url, **kwargs):
        assert url.endswith("/admin/backups/validar")
        assert "TEST-KEY" not in url and "TEST-SESSION" not in url
        for bloque in kwargs["content"]:
            assert len(bloque) <= 1024 * 1024
            recibidos.append(bloque)
        return httpx.Response(
            200, json={"valido": True},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("api_client.httpx.post", fake_post)
    assert cliente.validar_backup_servidor(origen)["valido"] is True
    assert len(recibidos) == 3
    assert sum(map(len, recibidos)) == origen.stat().st_size

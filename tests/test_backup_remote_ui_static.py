"""Regresión: en IntraShop no ofrecer una falsa restauración online."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_config_backup_remote_is_preview_only():
    source = (ROOT / "config.py").read_text(encoding="utf-8")
    ast.parse(source)
    assert "Vista previa solamente: no se importó ningún dato" in source
    assert "if _backup_remoto else ft.Row([" in source
    assert "tools/restaurar_backup_servidor.py" in source


def test_systemd_starts_backend_headless():
    doc = (ROOT / "docs/intrashop-servidor-independiente.md").read_text(encoding="utf-8")
    assert "pos_server.py --headless --host 0.0.0.0 --port 8000" in doc


def test_offline_runbook_requires_explicit_apply_step():
    doc = (ROOT / "docs/manual-operativo-pos-server-backups.md").read_text(encoding="utf-8")
    assert "--modo reemplazar --aplicar" in doc
    assert "--modo reemplazar" in doc
    assert "NO importa ningún registro" in doc

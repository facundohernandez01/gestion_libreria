"""Ticket IntraShop (80 mm): generar y enviar a impresora desde POS Server.

No importa Flet ni utiliza la SQLite de una terminal cliente. Cada venta tiene
un único job persistido; un error de impresora nunca revierte el cobro.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import subprocess
import sys
import textwrap
import time
from pathlib import Path

logger = logging.getLogger(__name__)


def _pdf_ticket(path: Path, venta_id: int, items: list[dict], total: float) -> None:
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    from core.settings import settings

    lines: list[tuple[str, bool]] = []
    for item in items:
        nombre = str(item.get("descripcion") or "Producto")
        cantidad = int(item["cantidad"])
        precio = float(item["precio_unitario"])
        for index, part in enumerate(textwrap.wrap(nombre, width=38) or [nombre]):
            lines.append((f"{cantidad} x {part}" if index == 0 else f"    {part}", False))
        lines.append((f"  {cantidad} x $ {precio:.2f}     $ {cantidad * precio:.2f}", False))

    alto = max(100, 75 + len(lines) * 5) * mm
    ancho = 80 * mm
    doc = canvas.Canvas(str(path), pagesize=(ancho, alto))
    y = alto - 12 * mm

    def escribir(texto: str, *, centrado: bool = False, fuerte: bool = False, size: int = 9):
        nonlocal y
        doc.setFont("Helvetica-Bold" if fuerte else "Helvetica", size)
        if centrado:
            doc.drawCentredString(ancho / 2, y, texto[:55])
        else:
            doc.drawString(5 * mm, y, texto[:55])
        y -= 5 * mm

    escribir((settings.nombre_negocio or "IntraShop")[:35], centrado=True, fuerte=True, size=11)
    escribir("TICKET DE COMPRA", centrado=True, fuerte=True)
    escribir(f"Venta #{venta_id} - Mercado Pago QR", centrado=True)
    escribir(time.strftime("%d/%m/%Y %H:%M"), centrado=True)
    escribir("-" * 42)
    for line, strong in lines:
        escribir(line, fuerte=strong)
    escribir("-" * 42)
    escribir(f"TOTAL: $ {total:.2f}", fuerte=True, size=12)
    escribir("Pedido abonado - conservar comprobante", centrado=True, size=8)
    escribir("NO ES FACTURA FISCAL", centrado=True, size=8)
    doc.showPage()
    doc.save()


def _enviar_a_impresora(path: Path) -> None:
    if sys.platform.startswith("win"):
        os.startfile(str(path), "print")  # type: ignore[attr-defined]
        return
    comando = ["lp"]
    impresora = os.getenv("INTRASHOP_PRINTER", "").strip()
    if impresora:
        comando += ["-d", impresora]
    comando.append(str(path))
    resultado = subprocess.run(comando, capture_output=True, text=True, timeout=20)
    if resultado.returncode:
        raise RuntimeError(resultado.stderr.strip()[:250] or "CUPS rechazó el ticket")


def emitir_ticket_venta(db_path: str, venta_id: int, checkout_id: str,
                        items: list[dict], total: float) -> dict:
    """Consumir un único trabajo PENDING después del COMMIT de la venta.

    El estado PRINTING no se reintenta automáticamente tras un reinicio
    porque CUPS pudo haber recibido el trabajo antes del corte.
    """
    with sqlite3.connect(db_path, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("BEGIN IMMEDIATE")
        job = conn.execute(
            """SELECT j.estado, c.estado AS checkout_estado, c.venta_id
               FROM intrashop_ticket_jobs j
               JOIN intrashop_checkouts c ON c.id=j.checkout_id
               WHERE j.venta_id=? AND j.checkout_id=?""",
            (venta_id, checkout_id),
        ).fetchone()
        if not job or job["estado"] != "pending":
            return {"estado": job["estado"] if job else "missing"}
        if job["checkout_estado"] != "completed" or job["venta_id"] != venta_id:
            return {"estado": "not_paid"}
        conn.execute(
            "UPDATE intrashop_ticket_jobs SET estado='printing',updated_at=? WHERE venta_id=?",
            (int(time.time()), venta_id),
        )
        conn.commit()

    path = None
    try:
        from core.settings import settings
        dest = Path(settings.tickets_path)
        if not dest.is_absolute():
            dest = Path(db_path).resolve().parent / dest
        dest.mkdir(parents=True, exist_ok=True)
        path = dest / f"intrashop_venta_{venta_id}.pdf"
        if not path.is_file():
            _pdf_ticket(path, venta_id, items, total)
        imprimir = os.getenv("INTRASHOP_PRINT_TICKET", "1").strip().lower() not in (
            "0", "false", "no", "off",
        )
        if imprimir:
            _enviar_a_impresora(path)
        estado = "sent" if imprimir else "generated"
        error = None
    except Exception as exc:
        logger.exception("No se pudo imprimir el ticket IntraShop venta #%s", venta_id)
        estado, error = "failed", str(exc)[:300]
    with sqlite3.connect(db_path, timeout=10) as conn:
        conn.execute(
            "UPDATE intrashop_ticket_jobs SET estado=?,pdf_path=?,error=?,updated_at=? WHERE venta_id=?",
            (estado, str(path) if path else None, error, int(time.time()), venta_id),
        )
        conn.commit()
    return {"estado": estado, "pdf_path": str(path) if path else None, "error": error}

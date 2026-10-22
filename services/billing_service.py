"""Facturación automática configurable — patrón Service + Strategy.

- Si FACTURACION_ACTIVA=false no genera nada (venta normal).
- Tipos soportados: ticket | factura_borrador | remito (todos en .txt imprimible;
  el PDF queda como extensión futura sin romper la API).
- Numeración automática con prefijo configurable, persistida en tabla config
  (FACTURACION_ULTIMO_NUMERO) para no depender solo del .env.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)


class BillingService:
    _instance = None

    def __new__(cls, *a, **kw):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init = False
        return cls._instance

    def __init__(self, db=None):
        if getattr(self, "_init", False):
            return
        self._db = db
        self._init = True

    def _db_or_none(self):
        if self._db is not None:
            return self._db
        try:
            from database_manager import DatabaseManager

            self._db = DatabaseManager()
            return self._db
        except Exception:
            return None

    # ---------- API pública ----------
    @property
    def activa(self) -> bool:
        try:
            from core.settings import settings

            return settings.facturacion_activa
        except Exception:
            return True

    def siguiente_numero(self) -> str:
        from core.settings import settings

        db = self._db_or_none()
        ultimo = 0
        if db:
            try:
                ultimo = int(db.get_config_value("FACTURACION_ULTIMO_NUMERO") or 0)
            except (TypeError, ValueError):
                ultimo = 0
        nuevo = ultimo + 1
        if db:
            db.set_config("FACTURACION_ULTIMO_NUMERO", str(nuevo))
        return f"{settings.facturacion_prefijo}-{nuevo:06d}"

    def generar_ticket_pdf(self, venta_id: int, items: List[dict], total: float,
                             metodo_pago: str = "efectivo", numero_factura: str = "",
                             cae: str = "", vencimiento_cae: str = "") -> str:
        """Ticket PDF estilo rollo térmico 80mm (como en el build: reportlab).

        Si reportlab no está instalado, recurre al comprobante .txt.
        Retorna la ruta del archivo generado.
        """
        try:
            from reportlab.lib.units import mm
            from reportlab.pdfgen import canvas
        except ImportError:
            return self.generar_comprobante(venta_id, items, total, metodo_pago)

        from core.settings import settings
        from datetime import datetime as _dt

        dest_dir = Path(settings.facturacion_dir) / "tickets"
        dest_dir.mkdir(parents=True, exist_ok=True)
        fecha = _dt.now().strftime("%Y%m%d_%H%M%S")
        path = dest_dir / f"ticket_venta_{venta_id}_{fecha}.pdf"

        ancho = 80 * mm
        alto = (220 + len(items) * 8) * mm
        c = canvas.Canvas(str(path), pagesize=(ancho, alto))
        x = 6 * mm
        y = alto - 10 * mm

        def linea(texto: str = "", bold: bool = False, size: int = 9, centro: bool = False):
            nonlocal y
            c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
            if centro:
                c.drawCentredString(ancho / 2, y, texto[:48])
            else:
                c.drawString(x, y, texto[:48])
            y -= (size * 0.55 + 2) * mm / 3

        logo = Path("img") / "logomp.png"
        if logo.exists():
            try:
                from reportlab.lib.utils import ImageReader
                c.drawImage(ImageReader(str(logo)), ancho / 2 - 15 * mm, y - 12 * mm,
                            width=30 * mm, height=12 * mm, preserveAspectRatio=True)
                y -= 14 * mm
            except Exception:  # noqa: BLE001
                pass

        nombre_negocio = (settings.nombre_negocio or "").strip()
        if nombre_negocio:
            linea(nombre_negocio.upper(), bold=True, size=12, centro=True)
        if settings.direccion_negocio:
            linea(f"Dirección: {settings.direccion_negocio}", centro=True)
        if settings.cuit:
            linea(f"CUIT: {settings.cuit}", centro=True)
        if settings.condicion_iva:
            linea(f"Cond. IVA: {settings.condicion_iva}", centro=True)
        if settings.ingresos_brutos:
            linea(f"Ing. Brutos: {settings.ingresos_brutos}", centro=True)
        if settings.inicio_actividades:
            linea(f"Inicio act.: {settings.inicio_actividades}", centro=True)
        linea("-" * 40, centro=True)
        if numero_factura:
            linea(f"Factura {settings.afip_tipo_factura} Nº {numero_factura}", bold=True, centro=True)
            if cae:
                linea(f"CAE: {cae}", centro=True)
            if vencimiento_cae:
                linea(f"Vto CAE: {vencimiento_cae}", centro=True)
        else:
            linea("TICKET DE VENTA", bold=True, size=11, centro=True)
        linea(f"Venta #{venta_id}  {_dt.now():%d/%m/%Y %H:%M}", centro=True)
        linea(f"Pago: {metodo_pago}", centro=True)
        linea("-" * 40, centro=True)
        linea(f"{'Cant':<6}{'Producto':<24}{'Subtotal':>10}", bold=True)
        for it in items:
            desc = str(it.get("descripcion", ""))[:22]
            linea(f"{int(it.get('cantidad', 0)):<6}{desc:<24}${float(it.get('subtotal', 0)):>9.2f}")
        linea("-" * 40, centro=True)
        linea(f"TOTAL: ${float(total):.2f}", bold=True, size=12, centro=True)
        linea("Consumidor Final", centro=True)
        if cae:
            try:
                import qrcode
                from reportlab.lib.utils import ImageReader as _IR
                from io import BytesIO
                qr_data = (f"https://www.afip.gob.ar/fe/qr/?p={numero_factura}")
                img = qrcode.make(qr_data)
                buf = BytesIO()
                img.save(buf, format="PNG")
                buf.seek(0)
                c.drawImage(_IR(buf), ancho / 2 - 15 * mm, y - 32 * mm,
                            width=30 * mm, height=30 * mm)
                y -= 33 * mm
                linea("Escanea para verificar en AFIP", size=7, centro=True)
            except Exception:  # noqa: BLE001
                pass
        linea("Gracias por su compra", centro=True)
        c.showPage()
        c.save()
        logger.info("ticket PDF generado: %s", path)
        return str(path)
        from core.settings import settings

        db = self._db_or_none()
        ultimo = 0
        if db:
            try:
                ultimo = int(db.get_config_value("FACTURACION_ULTIMO_NUMERO") or 0)
            except (TypeError, ValueError):
                ultimo = 0
        nuevo = ultimo + 1
        if db:
            db.set_config("FACTURACION_ULTIMO_NUMERO", str(nuevo))
        return f"{settings.facturacion_prefijo}-{nuevo:06d}"

    def generar_comprobante(self, venta_id: int, items: List[dict], total: float,
                            metodo_pago: str = "efectivo") -> str:
        """Genera y guarda el comprobante. Retorna ruta o '' si está desactivada."""
        from core.settings import settings

        if not settings.facturacion_activa:
            return ""
        numero = self.siguiente_numero()
        tipo = (settings.facturacion_tipo or "ticket").lower()
        dest_dir = Path(settings.comprobantes_path)
        dest_dir.mkdir(parents=True, exist_ok=True)
        fecha = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = dest_dir / f"{numero}_{fecha}.txt"

        lineas = ["=" * 40]
        if settings.nombre_negocio:
            lineas.append(settings.nombre_negocio.center(40))
        if settings.direccion_negocio:
            lineas.append(settings.direccion_negocio.center(40))
        if settings.cuit:
            lineas.append(f"CUIT: {settings.cuit}".center(40))
        if settings.condicion_iva:
            lineas.append(f"Cond. IVA: {settings.condicion_iva}".center(40))
        if settings.ingresos_brutos:
            lineas.append(f"Ing. Brutos: {settings.ingresos_brutos}".center(40))
        if settings.inicio_actividades:
            lineas.append(f"Inicio act.: {settings.inicio_actividades}".center(40))
        lineas += [
            "=" * 40,
            f"{tipo.upper()}  N° {numero}",
            f"Venta #{venta_id}  {datetime.now():%d/%m/%Y %H:%M}",
            f"Pago: {metodo_pago}",
            "-" * 40,
        ]
        for it in items:
            desc = str(it.get("descripcion", ""))[:26]
            cant = int(it.get("cantidad", 0))
            pu = float(it.get("precio_unitario", 0))
            sub = float(it.get("subtotal", pu * cant))
            lineas.append(f"{desc:<26} x{cant:>2} ${sub:>7.2f}")
        lineas += ["-" * 40, f"TOTAL: ${float(total):.2f}".rjust(40), "=" * 40,
                   "Gracias por su compra".center(40)]
        path.write_text("\n".join(l for l in lineas if l != ""), encoding="utf-8")
        logger.info("comprobante %s generado: %s", numero, path)
        return str(path)


billing_service = BillingService()

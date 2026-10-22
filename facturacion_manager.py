"""Gestor de facturación electrónica integrado con el punto de venta.

Maneja autenticación, emisión de facturas y generación de tickets PDF.
Compatible con WSAA y WSFE (soluciona DH_KEY_TOO_SMALL).

Reconstruido desde el bytecode del build.
"""
from __future__ import annotations

import base64
import json
import os
import threading
from datetime import datetime, timedelta
from io import BytesIO

import qrcode
from reportlab.lib.pagesizes import letter  # noqa: F401  (se mantiene por compatibilidad)
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

import configwsfe as config
from wsaa_client import WSAAClient
from wsfe_client import WSFEClient


class FacturacionManager:
    """Gestor centralizado de facturación electrónica."""

    def __init__(self, db_manager):
        self.db_manager = db_manager
        config.reload()  # re-lee DB (Ajustes) > .env
        try:
            from core.settings import settings

            settings.reload()
        except Exception:
            pass
        self.wsaa_client = None
        self.wsfe_client = None
        self.token = None
        self.sign = None
        self.token_expiration = None
        self._auth_lock = threading.Lock()
        self.tickets_dir = os.path.join(os.path.dirname(__file__), "tickets")
        try:
            from core.settings import settings

            self.tickets_dir = settings.tickets_path
        except Exception:
            pass
        os.makedirs(self.tickets_dir, exist_ok=True)
        print(f"🚀 FacturacionManager inicializado en {config.get_modo_texto()}")

    def _necesita_autenticacion(self) -> bool:
        """Verifica si se necesita autenticar o renovar token."""
        if not self.token or not self.sign:
            return True
        if self.token_expiration:
            tiempo_restante = self.token_expiration - datetime.now()
            if tiempo_restante.total_seconds() < 1800:
                return True
        return False

    def autenticar(self) -> dict:
        """Realiza autenticación con WSAA (thread-safe)."""
        with self._auth_lock:
            if not self._necesita_autenticacion():
                return {"success": True, "message": "Token vigente", "reused": True}
            try:
                print("🔐 Autenticando con AFIP...")
                if self.wsaa_client is None:
                    self.wsaa_client = WSAAClient()
                result = self.wsaa_client.login()
                if result["success"]:
                    self.token = result["token"]
                    self.sign = result["sign"]
                    self.token_expiration = datetime.now() + timedelta(hours=12)
                    print(f"✅ Token obtenido, válido hasta {self.token_expiration.strftime('%H:%M:%S')}")
                    return {
                        "success": True,
                        "message": "Autenticación exitosa",
                        "token": self.token,
                        "sign": self.sign,
                        "expiration": self.token_expiration,
                    }
                print(f"❌ Error autenticación: {result['message']}")
                return result
            except Exception as e:  # noqa: BLE001
                print(f"❌ Excepción autenticación: {str(e)}")
                return {"success": False, "message": f"Error en autenticación: {str(e)}"}

    def emitir_factura_venta(self, venta_id, carrito, medio_pago="efectivo") -> dict:
        """Emite factura para una venta del punto de venta.

        Args:
            venta_id: ID de la venta en la base de datos.
            carrito: Lista de items de la venta.
            medio_pago: "efectivo", "tarjeta" o "qr".
        """
        try:
            print(f"📝 Iniciando emisión de factura para venta #{venta_id}")
            auth_result = self.autenticar()
            if not auth_result["success"]:
                return auth_result

            self.wsfe_client = WSFEClient(self.token, self.sign)

            importe_neto = sum(item["subtotal"] for item in carrito)

            def _recargo(clave: str) -> float:
                try:
                    return float((self.db_manager.get_config_value(clave) or "0").replace(",", "."))
                except (TypeError, ValueError):
                    return 0.0

            if medio_pago in ("qr", "mercadopago_qr", "tarjeta"):
                recargo_porcentaje = _recargo("RECARGO")
            elif medio_pago == "tarjeta_debito":
                recargo_porcentaje = _recargo("RECARGO_DEBITO")
            elif medio_pago == "tarjeta_credito":
                recargo_porcentaje = _recargo("RECARGO_CREDITO")
            else:
                recargo_porcentaje = 0.0
            if recargo_porcentaje > 0:
                recargo = importe_neto * (recargo_porcentaje / 100)
                importe_neto += recargo
                print(f"💳 Recargo {recargo_porcentaje}% aplicado: ${recargo:.2f}")

            tipo_factura = (self.db_manager.get_config_value("AFIP_TIPO_FACTURA")
                            or config.TIPO_FACTURA or "C").upper()
            if tipo_factura == "C":
                tipo_cbte = config.TIPO_CBTE_FACTURA_C
                iva_porcentaje = config.IVA_0_PORCIENTO
            else:
                tipo_cbte = config.tipo_cbte_para_factura(tipo_factura)
                iva_porcentaje = config.IVA_21_PORCIENTO

            datos_factura = {
                "punto_venta": config.PUNTO_VENTA,
                "tipo_cbte": tipo_cbte,
                "concepto": config.CONCEPTO_PRODUCTOS,
                "tipo_doc": config.DOC_TIPO_CONSUMIDOR_FINAL,
                "nro_doc": 0,
                "importe_neto": round(importe_neto, 2),
                "iva_porcentaje": iva_porcentaje,
            }

            result = self.wsfe_client.emitir_factura(datos_factura)

            if result["success"]:
                self.db_manager.actualizar_factura_venta(
                    venta_id, result["numero"], result["cae"], result["vencimiento_cae"]
                )
                print(f"✅ Factura B #{result['numero']} emitida - CAE: {result['cae']}")
                return {
                    "success": True,
                    "numero_factura": result["numero"],
                    "cae": result["cae"],
                    "vencimiento_cae": result["vencimiento_cae"],
                    "importe_total": importe_neto + round(importe_neto * 0.21, 2),
                    "message": f"Factura {result['numero']} emitida exitosamente",
                }
            return result
        except Exception as e:  # noqa: BLE001
            print(f"❌ Error emitiendo factura: {str(e)}")
            return {"success": False, "message": f"Error al emitir factura: {str(e)}"}

    def generar_qr_afip(self, numero, cae, vencimiento, total):
        """Genera el QR oficial de AFIP según RG 4892/2021."""
        try:
            data = {
                "ver": 1,
                "fecha": datetime.now().strftime("%Y-%m-%d"),
                "cuit": int(config.CUIT),
                "ptoVta": int(config.PUNTO_VENTA),
                "tipoCmp": config.tipo_cbte_para_factura(config.TIPO_FACTURA),
                "nroCmp": numero,
                "importe": float(total),
                "moneda": "PES",
                "ctz": 1,
                "tipoDocRec": 99,
                "nroDocRec": 0,
                "tipoCodAut": "E",
                "codAut": int(cae),
            }
            json_data = json.dumps(data, separators=(",", ":"))
            b64_data = base64.b64encode(json_data.encode("utf-8")).decode("utf-8")
            url_afip = f"https://www.afip.gob.ar/fe/qr/?p={b64_data}"

            qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=8, border=1)
            qr.add_data(url_afip)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")

            buffer = BytesIO()
            img.save(buffer, format="PNG")
            buffer.seek(0)
            return ImageReader(buffer)
        except Exception as e:  # noqa: BLE001
            print(f"⚠️ Error generando QR: {str(e)}")
            return None

    def generar_ticket_pdf(
        self, venta_id, carrito, numero_factura=None, cae=None, vencimiento_cae=None
    ):
        """Genera un ticket PDF estilo rollo térmico (80mm de ancho)."""
        ancho = 80 * mm
        alto_estimado = (200 + len(carrito) * 15) * mm
        filename = f"ticket_{venta_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        filepath = os.path.join(self.tickets_dir, filename)

        c = canvas.Canvas(filepath, pagesize=(ancho, alto_estimado))
        y = alto_estimado - 10 * mm
        x_center = ancho / 2
        margen = 5 * mm

        c.setFont("Helvetica-Bold", 14)
        c.drawCentredString(x_center, y, "TICKET DE VENTA")
        y -= 6 * mm

        from core.settings import settings

        def _dato(attr: str, clave: str) -> str:
            return (str(getattr(settings, attr, "") or "").strip()
                    or str(self.db_manager.get_config_value(clave) or "").strip())

        nombre_negocio = _dato("nombre_negocio", "NOMBRE_NEGOCIO")
        direccion = _dato("direccion_negocio", "DIRECCION")
        cuit = (_dato("cuit", "CUIT") or _dato("afip_cuit", "AFIP_CUIT")
                or str(config.CUIT or "").strip())
        condicion_iva = _dato("condicion_iva", "CONDICION_IVA")
        ingresos_brutos = _dato("ingresos_brutos", "INGRESOS_BRUTOS")
        inicio_actividades = _dato("inicio_actividades", "INICIO_ACTIVIDADES")

        c.setFont("Helvetica-Bold", 10)
        if nombre_negocio:
            c.drawCentredString(x_center, y, nombre_negocio)
            y -= 5 * mm

        c.setFont("Helvetica", 8)
        for dato in (direccion,
                     f"CUIT: {cuit}" if cuit else "",
                     f"Cond. IVA: {condicion_iva}" if condicion_iva else "",
                     f"Ing. Brutos: {ingresos_brutos}" if ingresos_brutos else "",
                     f"Inicio act.: {inicio_actividades}" if inicio_actividades else ""):
            if dato:
                c.drawCentredString(x_center, y, dato)
                y -= 4 * mm
        y -= 2 * mm

        c.line(margen, y, ancho - margen, y)
        y -= 5 * mm

        c.setFont("Helvetica", 8)
        fecha_actual = datetime.now().strftime("%d/%m/%Y %H:%M")
        c.drawString(margen, y, f"Fecha: {fecha_actual}")
        y -= 4 * mm
        c.drawString(margen, y, f"Venta #: {venta_id}")
        y -= 6 * mm

        if numero_factura:
            tipo_factura = self.db_manager.get_config_value("AFIP_TIPO_FACTURA") or "C"
            c.setFont("Helvetica-Bold", 10)
            c.drawString(margen, y, f"FACTURA {tipo_factura}")
            y -= 4 * mm
            c.setFont("Helvetica", 8)
            c.drawString(margen, y, f"N°: {config.PUNTO_VENTA:04d}-{numero_factura:08d}")
            y -= 4 * mm
            c.drawString(margen, y, "Consumidor Final")
            y -= 6 * mm

            if cae:
                c.setFont("Helvetica", 7)
                c.drawString(margen, y, f"CAE: {cae}")
                y -= 3 * mm
                c.drawString(margen, y, f"Vto CAE: {vencimiento_cae}")
                y -= 6 * mm

        c.line(margen, y, ancho - margen, y)
        y -= 5 * mm

        c.setFont("Helvetica-Bold", 8)
        c.drawString(margen, y, "Producto")
        c.drawRightString(ancho - margen - 20 * mm, y, "Cant")
        c.drawRightString(ancho - margen, y, "Subtotal")
        y -= 4 * mm
        c.line(margen, y, ancho - margen, y)
        y -= 4 * mm

        c.setFont("Helvetica", 7)
        total = 0
        for item in carrito:
            desc = item["descripcion"][:35]
            c.drawString(margen, y, desc)
            c.drawRightString(ancho - margen - 20 * mm, y, f"{item['cantidad']}")
            c.drawRightString(ancho - margen, y, f"${item['subtotal']:.2f}")
            total += item["subtotal"]
            y -= 4 * mm

        y -= 2 * mm
        c.line(margen, y, ancho - margen, y)
        y -= 5 * mm

        c.setFont("Helvetica-Bold", 11)
        c.drawString(margen, y, "TOTAL:")
        c.drawRightString(ancho - margen, y, f"${total:.2f}")
        y -= 8 * mm

        if numero_factura and cae:
            qr_img = self.generar_qr_afip(numero_factura, cae, vencimiento_cae, total)
            if qr_img:
                qr_size = 40 * mm
                qr_x = (ancho - qr_size) / 2
                c.drawImage(qr_img, qr_x, y - qr_size, width=qr_size, height=qr_size)
                y -= qr_size + 4 * mm
                c.setFont("Helvetica", 6)
                c.drawCentredString(x_center, y, "Escanea para verificar en AFIP")
                y -= 6 * mm

        c.setFont("Helvetica", 7)
        c.drawCentredString(x_center, y, "Gracias por su compra!")
        y -= 4 * mm

        c.save()
        print(f"📄 Ticket generado: {filename}")
        return filepath

    def emitir_y_generar_ticket(self, venta_id, carrito, medio_pago="efectivo", generar_pdf=True) -> dict:
        """Emite factura y genera ticket PDF en un solo paso.

        Returns:
            dict con resultado completo.
        """
        print(f"🎯 Procesando venta #{venta_id} - Medio: {medio_pago}")

        result = self.emitir_factura_venta(venta_id, carrito, medio_pago)
        if not result["success"]:
            return result

        pdf_path = None
        if generar_pdf:
            try:
                pdf_path = self.generar_ticket_pdf(
                    venta_id,
                    carrito,
                    result.get("numero_factura"),
                    result.get("cae"),
                    result.get("vencimiento_cae"),
                )
            except Exception as e:  # noqa: BLE001
                result["pdf_error"] = f"Error generando PDF: {str(e)}"
                print(f"⚠️ Error en PDF: {str(e)}")

        result["pdf_path"] = pdf_path
        return result

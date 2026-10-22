"""Cliente WSFE (facturación electrónica AFIP) — reconstruido del build.

Maneja la emisión de comprobantes electrónicos.
Incluye SSLAdapter con ``DEFAULT@SECLEVEL=1``.
"""
from __future__ import annotations

import ssl
from datetime import datetime

import requests
from requests import Session
from zeep import Client
from zeep.transports import Transport

import configwsfe as config

ctx = ssl.create_default_context()
ctx.set_ciphers("DEFAULT@SECLEVEL=1")
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


class SSLAdapter(requests.adapters.HTTPAdapter):
    """Adaptador que inyecta el contexto SSL personalizado."""

    def init_poolmanager(self, *args, **kwargs):
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, *args, **kwargs):
        kwargs["ssl_context"] = ctx
        return super().proxy_manager_for(*args, **kwargs)


class WSFEClient:
    """Cliente para operaciones de facturación electrónica con WSFE."""

    def __init__(self, token, sign):
        self.url = config.WSFE_URL
        self.token = token
        self.sign = sign
        self.cuit = config.CUIT

        session = Session()
        session.mount("https://", SSLAdapter())
        session.verify = False
        import urllib3

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        transport = Transport(session=session, timeout=30)
        self.client = Client(self.url, transport=transport)

    def _create_auth(self) -> dict:
        return {"Token": self.token, "Sign": self.sign, "Cuit": self.cuit}

    def get_ultimo_comprobante(self, punto_venta, tipo_cbte) -> dict:
        """Retorna el último número de comprobante autorizado por AFIP."""
        try:
            auth = self._create_auth()
            response = self.client.service.FECompUltimoAutorizado(
                Auth=auth, PtoVta=punto_venta, CbteTipo=tipo_cbte
            )
            if hasattr(response, "Errors") and response.Errors:
                return {"success": False, "message": response.Errors.Err[0].Msg}
            return {"success": True, "ultimo_nro": response.CbteNro}
        except Exception as e:  # noqa: BLE001
            return {"success": False, "message": str(e)}

    def emitir_factura(self, datos_factura: dict) -> dict:
        """Emite una factura electrónica y maneja la respuesta de AFIP."""
        try:
            auth = self._create_auth()
            ultimo = self.get_ultimo_comprobante(
                datos_factura["punto_venta"], datos_factura["tipo_cbte"]
            )
            if not ultimo["success"]:
                print(f"❌ Error obteniendo último comprobante: {ultimo['message']}")
                return ultimo

            siguiente_nro = ultimo["ultimo_nro"] + 1

            importe_neto = round(datos_factura["importe_neto"], 2)
            if datos_factura["iva_porcentaje"] == config.IVA_21_PORCIENTO:
                importe_iva = round(importe_neto * 0.21, 2)
            elif datos_factura["iva_porcentaje"] == config.IVA_10_5_PORCIENTO:
                importe_iva = round(importe_neto * 0.105, 2)
            else:
                importe_iva = 0
            importe_total = round(importe_neto + importe_iva, 2)
            fecha_cbte = datetime.now().strftime("%Y%m%d")

            print("📊 Datos de factura:")
            print(f"   - Número: {siguiente_nro}")
            print(f"   - Importe Neto: ${importe_neto:.2f}")
            print(f"   - IVA: ${importe_iva:.2f}")
            print(f"   - Total: ${importe_total:.2f}")
            print(f"   - Fecha: {fecha_cbte}")

            factory = self.client.type_factory("ns0")

            cabecera = factory.FECAECabRequest(
                CantReg=1,
                PtoVta=datos_factura["punto_venta"],
                CbteTipo=datos_factura["tipo_cbte"],
            )

            detalle = factory.FECAEDetRequest(
                Concepto=datos_factura.get("concepto", config.CONCEPTO_PRODUCTOS),
                DocTipo=datos_factura.get("tipo_doc", config.DOC_TIPO_CONSUMIDOR_FINAL),
                DocNro=datos_factura.get("nro_doc", 0),
                CbteDesde=siguiente_nro,
                CbteHasta=siguiente_nro,
                CbteFch=fecha_cbte,
                ImpTotal=importe_total,
                ImpTotConc=0,
                ImpNeto=importe_neto,
                ImpOpEx=0,
                ImpIVA=importe_iva,
                ImpTrib=0,
                MonId=datos_factura.get("moneda", config.MONEDA_PESOS),
                MonCotiz=datos_factura.get("cotizacion", 1),
            )

            if importe_iva > 0:
                alic_iva = factory.AlicIva(
                    Id=datos_factura["iva_porcentaje"],
                    BaseImp=importe_neto,
                    Importe=importe_iva,
                )
                detalle.Iva = factory.ArrayOfAlicIva([alic_iva])

            solicitud = factory.FECAERequest(
                FeCabReq=cabecera,
                FeDetReq=factory.ArrayOfFECAEDetRequest([detalle]),
            )

            print("📤 Enviando solicitud a AFIP...")
            response = self.client.service.FECAESolicitar(Auth=auth, FeCAEReq=solicitud)
            print("📥 Respuesta AFIP recibida")
            print(f"   - Tiene FeDetResp: {hasattr(response, 'FeDetResp')}")

            if hasattr(response, "Errors") and response.Errors:
                print("❌ Errores generales:")
                for err in response.Errors.Err:
                    print(f"   - Código {err.Code}: {err.Msg}")

            if hasattr(response, "FeDetResp") and response.FeDetResp:
                detalle_resp = response.FeDetResp.FECAEDetResponse[0]
                print("📋 Detalle respuesta:")
                print(f"   - Resultado: {detalle_resp.Resultado}")
                print(f"   - CBTEDesde: {getattr(detalle_resp, 'CbteDesde', 'N/A')}")
                print(f"   - CBTEHasta: {getattr(detalle_resp, 'CbteHasta', 'N/A')}")

                if detalle_resp.Resultado == "A":
                    print(f"   - CAE: {detalle_resp.CAE}")
                    print(f"   - Vencimiento: {detalle_resp.CAEFchVto}")
                    return {
                        "success": True,
                        "numero": siguiente_nro,
                        "cae": detalle_resp.CAE,
                        "vencimiento_cae": detalle_resp.CAEFchVto,
                        "message": f"Factura {siguiente_nro} autorizada",
                    }

                errores = []
                if hasattr(detalle_resp, "Observaciones") and detalle_resp.Observaciones:
                    print("⚠️ Observaciones AFIP:")
                    for obs in detalle_resp.Observaciones.Obs:
                        error_msg = f"Código {obs.Code}: {obs.Msg}"
                        print(f"   - {error_msg}")
                        errores.append(error_msg)
                if not errores:
                    errores.append("Factura rechazada sin mensaje de error específico")
                return {"success": False, "message": f"Rechazada: {' | '.join(errores)}"}

            print("❌ Respuesta vacía o inválida de AFIP")
            return {"success": False, "message": "Respuesta vacía de AFIP"}
        except Exception as e:  # noqa: BLE001
            print(f"💥 Excepción en emitir_factura: {str(e)}")
            import traceback

            traceback.print_exc()
            return {"success": False, "message": f"Error crítico: {str(e)}"}

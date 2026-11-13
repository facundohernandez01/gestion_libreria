"""Adaptador aislado para la nueva Orders API QR de Mercado Pago.

NO modifica aún los cobros existentes: su activación requiere persistir
order_id antes de exponer el QR y recuperar operaciones tras reinicios.
Nunca interpreta ausencia de resultados como ausencia definitiva de pago.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import quote
from uuid import NAMESPACE_URL, uuid5

import requests

BASE_URL = "https://api.mercadopago.com/v1/orders"


def _amount(value) -> Decimal:
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number <= 0:
            raise ValueError("Importe inválido")
        return number.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("Importe inválido") from exc


class MercadoPagoOrdersV1:
    def __init__(self, token_provider=None, http=None, timeout=15):
        self.token_provider = token_provider or self._token_actual
        self.http = http or requests
        self.timeout = timeout

    @staticmethod
    def _token_actual():
        from services.mercadopago_service import mp_service
        return mp_service.credenciales()[0]

    def _headers(self, operation: str = "", reference: str = ""):
        token = self.token_provider()
        if not token:
            raise ValueError("Mercado Pago no tiene Access Token autorizado")
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        if operation:
            # La misma operación sobre el mismo checkout reutiliza la clave
            # ante timeouts. Crear y cancelar usan claves distintas.
            headers["X-Idempotency-Key"] = str(
                uuid5(NAMESPACE_URL, f"intrashop:{reference}:{operation}")
            )
        return headers

    def crear(self, reference: str, pos_external_id: str, items: list[dict], total):
        """POST v1/orders. Retorna order_id solo si la respuesta coincide.

        Tras un timeout, NO cambiar de referencia ni usar otra operación:
        debe reintentarse con los mismos datos e idempotency key.
        """
        if not reference or len(reference) > 64 or not all(
            char.isalnum() and char.isascii() or char in "_-" for char in reference
        ):
            raise ValueError("Referencia inválida")
        if not pos_external_id or not items:
            raise ValueError("Falta caja o carrito")
        expected = _amount(total)
        details = []
        calculated = Decimal("0")
        for item in items:
            cantidad = int(item["cantidad"])
            unit = _amount(item["precio_unitario"])
            if cantidad <= 0:
                raise ValueError("Cantidad inválida")
            calculated += unit * cantidad
            details.append({
                "title": str(item.get("descripcion") or "Producto")[:150],
                "unit_price": f"{unit:.2f}",
                "quantity": cantidad,
                "unit_measure": "unit",
            })
        if calculated.quantize(Decimal("0.01")) != expected:
            raise ValueError("El total no coincide con los productos")
        body = {
            "type": "qr",
            "total_amount": f"{expected:.2f}",
            "description": "Compra IntraShop",
            "external_reference": reference,
            "expiration_time": "PT5M",
            "config": {"qr": {"external_pos_id": pos_external_id, "mode": "static"}},
            "transactions": {"payments": [{"amount": f"{expected:.2f}"}]},
            "items": details,
        }
        try:
            response = self.http.post(
                BASE_URL,
                headers=self._headers("create", reference),
                json=body,
                timeout=self.timeout,
            )
            if response.status_code != 201:
                return {"estado": "uncertain", "motivo": f"Creación QR HTTP {response.status_code}"}
            data = response.json()
            if not isinstance(data, dict):
                return {"estado": "uncertain", "motivo": "Respuesta QR inválida"}
            if (
                not data.get("id")
                or data.get("external_reference") != reference
                or _amount(data.get("total_amount")) != expected
            ):
                return {"estado": "uncertain", "motivo": "Orden creada sin identificación verificable"}
            return {"estado": "created", "order_id": str(data["id"])}
        except (requests.RequestException, ValueError, KeyError, TypeError):
            return {"estado": "uncertain", "motivo": "Creación QR sin confirmación"}

    def consultar(self, order_id: str, reference: str, total):
        """Consulta por order_id y valida referencia/importe antes de decidir."""
        if not order_id or not reference:
            return {"estado": "uncertain", "motivo": "Falta ID de orden o referencia"}
        try:
            response = self.http.get(
                f"{BASE_URL}/{quote(str(order_id), safe='')}",
                headers=self._headers(), timeout=self.timeout,
            )
            if response.status_code != 200:
                return {"estado": "uncertain", "motivo": f"Consulta QR HTTP {response.status_code}"}
            data = response.json()
            if (
                not isinstance(data, dict)
                or str(data.get("id") or "") != str(order_id)
                or data.get("external_reference") != reference
                or _amount(data.get("total_amount")) != _amount(total)
            ):
                return {"estado": "uncertain", "motivo": "La orden no coincide con la venta"}
            estado = data.get("status")
            detalle = data.get("status_detail")
            if estado == "processed" and detalle == "processed":
                # El status_detail de la order es 'processed'. La
                # acreditación corresponde al pago dentro de transactions.
                pagos = (data.get("transactions") or {}).get("payments")
                if not isinstance(pagos, list) or len(pagos) != 1:
                    return {"estado": "uncertain", "motivo": "Transacción de pago no verificable"}
                pago = pagos[0]
                if (
                    not isinstance(pago, dict)
                    or pago.get("status") != "processed"
                    or pago.get("status_detail") != "accredited"
                    or _amount(pago.get("amount")) != _amount(total)
                ):
                    return {"estado": "uncertain", "motivo": "Pago no acreditado por importe correcto"}
                return {"estado": "approved", "order_id": order_id}
            if estado == "canceled" and detalle == "canceled":
                return {"estado": "cancelled", "order_id": order_id}
            if estado == "expired" and detalle == "expired":
                return {"estado": "expired", "order_id": order_id}
            if estado == "created":
                return {"estado": "pending", "order_id": order_id}
            return {"estado": "uncertain", "motivo": "Estado de orden no definitivo"}
        except (requests.RequestException, ValueError, KeyError, TypeError):
            return {"estado": "uncertain", "motivo": "No se pudo verificar la orden"}

    def cancelar(self, order_id: str, reference: str, total):
        """Cancela con idempotencia y SIEMPRE consulta estado final de la order.

        Un 409 puede indicar orden ya procesada. Nunca se interpreta como
        cancelación hasta observar status=canceled para el mismo order_id.
        """
        if not order_id or not reference:
            return {"estado": "uncertain", "motivo": "Falta ID o referencia"}
        try:
            self.http.post(
                f"{BASE_URL}/{quote(str(order_id), safe='')}/cancel",
                headers=self._headers("cancel", reference),
                timeout=self.timeout,
            )
        except requests.RequestException:
            pass
        return self.consultar(order_id, reference, total)

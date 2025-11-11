import requests
import time
import json

ACCESS_TOKEN = "APP_USR-2575300947252064-111011-7baddd566dc2eee1112cb9f85e829a87-2674497459"
USER_ID = "2674497459"

HEADERS = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Content-Type": "application/json"
}

ultima_referencia = None


def crear_orden(external_pos_id, external_store_id, monto):
    """Crea una orden QR en Mercado Pago"""
    global ultima_referencia
    ultima_referencia = f"ORDER_{int(time.time())}"
    
    url = f"https://api.mercadopago.com/instore/qr/seller/collectors/{USER_ID}/stores/{external_store_id}/pos/{external_pos_id}/orders"
    payload = {
        "external_reference": ultima_referencia,
        "title": "Venta en local",
        "description": f"Cobro de ${monto}",
        "total_amount": float(monto),
        "items": [
            {
                "sku_number": "LOCAL001",
                "category": "marketplace",
                "title": "Venta en local",
                "description": "Cobro en mostrador",
                "unit_price": float(monto),
                "quantity": 1,
                "unit_measure": "unit",
                "total_amount": float(monto)
            }
        ]
    }

    resp = requests.put(url, headers=HEADERS, json=payload)
    return resp.status_code == 204


def verificar_estado(external_pos_id, timeout=300, intervalo=5):
    """
    Consulta el estado del QR hasta que se pague o expire.
    Devuelve True si se detecta el pago.
    """
    url = f"https://api.mercadopago.com/instore/qr/seller/collectors/{USER_ID}/pos/{external_pos_id}/orders"
    inicio = time.time()

    while (time.time() - inicio) < timeout:
        resp = requests.get(url, headers=HEADERS)

        if resp.status_code == 200:
            data = resp.json()
            estado = data.get("order_status", "unknown")
            pagado = data.get("paid_amount", 0)
            total = data.get("total_amount", 0)

            if estado == "paid" or pagado >= total:
                return True

        elif resp.status_code == 404:
            return consultar_ultimo_pago_por_referencia()

        time.sleep(intervalo)

    return False


def consultar_ultimo_pago_por_referencia():
    """Consulta el último pago por la external_reference guardada."""
    global ultima_referencia
    if not ultima_referencia:
        return False

    url = f"https://api.mercadopago.com/v1/payments/search?external_reference={ultima_referencia}"
    resp = requests.get(url, headers=HEADERS)
    
    if resp.status_code == 200:
        data = resp.json()
        resultados = data.get("results", [])
        if resultados:
            pago = resultados[0]
            estado = pago.get("status")
            return estado == "approved"
    return False

import requests
import time
import json

# === CONFIGURACIÓN ===
ACCESS_TOKEN = "APP_USR-2575300947252064-111011-7baddd566dc2eee1112cb9f85e829a87-2674497459"
USER_ID = "2674497459"

HEADERS = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Content-Type": "application/json"
}

ultima_referencia = None


# --- Utilidad para registrar mensajes (callback desde Flet opcional) ---
def log(msg, cb=None):
    """Si se pasa un callback (desde Flet), lo usa; sino imprime."""
    if cb:
        try:
            cb(msg)
        except Exception:
            print(msg)
    else:
        print(msg)


# --- CREAR ORDEN ---
def crear_orden(external_pos_id, external_store_id, monto, cb=None):
    """Crea una orden QR dinámica en Mercado Pago"""
    global ultima_referencia
    ultima_referencia = f"ORDER_{int(time.time())}"
    url = (
        f"https://api.mercadopago.com/instore/qr/seller/collectors/"
        f"{USER_ID}/stores/{external_store_id}/pos/{external_pos_id}/orders"
    )
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
                "total_amount": float(monto),
            }
        ],
    }

    log(f"📤 Creando orden QR por ${monto:.2f}...", cb)
    resp = requests.put(url, headers=HEADERS, json=payload)

    if resp.status_code == 204:
        log("✅ Orden creada exitosamente. Esperando pago del cliente...", cb)
        return True
    else:
        log(f"❌ Error creando orden ({resp.status_code}) - {resp.text}", cb)
        return False


# --- VERIFICAR ESTADO ---
def verificar_estado(external_pos_id, timeout=300, intervalo=5, cb=None):
    """
    Consulta el estado del POS QR hasta que la orden sea pagada o expire.
    Devuelve True si se detecta un pago exitoso.
    """
    url = (
        f"https://api.mercadopago.com/instore/qr/seller/collectors/"
        f"{USER_ID}/pos/{external_pos_id}/orders"
    )
    inicio = time.time()
    intentos = 0

    log(f"⏳ Monitoreando pago en POS {external_pos_id}...", cb)
    log(f"   Consultando cada {intervalo}s (máx {timeout//intervalo} intentos)", cb)

    while (time.time() - inicio) < timeout:
        intentos += 1
        resp = requests.get(url, headers=HEADERS)

        # OK
        if resp.status_code == 200:
            data = resp.json()
            estado = data.get("order_status", "unknown")
            pagado = data.get("paid_amount", 0)
            total = data.get("total_amount", 0)
            log(f"💳 Esperando pago {intentos}: Estado={estado} | Pagado ${pagado}/{total}", cb)

            if estado == "paid" or pagado >= total:
                log("✅ ¡Pago recibido correctamente!", cb)
                pagos = data.get("payments", [])
                if pagos:
                    pago = pagos[0]
                    log(f"💳 Payment ID: {pago.get('id')} | Estado: {pago.get('status')}", cb)
                return True

        # Orden cerrada
        elif resp.status_code == 404:
            log("📭 La orden ya no está activa. Verificando último pago...", cb)
            return consultar_ultimo_pago_por_referencia(cb)

        # Error inesperado
        elif resp.status_code >= 400:
            log(f"⚠️ Error {resp.status_code}: {resp.text}", cb)

        time.sleep(intervalo)

    log("⏰ Tiempo de espera agotado. La orden sigue abierta.", cb)
    return False


# --- CONSULTAR ÚLTIMO PAGO POR REFERENCIA ---
def consultar_ultimo_pago_por_referencia(cb=None):
    """Busca el último pago asociado a la external_reference de la última orden."""
    global ultima_referencia
    if not ultima_referencia:
        log("⚠️ No hay external_reference guardada para buscar pago.", cb)
        return False

    url = f"https://api.mercadopago.com/v1/payments/search?external_reference={ultima_referencia}"
    resp = requests.get(url, headers=HEADERS)

    if resp.status_code == 200:
        data = resp.json()
        resultados = data.get("results", [])
        if resultados:
            pago = resultados[0]
            estado = pago.get("status")
            monto = pago.get("transaction_amount")
            log(f"💰 Pago detectado: ID={pago.get('id')} | Estado={estado} | Monto=${monto}", cb)
            return estado == "approved"
        else:
            log("⚠️ No se encontraron pagos recientes con esa referencia.", cb)
    else:
        log(f"⚠️ Error consultando pagos ({resp.status_code}) - {resp.text}", cb)

    return False

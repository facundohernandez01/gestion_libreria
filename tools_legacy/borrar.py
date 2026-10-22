import requests
import time
import json
import requests

ACCESS_TOKEN = "APP_USR-***REVOCAR***"
USER_ID = "***"
HEADERS = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Content-Type": "application/json"
}

# IDs que ya conoces
pos_id = 12345678      # ID numérico del POS
store_id = 71528575    # ID numérico del Store


# Eliminar Store
print("🗑 Eliminando Store...")
resp_store = requests.delete(f"https://api.mercadopago.com/stores/{store_id}", headers=HEADERS)
print(f"Store: {resp_store.status_code} - {resp_store.text}")
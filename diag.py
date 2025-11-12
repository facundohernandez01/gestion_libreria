import requests
import json
import time

# === TUS CREDENCIALES DE PRODUCCIÓN ===
ACCESS_TOKEN = "APP_USR-8451402943469154-111206-cd551da9da9595bb3f9e81186ff6da59-135098517"  # 👈 Reemplaza con tu token
USER_ID = "135098517"  # 👈 Reemplaza con tu User ID

HEADERS = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Content-Type": "application/json"
}

print("=" * 70)
print("🔧 REPARACIÓN DE CONFIGURACIÓN - PRODUCCIÓN")
print("=" * 70)

# ============================================
# PASO 1: ELIMINAR POS INVÁLIDO
# ============================================
print("\n🗑️ PASO 1: Eliminando POS inválido (ID: 4032377)...")

pos_id = 4032377
url_delete_pos = f"https://api.mercadopago.com/pos/{pos_id}"
resp = requests.delete(url_delete_pos, headers=HEADERS)

if resp.status_code in [200, 204]:
    print("✅ POS eliminado correctamente")
else:
    print(f"⚠️ Error eliminando POS: {resp.status_code}")
    print(resp.text)
    print("   Puedes continuar de todas formas...")

# ============================================
# PASO 2: ELIMINAR STORE INVÁLIDO
# ============================================
print("\n🗑️ PASO 2: Eliminando Store inválido (ID: 44554839)...")

store_id = 44554839
url_delete_store = f"https://api.mercadopago.com/stores/{store_id}"
resp = requests.delete(url_delete_store, headers=HEADERS)

if resp.status_code in [200, 204]:
    print("✅ Store eliminado correctamente")
else:
    print(f"⚠️ Error eliminando Store: {resp.status_code}")
    print(resp.text)
    print("   Si da error, primero elimina todos los POS de este Store")

# Esperar un momento para que se procesen las eliminaciones
print("\n⏳ Esperando 3 segundos...")
time.sleep(3)

# ============================================
# PASO 3: CREAR STORE VÁLIDO
# ============================================
print("\n🏪 PASO 3: Creando Store válido en producción...")

url_create_store = f"https://api.mercadopago.com/users/{USER_ID}/stores"

# CRÍTICO: external_id debe ser único y NO "default"
external_store_id = f"STORE{int(time.time())}"

payload_store = {
    "name": "Mi Local",  # 👈 Cambia por el nombre de tu negocio
    "external_id": external_store_id,  # 👈 CRÍTICO
    "location": {
        "street_number": "3456",
        "street_name": "Calle Corrientes",
        "city_name": "Rosario",
        "state_name": "Santa Fe",
        "latitude": -32.9468,
        "longitude": -60.6393,
        "reference": "Local comercial"
    }
}

print("\n📤 Creando Store con payload:")
print(json.dumps(payload_store, indent=2))

resp = requests.post(url_create_store, headers=HEADERS, json=payload_store)

print(f"\n📥 Respuesta: {resp.status_code}")

if resp.status_code in [200, 201]:
    store_data = resp.json()
    print("\n✅ ¡Store creado exitosamente!")
    print(f"   ID: {store_data['id']}")
    print(f"   External ID: {store_data['external_id']}")
    print(f"   Nombre: {store_data['name']}")
    
    new_store_id = store_data['id']
    new_external_store_id = store_data['external_id']
    
else:
    print(f"\n❌ Error creando Store: {resp.status_code}")
    print(resp.text)
    print("\n⚠️ No se puede continuar sin Store válido")
    exit()

# Esperar un momento
print("\n⏳ Esperando 2 segundos...")
time.sleep(2)

# ============================================
# PASO 4: CREAR POS VÁLIDO
# ============================================
print("\n🖥️ PASO 4: Creando POS válido con fixed_amount=True...")

url_create_pos = "https://api.mercadopago.com/pos"

# CRÍTICO: external_id debe ser único y NO "default"
# NO uses guion bajo (_) en external_id, solo números y letras
external_pos_id = f"POS{int(time.time())}"

payload_pos = {
    "name": "Caja Principal",  # 👈 Nombre de tu punto de venta
    "external_id": external_pos_id,  # 👈 CRÍTICO: sin guiones bajos
    "store_id": new_store_id,  # 👈 ID del store que acabamos de crear
    "fixed_amount": True,  # 👈 Correcto para tu caso de uso
    "category": 621102  # Retail
}

print("\n📤 Creando POS con payload:")
print(json.dumps(payload_pos, indent=2))

resp = requests.post(url_create_pos, headers=HEADERS, json=payload_pos)

print(f"\n📥 Respuesta: {resp.status_code}")

if resp.status_code in [200, 201]:
    pos_data = resp.json()
    print("\n✅ ¡POS creado exitosamente!")
    print(f"   ID: {pos_data['id']}")
    print(f"   External ID: {pos_data['external_id']}")
    print(f"   Fixed Amount: {pos_data.get('fixed_amount')}")
    print(f"   Status: {pos_data.get('status')}")
    
    if 'qr' in pos_data and 'image' in pos_data['qr']:
        qr_url = pos_data['qr']['image']
        print(f"\n   📱 QR URL: {qr_url}")
        print("\n   ⚠️ IMPORTANTE:")
        print("   1. Descarga e imprime este QR")
        print("   2. Es el QR que tus clientes deben escanear")
        print("   3. Guarda esta URL en tu base de datos")
    
    new_external_pos_id = pos_data['external_id']
    
    # ============================================
    # PASO 5: GUARDAR CONFIGURACIÓN
    # ============================================
    print("\n" + "=" * 70)
    print("💾 CONFIGURACIÓN PARA TU APP")
    print("=" * 70)
    print(f"\nGuarda estos valores en tu base de datos:\n")
    print(f"EXTERNAL_STORE_ID = \"{new_external_store_id}\"")
    print(f"EXTERNAL_POS_ID = \"{new_external_pos_id}\"")
    print(f"QR_URL = \"{qr_url}\"")
    print(f"\n🔧 Ejecuta en tu app:")
    print(f"""
from database_manager import DatabaseManager
db = DatabaseManager()
db.set_config("EXTERNAL_STORE_ID", "{new_external_store_id}")
db.set_config("EXTERNAL_POS_ID", "{new_external_pos_id}")
db.set_config("QR_URL", "{qr_url}")
print("✅ Configuración guardada")
""")
    
else:
    print(f"\n❌ Error creando POS: {resp.status_code}")
    print(resp.text)
    
    # Posibles causas de error
    print("\n🔍 Posibles causas:")
    if resp.status_code == 400:
        print("   - El external_id ya existe (intenta ejecutar el script de nuevo)")
        print("   - Algún campo del payload es inválido")
        print("   - El store_id no es correcto")
    elif resp.status_code == 401:
        print("   - Token de acceso inválido o expirado")
    elif resp.status_code == 404:
        print("   - El store_id no existe")

print("\n" + "=" * 70)
print("✅ PROCESO COMPLETADO")
print("=" * 70)


# ============================================
# FUNCIÓN PARA PROBAR EL COBRO
# ============================================
def probar_cobro(external_pos_id, external_store_id, monto=100):
    """Prueba crear una orden de cobro"""
    print(f"\n🧪 PRUEBA: Creando orden de ${monto}")
    
    order_ref = f"TEST{int(time.time())}"
    
    url = (
        f"https://api.mercadopago.com/instore/qr/seller/collectors/"
        f"{USER_ID}/stores/{external_store_id}/pos/{external_pos_id}/orders"
    )
    
    payload = {
        "external_reference": order_ref,
        "title": "Venta de prueba",
        "description": f"Cobro de ${monto}",
        "total_amount": float(monto),
        "items": [
            {
                "sku_number": "TEST001",
                "category": "marketplace",
                "title": "Producto de prueba",
                "description": "Item de prueba",
                "unit_price": float(monto),
                "quantity": 1,
                "unit_measure": "unit",
                "total_amount": float(monto),
            }
        ],
    }
    
    print(f"\n📤 Enviando orden...")
    resp = requests.put(url, headers=HEADERS, json=payload, timeout=15)
    
    print(f"📥 Respuesta: {resp.status_code}")
    
    if resp.status_code == 204:
        print("\n✅ ¡ORDEN CREADA EXITOSAMENTE!")
        print(f"   External Reference: {order_ref}")
        print(f"\n   📱 El cliente debe escanear el QR estático")
        print(f"   💰 Monto: ${monto}")
        print(f"\n   ⚠️ IMPORTANTE:")
        print(f"   1. Si ya tenías el QR escaneado, sal y vuelve a escanearlo")
        print(f"   2. Debería aparecer el monto ${monto} para pagar")
        return True
    else:
        print(f"\n❌ Error creando orden: {resp.status_code}")
        print(resp.text)
        return False


print("\n\n🧪 Para probar el cobro, ejecuta:")
print(f'probar_cobro("{new_external_pos_id}", "{new_external_store_id}", 150)')
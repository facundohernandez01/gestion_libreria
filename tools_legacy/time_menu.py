import requests
import time
import json

# --- CONFIGURACIÓN ---
ACCESS_TOKEN = "APP_USR-***REVOCAR***"
USER_ID = "***"

HEADERS = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Content-Type": "application/json"
}

# --- DIAGNÓSTICO: Verificar credenciales ---
def verificar_credenciales():
    """Verifica que el access token sea válido"""
    url = f"https://api.mercadopago.com/v1/users/{USER_ID}"
    resp = requests.get(url, headers=HEADERS)
    
    if resp.status_code == 200:
        data = resp.json()
        print(f"✅ Token válido")
        print(f"   Usuario: {data.get('first_name')} {data.get('last_name')}")
        print(f"   Email: {data.get('email')}")
        print(f"   ID: {data.get('id')}")
        return True
    else:
        print(f"❌ Token inválido: {resp.status_code} - {resp.text}")
        return False

# --- PASO 1: GESTIÓN DE TIENDA ---
def listar_tiendas():
    """Lista todas las tiendas"""
    url = f"https://api.mercadopago.com/users/{USER_ID}/stores/search"
    resp = requests.get(url, headers=HEADERS)
    
    if resp.status_code == 200:
        stores = resp.json().get('results', [])
        print(f"\n📍 Tiendas encontradas: {len(stores)}")
        for store in stores:
            print(f"  - Nombre: {store['name']}")
            print(f"    ID: {store['id']}")
            print(f"    External ID: {store.get('external_id', 'N/A')}")
        return stores
    else:
        print(f"❌ Error listando tiendas: {resp.status_code} - {resp.text}")
        return []

def crear_tienda():
    """Crea una tienda nueva"""
    url = f"https://api.mercadopago.com/users/{USER_ID}/stores"
    payload = {
        "name": "Mi Negocio",
        "business_hours": {
            "monday": [{"open": "09:00", "close": "18:00"}],
            "tuesday": [{"open": "09:00", "close": "18:00"}],
            "wednesday": [{"open": "09:00", "close": "18:00"}],
            "thursday": [{"open": "09:00", "close": "18:00"}],
            "friday": [{"open": "09:00", "close": "18:00"}]
        },
        "location": {
            "street_number": "123",
            "street_name": "Calle Principal",
            "city_name": "Rosario",
            "state_name": "Santa Fe",
            "latitude": -34.0,
            "longitude": -64.0,
            "reference": "Referencia"
        },
        "external_id": f"STORE_{int(time.time())}"
    }
    
    resp = requests.post(url, headers=HEADERS, json=payload)
    if resp.status_code in [200, 201]:
        data = resp.json()
        print(f"✅ Tienda creada: {data['name']} (ID: {data['id']})")
        return data
    else:
        print(f"❌ Error creando tienda: {resp.status_code} - {resp.text}")
        return None

# --- PASO 2: GESTIÓN DE POS ---
def listar_pos():
    """Lista todos los POS y muestra su estado real"""
    url = f"https://api.mercadopago.com/pos"
    resp = requests.get(url, headers=HEADERS)

    if resp.status_code != 200:
        print(f"❌ Error listando POS: {resp.status_code} - {resp.text}")
        return []

    pos_list = resp.json().get('results', [])
    print(f"\n🖥️  POS encontrados: {len(pos_list)}")

    for pos in pos_list:
        pos_id = pos['id']
        # Consultar estado real del POS
        url_detalle = f"https://api.mercadopago.com/pos/{pos_id}"
        detalle = requests.get(url_detalle, headers=HEADERS)

        status_real = "N/A"
        if detalle.status_code == 200:
            detalle_data = detalle.json()
            status_real = detalle_data.get("status", "N/A")

        print(f"\n  Nombre: {pos['name']}")
        print(f"  ID: {pos_id}")
        print(f"  External ID: {pos.get('external_id', 'N/A')}")
        print(f"  Store ID: {pos.get('store_id')}")
        print(f"  Fixed Amount: {pos.get('fixed_amount')}")
        print(f"  Status: {status_real}")
        if 'qr' in pos:
            print(f"  QR Image: {pos['qr'].get('image')}")

    return pos_list

def crear_pos(store_id):
    """Crea un POS en una tienda"""
    url = "https://api.mercadopago.com/pos"
    payload = {
        "name": f"Caja Principal {int(time.time())}",
        "fixed_amount": True,  # CRÍTICO: debe ser False para montos variables
        "category": 621102,
        "store_id": store_id,
        "external_id": f"POS{int(time.time())}"  # ← sin guion bajo
    }

    print(f"\n📤 Creando POS con payload:")
    print(json.dumps(payload, indent=2))

    resp = requests.post(url, headers=HEADERS, json=payload)
    print(f"\n📥 Respuesta: {resp.status_code}")
    print(resp.text)

    if resp.status_code in [200, 201]:
        data = resp.json()
        print(f"\n✅ POS creado exitosamente!")
        print(f"   ID: {data['id']}")
        print(f"   External ID: {data['external_id']}")
        print(f"   QR Image: {data['qr']['image']}")
        return data
    else:
        print(f"❌ Error creando POS: {resp.status_code}")
        print(resp.text)
        return None

def eliminar_pos(pos_id):
    """Elimina un POS"""
    url = f"https://api.mercadopago.com/pos/{pos_id}"
    
    print(f"\n🗑️  Eliminando POS {pos_id}...")
    resp = requests.delete(url, headers=HEADERS)
    
    if resp.status_code in [200, 204]:
        print(f"✅ POS eliminado exitosamente")
        return True
    else:
        print(f"❌ Error eliminando POS: {resp.status_code}")
        print(resp.text)
        return False
def eliminar_tienda(store_id):
    """Elimina una tienda (debe no tener POS asociados)"""
    url = f"https://api.mercadopago.com/stores/{store_id}"
    print(f"\n🗑️ Eliminando tienda {store_id}...")
    resp = requests.delete(url, headers=HEADERS)
    if resp.status_code in [200, 204]:
        print("✅ Tienda eliminada exitosamente")
        return True
    else:
        print(f"❌ Error eliminando tienda: {resp.status_code}")
        print(resp.text)
        print("⚠️ Asegúrate de eliminar primero todos los POS asociados.")
        return False
    
def recrear_pos_corregido(pos_viejo):
    """Elimina el POS viejo y crea uno nuevo corregido"""
    print("\n🔄 Proceso de corrección del POS:")
    print(f"   1. Eliminar POS actual: {pos_viejo['name']}")
    print(f"   2. Crear uno nuevo con fixed_amount=False")
    print(f"   3. Obtendrás un QR nuevo para imprimir")
    
    confirmar = input("\n⚠️  ¿Continuar? Tu QR actual dejará de funcionar (s/n): ")
    if confirmar.lower() != 's':
        print("❌ Operación cancelada")
        return None
    
    # Eliminar POS viejo
    if not eliminar_pos(pos_viejo['id']):
        return None
    
    # Crear POS nuevo
    store_id = pos_viejo.get('store_id')
    if not store_id:
        print("❌ No se pudo obtener el store_id del POS viejo")
        return None
    
    return crear_pos(store_id)


# --- PASO 3: CREAR ORDEN ---
def crear_orden_qr(external_pos_id, external_store_id, monto):
    global ultima_referencia
    ultima_referencia = f"ORDER_{int(time.time())}"
    url = f"https://api.mercadopago.com/instore/qr/seller/collectors/{USER_ID}/stores/{external_store_id}/pos/{external_pos_id}/orders"
    payload = {
        "external_reference": f"ORDER_{int(time.time())}",
        "title": "Venta en local",
        "description": f"Cobro de ${monto}",
        "total_amount": float(monto),
        "items": [
            {
                "sku_number": "A123K9191938",
                "category": "marketplace",
                "title": "Venta en local",
                "description": "Cobro en local",
                "unit_price": float(monto),
                "quantity": 1,
                "unit_measure": "unit",
                "total_amount": float(monto)
            }
        ]
    }

    print("\n📤 Creando orden con:")
    print(json.dumps(payload, indent=2))
    resp = requests.put(url, headers=HEADERS, json=payload)

    print(f"\n📥 Respuesta: {resp.status_code}")
    print(resp.text)
    if resp.status_code == 204:
        print("\n✅ Orden creada! (No se devuelve body)")
        return True
    else:
        print("\n❌ Error creando orden")
        print(f"Código: {resp.status_code}, Detalle: {resp.text}")
        return False

def verificar_estado_qr(external_pos_id, timeout=300, intervalo=5):
    """
    Consulta periódicamente el estado del POS QR para ver si la orden fue pagada.
    Si el POS ya no tiene orden activa (404), consulta el último pago.
    """
    url = f"https://api.mercadopago.com/instore/qr/seller/collectors/{USER_ID}/pos/{external_pos_id}/orders"
    print(f"\n⏳ Monitoreando pago en POS {external_pos_id} (sin backend)...")
    print(f"   Consultando cada {intervalo} segundos (máx {timeout//intervalo} intentos)\n")

    inicio = time.time()

    while (time.time() - inicio) < timeout:
        resp = requests.get(url, headers=HEADERS)

        # 🔹 Caso exitoso
        if resp.status_code == 200:
            data = resp.json()
            estado = data.get("order_status", "unknown")
            pagado = data.get("paid_amount", 0)
            total = data.get("total_amount", 0)
            print(f"🕒 Estado actual: {estado} | Pagado: ${pagado}/{total}")

            if estado == "paid" or pagado >= total:
                print("\n✅ ¡Pago recibido correctamente!")
                pagos = data.get("payments", [])
                if pagos:
                    payment_id = pagos[0].get("id")
                    print(f"   🆔 Payment ID: {payment_id}")
                    print(f"   💳 Estado: {pagos[0].get('status')}")
                    print(f"   Fecha: {pagos[0].get('date_approved')}")
                return True

        # 🔹 Caso 404 → la orden fue cerrada
        elif resp.status_code == 404:
            print("📭 La orden ya no está activa. Verificando último pago realizado...")
            consultar_ultimo_pago_por_referencia()
            return True

        else:
            print(f"⚠️ Error consultando estado: {resp.status_code}")
            print(resp.text)
            return False

        time.sleep(intervalo)

    print("\n⏰ Tiempo de espera agotado. La orden sigue abierta.")
    return False
def consultar_ultimo_pago_por_referencia():
    """
    Busca el último pago usando la external_reference de la última orden creada.
    """
    # ⚠️ IMPORTANTE: guardá la referencia cuando creás la orden
    global ultima_referencia

    if not ultima_referencia:
        print("⚠️ No se encontró external_reference para buscar el pago.")
        return

    url = f"https://api.mercadopago.com/v1/payments/search?external_reference={ultima_referencia}"
    resp = requests.get(url, headers=HEADERS)

    if resp.status_code == 200:
        data = resp.json()
        resultados = data.get("results", [])
        if resultados:
            pago = resultados[0]
            print("\n💰 Último pago detectado:")
            print(f"   🆔 Payment ID: {pago.get('id')}")
            print(f"   💳 Estado: {pago.get('status')}")
            print(f"   Monto: ${pago.get('transaction_amount')}")
            print(f"   Fecha: {pago.get('date_approved')}")
        else:
            print("\n⚠️ No se encontraron pagos recientes con esa referencia.")
    else:
        print(f"⚠️ Error consultando último pago: {resp.status_code}")
        print(resp.text)


def consultar_ultimo_pago_pos(external_pos_id):
    """
    Consulta el último pago asociado a un POS para saber si se completó la venta.
    """
    url = f"https://api.mercadopago.com/v1/payments/search?external_pos_id={external_pos_id}&sort=date_created&criteria=desc"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code == 200:
        data = resp.json()
        resultados = data.get("results", [])
        if resultados:
            pago = resultados[0]
            print("\n💰 Último pago detectado:")
            print(f"   🆔 Payment ID: {pago.get('id')}")
            print(f"   💳 Estado: {pago.get('status')}")
            print(f"   Monto: ${pago.get('transaction_amount')}")
            print(f"   Fecha: {pago.get('date_approved')}")
        else:
            print("\n⚠️ No se encontraron pagos recientes para este POS.")
    else:
        print("⚠️ Error consultando último pago:", resp.status_code)

def verificar_orden(order_id):
    """Verifica el estado de una orden usando el endpoint correcto"""
    # Usar el endpoint de merchant orders que es más confiable
    url = f"https://api.mercadopago.com/merchant_orders/{order_id}"
    resp = requests.get(url, headers=HEADERS)
    
    if resp.status_code == 200:
        data = resp.json()
        print(f"\n📊 Estado de la orden:")
        print(f"   Status: {data.get('status')}")
        print(f"   Order Status: {data.get('order_status')}")
        print(f"   Total: ${data.get('total_amount')}")
        print(f"   Pagado: ${data.get('paid_amount')}")
        return data
    else:
        # Intentar con el otro endpoint
        url2 = f"https://api.mercadopago.com/instore/qr/seller/collectors/{USER_ID}/stores/{order_id}/orders"
        resp2 = requests.get(url2, headers=HEADERS)
        
        if resp2.status_code == 200:
            print(f"\n📊 Orden encontrada en endpoint alternativo")
            return resp2.json()
        else:
            print(f"❌ Error consultando orden en ambos endpoints")
            print(f"   Endpoint 1: {resp.status_code} - {resp.text[:100]}")
            print(f"   Endpoint 2: {resp2.status_code} - {resp2.text[:100]}")
            return None


# --- MENÚ PRINCIPAL ---
def menu_principal():
    print("\n" + "="*60)
    print("🔧 MERCADOPAGO QR ESTÁTICO - DIAGNÓSTICO Y CONFIGURACIÓN")
    print("="*60)
    
    print("\n1️⃣  Verificar credenciales")
    print("2️⃣  Listar tiendas")
    print("3️⃣  Crear nueva tienda")
    print("4️⃣  Listar POS (Puntos de Venta)")
    print("5️⃣  Crear nuevo POS")
    print("6️⃣  🔧 Recrear POS (corregir fixed_amount)")
    print("7️⃣  🗑️  Eliminar POS")
    print("8️⃣  🎯 REALIZAR COBRO")
    print("9️⃣  Ver estado de orden")
    print("🔟 Eliminar tienda")
    print("0️⃣  Salir")
    
    return input("\n👉 Seleccioná una opción: ")

# --- FLUJO DE COBRO SIMPLIFICADO ---
def obtener_external_store_id(store_id):
    """Busca el external_id de una tienda por su ID interno."""
    url = f"https://api.mercadopago.com/stores/{store_id}"
    resp = requests.get(url, headers=HEADERS)
    
    if resp.status_code == 200:
        data = resp.json()
        external_id = data.get('external_id')
        if external_id:
            print(f"✅ External Store ID encontrado: {external_id}")
            return external_id
        else:
            print("⚠️ La tienda no tiene External ID. Usaremos el ID interno como fallback.")
            # Si no tiene external_id, a veces MP acepta el ID interno
            return str(store_id) 
    else:
        print(f"❌ Error al obtener la tienda {store_id}: {resp.status_code} - {resp.text}")
        return None


def flujo_cobro():
    print("\n" + "="*60)
    print("💰 PROCESO DE COBRO - DEBUG COMPLETO")
    print("="*60)
    
    # ... (código existente para verificar y seleccionar POS) ...
    pos_list = listar_pos()
    
    if not pos_list:
        print("\n⚠️ No hay POS configurados. Primero creá uno (opción 5)")
        return
    
    # Mostrar POS disponibles con toda la info (mantenemos esto para referencia)
    print("\n📋 POS disponibles:")
    for i, pos in enumerate(pos_list):
        store_id = pos.get('store_id', 'N/A')
        print(f"\n   {i+1}. {pos['name']} (Store ID: {store_id})")
        print(f"      External ID: {pos.get('external_id', 'N/A')}")
        print(f"      Status: {pos.get('status', 'N/A')}")

    # Seleccionar POS
    try:
        idx = int(input("\n👉 Seleccioná un POS (número): ")) - 1
        pos_seleccionado = pos_list[idx]
    except (ValueError, IndexError):
        print("❌ Selección inválida")
        return
    
    external_pos_id = pos_seleccionado.get('external_id')
    store_id = pos_seleccionado.get('store_id')
    status = pos_seleccionado.get('status', 'unknown')
    
    # NUEVO PASO CRÍTICO: Obtener el External Store ID
    if not store_id:
        print("\n❌ ERROR: El POS no tiene Store ID asociado.")
        return

    print(f"\n🔍 Buscando External ID para Store ID: {store_id}")
    external_store_id = obtener_external_store_id(store_id)
    
    if not external_store_id:
         print("\n❌ ERROR: No se pudo obtener el External ID de la tienda.")
         return

    if status != 'active':
        print(f"\n⚠️ ADVERTENCIA: El POS está en estado '{status}'. Debe ser 'active'.")
        continuar = input("   ¿Continuar de todos modos? (s/n): ")
        if continuar.lower() != 's':
            return
    
    # Solicitar monto
    try:
        monto = float(input("\n💵 Ingresá el monto a cobrar: $"))
    except ValueError:
        print("❌ Monto inválido")
        return
    
    print(f"\n🔄 Creando orden para ${monto}...")
    
    # Llama a la función corregida con el External Store ID
    order_id = crear_orden_qr(external_pos_id, external_store_id, monto)
    if not order_id:
        print("\n❌ FALLÓ LA CREACIÓN DE LA ORDEN")
        return
    
    # Monitorear pago
    print(f"\n✅ ORDEN CREADA EXITOSAMENTE")
    print(f"   Order ID: {order_id}")
    print(f"\n📱 AHORA SÍ: El cliente debe escanear tu QR estático")
    print("\n⚠️ IMPORTANTE: Si el cliente ya tenía el QR escaneado, debe salir y volver a escanearlo.")

    input("\n⏎ Presioná ENTER cuando el cliente esté listo para escanear y monitorear el pago...")
    verificar_estado_qr(external_pos_id)

    
# --- EJECUCIÓN ---
if __name__ == "__main__":
    print("\n🚀 Sistema de Cobros MercadoPago")
    print("   Diagnóstico y Configuración\n")
    
    while True:
        opcion = menu_principal()
        
        if opcion == "1":
            verificar_credenciales()
        
        elif opcion == "2":
            listar_tiendas()
        
        elif opcion == "3":
            crear_tienda()
        
        elif opcion == "4":
            listar_pos()
        
        elif opcion == "5":
            stores = listar_tiendas()
            if stores:
                print("\n📋 Seleccioná una tienda:")
                for i, s in enumerate(stores):
                    print(f"   {i+1}. {s['name']} (ID: {s['id']})")
                try:
                    idx = int(input("\n👉 Número: ")) - 1
                    crear_pos(stores[idx]['id'])
                except (ValueError, IndexError):
                    print("❌ Selección inválida")
            else:
                print("⚠️ Primero creá una tienda (opción 3)")
        
        elif opcion == "6":
            # Recrear POS corregido
            pos_list = listar_pos()
            if pos_list:
                print("\n📋 Seleccioná el POS a recrear:")
                for i, p in enumerate(pos_list):
                    print(f"   {i+1}. {p['name']} (Fixed: {p.get('fixed_amount')})")
                try:
                    idx = int(input("\n👉 Número: ")) - 1
                    nuevo_pos = recrear_pos_corregido(pos_list[idx])
                    if nuevo_pos:
                        print("\n✅ POS recreado exitosamente!")
                        print(f"   🆔 Nuevo ID: {nuevo_pos['id']}")
                        print(f"   📱 Nuevo QR: {nuevo_pos['qr']['image']}")
                        print("\n⚠️  IMPORTANTE: Descargá e imprimí el nuevo QR")
                except (ValueError, IndexError):
                    print("❌ Selección inválida")
        
        elif opcion == "7":
            # Eliminar POS
            pos_list = listar_pos()
            if pos_list:
                print("\n📋 Seleccioná un POS para eliminar:")
                for i, p in enumerate(pos_list):
                    print(f"   {i+1}. {p['name']}")
                try:
                    idx = int(input("\n👉 Número: ")) - 1
                    confirmar = input(f"\n⚠️  ¿Confirmar eliminación de '{pos_list[idx]['name']}'? (s/n): ")
                    if confirmar.lower() == 's':
                        eliminar_pos(pos_list[idx]['id'])
                except (ValueError, IndexError):
                    print("❌ Selección inválida")
        
        elif opcion == "8":
            flujo_cobro()
        
        elif opcion == "9":
            order_id = input("\n🆔 Ingresá el Order ID: ")
            verificar_orden(order_id)
        elif opcion == "10":
            stores = listar_tiendas()
            if stores:
                print("\n📋 Seleccioná una tienda para eliminar:")
                for i, s in enumerate(stores):
                    print(f" {i+1}. {s['name']} (ID: {s['id']})")
                try:
                    idx = int(input("\n👉 Número: ")) - 1
                    confirmar = input(f"\n⚠️ ¿Confirmar eliminación de '{stores[idx]['name']}'? (s/n): ")
                    if confirmar.lower() == 's':
                        eliminar_tienda(stores[idx]['id'])
                except (ValueError, IndexError):
                    print("❌ Selección inválida")
            else:
                print("⚠️ No hay tiendas para eliminar")
        
        elif opcion == "0":
            print("\n👋 ¡Hasta luego!")
            break
        
        else:
            print("❌ Opción inválida")
        
        input("\n⏎ Presioná ENTER para continuar...")
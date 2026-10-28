# IntraShop

Tienda web local para el POS de Gestión Librería/Kiosko. Usa la misma SQLite del servidor POS; no requiere una base de datos en Internet.

## Componentes

- `../api_server.py`: monta la API `/tienda/*` sobre el servidor FastAPI existente.
- `../intrashop_api.py`: catálogo, configuración de disponibilidad/imágenes y checkout.
- `src/pages/index.astro`: catálogo, carrito y estado de pago.
- Columnas aditivas en `productos`: `disponible_tienda` (apagado por defecto) e `imagen_tienda`.

## Ejecutar en desarrollo

1. Instalar dependencias del POS y configurar su `.env`/ajustes habituales.
2. Iniciar el servidor del POS: `python api_server.py --server` (o el comando de servidor usado por la instalación).
3. Desde `intrashop/`: `npm install` y `npm run dev`.
4. Abrir `http://localhost:4321`. Para otros dispositivos, usar la IP LAN del equipo que ejecuta Astro y configurar en la tienda la dirección del POS `http://IP-DEL-SERVIDOR:8000` junto con su `API_KEY`.

## Requisitos de cobro

- Mercado Pago debe estar configurado en el POS (token, user ID, Store/POS y QR).
- Debe haber una caja abierta en el POS.
- El servidor debe permanecer ejecutándose mientras se espera el pago; el estado del checkout vive en memoria.
- El QR mostrado usa la URL QR configurada en el POS. La integración actual reutiliza el servicio QR existente del POS.

## Habilitar productos

Los productos quedan fuera del catálogo por defecto. El endpoint administrativo `PUT /tienda/admin/productos/{id}` recibe `x-api-key` y JSON:

```json
{
  "disponible": true,
  "imagen_nombre": "producto.jpg",
  "imagen_base64": "data:image/jpeg;base64,..."
}
```

Se aceptan JPG, PNG y WebP de hasta 5 MB. La imagen se guarda localmente junto a la base de datos. Si no se envía una imagen, se conserva la imagen anterior; el catálogo muestra una imagen ilustrativa si no hay foto cargada.

## Limitaciones iniciales

- El cobro usa el servicio QR existente y una única orden activa a la vez.
- Si Mercado Pago confirma el pago pero falla el registro de la venta, el checkout queda en `paid_sale_error` y debe conciliarse manualmente antes de reintentar.
- El comprobante automático de IntraShop es un comprobante interno de texto, no una factura fiscal. La emisión fiscal depende del flujo de facturación ya configurado en el POS.
- El panel de administración para marcar productos y subir fotos debe completarse/integrarse con la pantalla de artículos del POS antes de usarlo con clientes.

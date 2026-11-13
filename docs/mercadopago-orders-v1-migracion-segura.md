# Mercado Pago QR: circuito IntraShop y migración a Orders API

Estado: **circuito de código implementado y verificado con SQLite/HTTP simulado**. La nueva Orders API está **desactivada por defecto** y falta validar credenciales, webhooks HTTPS y pagos con una cuenta real de pruebas antes de habilitarla en producción.

## 1. Compatibilidad con operaciones existentes

- La API legacy sigue atendiendo cobros de POS escritorio y checkouts previos de IntraShop.
- La base incorpora una migración aditiva en `intrashop_checkouts`: `mp_api` (default `legacy`), `mp_order_id` (índice único parcial) y `mp_cancel_requested`.
- La opción `INTRASHOP_MP_ORDERS_V1=1` solo afecta **nuevos checkouts de los tótems IntraShop**. No cambia pagos abiertos ni la caja del POS escritorio.
- El carrito, las cantidades y el monto se calculan en POS Server. La reserva de stock permanece mientras MP no confirme un estado terminal.

## 2. Configuración y habilitación

1. Actualizar POS Server y guardar una copia de seguridad de su SQLite.
2. Verificar que cada tótem esté registrado, con caja abierta y un POS de Mercado Pago exclusivo correctamente asociado a la misma cuenta del token.
3. Verificar credenciales OAuth o Access Token válidos en el servidor. Nunca enviarlos al frontend ni guardarlos en URLs.
4. En `.env` del POS Server configurar:
   ```env
   MP_ACTIVO=true
   INTRASHOP_MP_ORDERS_V1=1
   MP_ORDERS_WEBHOOK_SECRET=LA_FIRMA_SECRETA_DEL_PANEL
   MP_TIMEOUT_SEG=15
   MP_POLL_INTERVAL_SEG=5
   MP_POLL_TIMEOUT_SEG=300
   ```
5. Reiniciar POS Server para que cargue las variables de entorno y ejecute migraciones.
6. Usar inicialmente credenciales de prueba y comprobar el circuito completo antes de operar en producción.

Para volver a usar el flujo legacy en nuevos checkouts: `INTRASHOP_MP_ORDERS_V1=0` y reiniciar. Los pedidos guardados como `orders_v1` mantienen ese proveedor para conciliaciones.

## 3. Circuito QR implementado

- **Crear:** `POST /v1/orders` con `external_pos_id`, total y referencia única del checkout. Reutiliza una `X-Idempotency-Key` determinística para reintentos de la misma operación.
- **Persistir:** guarda `mp_order_id` antes de publicar `waiting_payment`. La caja sigue mostrando su QR estático asignado.
- **Cobrar:** consulta `GET /v1/orders/{order_id}`. Exige ID, referencia, total e importe acreditado de la transacción. El body de un webhook no acredita ninguna venta.
- **Registrar:** inserta `ventas`, `venta_items`, descuento de productos, `movimientos_stock` y comanda de entrega en una transacción SQLite. Los reintentos no duplican ventas.
- **Cancelar:** el botón del tótem guarda `mp_cancel_requested`, solicita `POST /v1/orders/{order_id}/cancel` y consulta de nuevo la orden. Solo `canceled/canceled` o `expired/expired` confirmados liberan la reserva.
- **Incidencia:** una respuesta HTTP incierta, error de red, timeout o estado no acreditado conserva la reserva para conciliación.
- **Reinicio:** operaciones legacy siguen su procedimiento anterior; las Orders v1 se verifican por ID y, si quedaron abiertas, se cierran por ID. La creación cuyo POST perdió la respuesta solo se reintenta idempotentemente durante una ventana corta de recuperación; después requiere localizar el `order_id` por webhook o un administrador.

## 4. Webhook firmado

- Ruta FastAPI: `POST /tienda/webhooks/mercadopago/orders`.
- En Mercado Pago Developers > aplicación > Webhooks, seleccionar **Order (Mercado Pago)** y configurar una URL HTTPS pública a esta ruta. Guardar la firma secreta en `MP_ORDERS_WEBHOOK_SECRET`.
- Se verifica HMAC-SHA256 con `data.id`, `x-request-id` y `x-signature`, comparación constante y una tolerancia temporal de cinco minutos.
- Se valida que el ID del body coincida con el parámetro firmado. Solo se concilian IDs asociados a checkouts locales; cada conciliación realiza **GET autenticado** antes de modificar ventas.
- Si un POST creó la orden pero el ID se perdió por una caída, el webhook firmado puede aportar la referencia. POS Server verifica el ID, referencia y total en MP mediante GET antes de asociarlo.
- **Un servidor exclusivamente LAN no es alcanzable desde Mercado Pago.** Se necesita una ruta HTTPS expuesta con proxy/túnel o relay seguro. No publicar todo POS Server en Internet. Sin webhook, el polling y la recuperación tras reinicio siguen disponibles, pero no hay notificaciones en tiempo real del exterior.
- Sin `MP_ORDERS_WEBHOOK_SECRET` el endpoint devuelve 503; firmas inválidas devuelven 401.

## 5. Recuperación administrativa

Los endpoints siguientes requieren un **Bearer de un administrador POS**, no solo la API key general:

- `GET /tienda/admin/checkouts-pending` muestra proveedor (`mp_api`), `mp_order_id`, cancelación pendiente y estado de la reserva.
- `POST /tienda/admin/checkouts/{id}/reconcile` consulta la order identificada y aplica estados acreditados/cancelados verificados.
- `POST /tienda/admin/checkouts/{id}/resolve-mp-order` con `{"order_id":"ORD..."}` asocia un ID recuperado del panel de Mercado Pago **solo tras GET autenticado y comprobación de referencia/total**; audita al operador.
- `POST /tienda/admin/checkouts/{id}/release` exige confirmación del administrador. En Orders v1, la liberación requiere `canceled` o `expired` confirmado mediante GET; si está pendiente, solicita cancelación por ID.

No se permite liberar una reserva por buscar pagos y no encontrar ninguno.

## 6. Pruebas y estado de producción

CI: `.github/workflows/qr-stock-regression.yml` (compilación Python y pruebas SQLite/HTTP simuladas).

```bash
python -m pytest -q \
  tests/test_intrashop_orders_e2e_mock.py \
  tests/test_mp_orders_v1_mock.py \
  tests/test_mp_orders_webhook.py \
  tests/test_mp_qr_network_mock.py \
  tests/test_reservas_intrashop_pos.py
```

**Antes del cambio productivo** validar con la cuenta de pruebas del comercio: QR real escaneado, cobro aprobado, monto con recargo, cancelación antes/durante el POST, intento de pago durante la cancelación, reinicio de POS Server, entrega, webhook HMAC, y operación sin conectividad. Verificar además las credenciales OAuth de cada comercio y el proxy HTTPS.

Fuentes oficiales:
- https://www.mercadopago.com.ar/developers/es/docs/qr-code/payment-processing
- https://www.mercadopago.com.ar/developers/es/docs/qr-code/notifications
- https://www.mercadopago.com.ar/developers/es/docs/qr-code/resources/status-order-transaction

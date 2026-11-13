# Migración segura de QR IntraShop / POS a Mercado Pago Orders API

Estado: **adaptador implementado y probado con HTTP simulado, NO habilitado en producción**.

El flujo actual usa Instore Orders V2 (legacy), que crea el cobro por `PUT` y devuelve 204 sin `order_id`. El GET por caja no permite consultar un pedido histórico concreto. Por tanto, **no se debe inferir ausencia definitiva de pago de una búsqueda vacía de Payments**, aunque el DELETE del QR haya respondido 204.

Referencias oficiales:
- https://www.mercadopago.com.ar/developers/es/docs/qr-code/resources/migrate-instore-orders-v2-to-orders
- https://www.mercadopago.com.ar/developers/es/docs/qr-code/payment-processing

## Cambios seguros ya activos (legacy)

- Cada cobro QR del POS e IntraShop tiene una referencia única.
- Antes de finalizar una venta se consulta pago por referencia e importe.
- Al cancelar se consulta la orden activa del POS y únicamente se elimina si coincide con la referencia.
- El DELETE legacy utiliza el endpoint **por colector y POS**, sin segmento `stores`.
- La caída de red, la respuesta 404 o un payment search vacío se consideran incertidumbre, **no éxito de cancelación**.
- POS Server recupera cobros interrumpidos y reconsulta pagos. Guarda evidencia del cierre en `qr_close_status`; no libera stock si pudo haberse intentado un QR.
- Las reservas en estado `reserved` sin worker iniciado se pueden cancelar tras reinicio porque el worker persiste `creating` antes del PUT.
- La liberación manual exige sesión autorizada, confirmación explícita, QR sin orden activa, doble consulta de pagos y auditoría.

## Nueva Orders API: adaptador aislado

`services/mp_orders_v1_client.py` contiene `MercadoPagoOrdersV1`:

- `crear(reference, pos_external_id, items, total)` → POST /v1/orders
- `consultar(order_id, reference, total)` → GET /v1/orders/{order_id}
- `cancelar(order_id, reference, total)` → POST /v1/orders/{order_id}/cancel y luego GET por ID

Incluye idempotency keys determinísticas por referencia y operación, validación de referencia e importe, credenciales solo en el header Authorization y estados conservadores. Probado con respuestas simuladas en `tests/test_mp_orders_v1_mock.py`.

**No conectar directamente este adaptador al checkout legacy.** La Orders API crea la orden con ID y necesita persistencia e integración de estado distintas.

## Criterios para activar la nueva integración

1. Añadir columnas `mp_order_id`, `mp_api` y claves de operación a la tabla de checkouts. Conservar `legacy` para registros previos.
2. Persistir el proveedor elegido antes de crear una orden. Guardar el `order_id` antes de mostrar el QR al comprador.
3. Si un POST pierde la respuesta por timeout, reintentar **la misma petición** con la misma idempotency key; nunca generar otra referencia ni cambiar el total.
4. Usar GET /v1/orders/{order_id} más webhook del tópico `orders` verificado en backend. Una orden `processed` con detalle `accredited`, misma referencia e importe, conduce a venta idempotente.
5. Para cancelar, POST por el `order_id` exacto y luego GET por ese mismo ID. Solo el estado `canceled` confirmado, con referencia e importe correctos, autoriza liberar stock automáticamente. Un `409` de cancelación exige GET: puede significar un pago ya procesado.
6. Para reinicios, recuperar cada checkout según su campo `mp_api`. No cambiar automáticamente el proveedor de una orden pendiente.
7. Habilitar mediante opción explícita de configuración únicamente tras probar creación, pago, cancelación durante creación, pago durante cancelación, reinicio y red caída con credenciales de prueba. Verificar webhooks y procesamiento con cuenta real antes de producción.

## Ejecutar pruebas automáticas

GitHub Actions: `.github/workflows/qr-stock-regression.yml`

Local:

```bash
python -m pytest -q tests/test_mp_orders_v1_mock.py tests/test_mp_qr_network_mock.py tests/test_intrashop_startup_recovery_mock.py tests/test_pos_qr_cancel_static.py
```

La nueva Orders API **todavía no cobra ni cancela pedidos reales en IntraShop**. El adaptador no se activa hasta cumplir los criterios anteriores para evitar un cambio accidental de proveedor de pagos sobre un comercio existente.

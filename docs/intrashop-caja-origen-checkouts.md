# IntraShop — caja de origen por checkout

## Qué corrige

Antes, la venta de un tótem se imputaba a `SELECT id FROM cajas WHERE estado='abierta' ORDER BY id DESC LIMIT 1` **al acreditar el pago**. Reinicios, cambios de turno o más de una caja abierta podían imputar la venta a otra caja.

Ahora, **antes de crear el cobro Mercado Pago**, la reserva guarda `intrashop_checkouts.caja_id`, seleccionado exclusivamente desde POS Server:

- Si el tótem tiene `caja_id` configurado en su vinculación con POS Mercado Pago, esa caja debe estar **abierta**.
- Si no está configurado y hay **exactamente una caja abierta**, se utiliza esa caja por compatibilidad con instalaciones actuales.
- Si hay cero o más de una caja abierta sin asignación, se rechaza el checkout antes de llamar a Mercado Pago.
- La venta utiliza únicamente el `caja_id` persistido. **Nunca** vuelve a buscar la última caja abierta.
- El `caja_id` permanece igual en consultas, conciliaciones tras reinicio y reintentos.
- Los checkouts viejos con `caja_id=NULL` no se reasignan automáticamente: si aparece un cobro confirmado, la reserva se conserva como `uncertain` para reconciliación administrativa.
- Si la caja original está cerrada, no se crea una venta en otra: se conserva la reserva y la operación requiere intervención.

## Migración

`intrashop_checkout_store.ensure_schema` agrega columnas opcionales `caja_id` a `intrashop_mp_bindings` e `intrashop_checkouts`. No reemplaza ni borra operaciones previas. Las vinculaciones anteriores siguen funcionando con una sola caja activa; es recomendable asignar una explícitamente para cada tótem.

## Configuración manual

1. Ingresar al **POS IntraShop** como administrador con acceso a POS Server.
2. Abrir **Ajustes > Mercado Pago > Asignación de QR por dispositivo**.
3. Usar **Detectar tótems y POS**.
4. Elegir el tótem y su POS Mercado Pago exclusivo.
5. En **Caja para ventas del tótem**, seleccionar la caja abierta donde deben registrarse los pagos. La opción *Automática* solo es válida si existe una única caja abierta.
6. Revisar y confirmar la vinculación. La relación incluye el número de caja y se guarda en POS Server.
7. Comprobar un checkout simulado y verificar `ventas.caja_id`, `intrashop_checkouts.caja_id`, stock y comanda.

Para una asociación a otra caja, primero completar o conciliar los cobros pendientes; el servidor rechaza el cambio de un QR con checkout activo.

## Recuperación de un checkout anterior a la migración

Si un checkout existente quedó con `caja_id=NULL`, **no** se inventa una caja ni se libera su reserva. Un administrador que verificó a qué caja correspondía puede utilizar `POST /tienda/admin/checkouts/{checkout_id}/assign-caja` con encabezado `Authorization: Bearer <sesión_admin>` y body:

```json
{"caja_id": 123, "confirmacion": "ASIGNAR CAJA A CHECKOUT ANTIGUO"}
```

Solo acepta una caja **abierta**, sin venta previa y un checkout aún no cerrado. Registra la decisión del operador en `intrashop_auditoria` y no produce ni descuenta ventas por sí misma. La caja queda inmutable. Luego usar `POST /tienda/admin/checkouts/{checkout_id}/reconcile` para comprobar el pago en Mercado Pago antes de registrar una venta. No publicar el token administrativo, ni llamar esta ruta desde el navegador del tótem.

Si la caja original se cerró, este procedimiento no reasigna automáticamente pagos históricos a otra caja. Hace falta conciliación operativa antes de modificar cierres contables.

## Validaciones

```bash
python -m pytest -q tests/test_intrashop_caja_link.py tests/test_intrashop_orders_e2e_mock.py tests/test_pos_server_caja_ventas.py
```

Estos tests usan SQLite temporal y no acceden a credenciales Mercado Pago.

**Limitación consciente:** este cambio resuelve el destino de cada checkout y prepara la coexistencia de varias cajas, pero no implementa todavía apertura de cajas separada por identidad de cada POS. El endpoint actual de apertura impide una segunda caja abierta. Eso necesita una implementación aparte de sesiones por terminal/cajero, permisos y conciliación de cierre.

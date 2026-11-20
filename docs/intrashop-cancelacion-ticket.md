# IntraShop / POS — cancelación QR y ticket

## Cancelación inmediata

- Al tocar **Cancelar** o **X** el tótem cierra el modal **sin esperar** Mercado Pago.
- El servidor registra `mp_cancel_requested` antes de detener el worker.
- Una venta que **aún no fue registrada** queda bloqueada por esa marca: no se descuenta stock, no se crea comanda y no se genera ticket.
- En la API QR legacy se cierra exclusivamente la orden con la `external_reference` correspondiente. Cuando Mercado Pago confirma su cierre, el estado pasa a `cancelled` y se libera la reserva. Si el cierre falla o no puede comprobarse, se conserva la reserva para revisión administrativa, pero **no se bloquea el modal**.
- Orders API v1 realiza la cancelación por `order_id` en segundo plano y mantiene sus controles de idempotencia.
- Si Mercado Pago acreditó el pago **antes** de la cancelación, la venta ya confirmada no puede deshacerse sólo ocultando el QR. Si hay una acreditación simultánea después de solicitar cancelar, se impide generar automáticamente una comanda y se requiere revisión/devolución del dinero. Nunca interpretar la ausencia en la búsqueda de pagos como una prueba definitiva.

## Impresión de ticket tras pago

En **IntraShop**, después del commit de una venta confirmada:

1. Se crea `intrashop_ticket_jobs` en la misma transacción que la venta, con `venta_id` único.
2. POS Server genera un PDF de 80 mm, con productos, cantidades, total e identificación de la venta.
3. Desde POS Server se envía a la cola de impresión (Linux/macOS: `lp`; Windows: impresión del PDF mediante la asociación del sistema).
4. Se registra `sent` si se aceptó el envío. Si falla, queda `failed`, con la ruta del PDF y el error. El error de la impresora **no revierte la venta**.
5. Un trabajo `sent` o `printing` no se reenvía automáticamente para evitar tickets duplicados.

**Configuración opcional en el entorno de POS Server:**

```env
INTRASHOP_PRINT_TICKET=1
INTRASHOP_PRINTER=
```

`INTRASHOP_PRINTER` vacío utiliza la impresora predeterminada de CUPS. Para una impresora específica, utilizar el **nombre de cola CUPS** (no una dirección URL). `INTRASHOP_PRINT_TICKET=0` guarda el PDF sin enviarlo a impresora.

En Ubuntu, comprobar las impresoras con:

```bash
lpstat -p -d
```

Los PDFs se guardan en `TICKETS_DIR` (Ajustes del POS), relativo a la carpeta de la base SQLite del servidor si no es absoluto. No se imprime ningún ticket desde el navegador ni se necesita conectar una impresora al tótem.

En **POS Flet**, el QR confirmado usa la impresión del comprobante o del PDF de facturación. Si la facturación está inactiva, se genera un ticket interno PDF para imprimirlo igualmente.

**Nota fiscal:** el ticket interno no sustituye a una factura electrónica AFIP/ARCA ni contiene autorización fiscal.

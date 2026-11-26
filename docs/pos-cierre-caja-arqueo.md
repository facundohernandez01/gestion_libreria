# Cierre de caja POS — arqueo y control de efectivo

## Flujo de operador

1. Abrir **Cerrar caja** desde la ventana principal del POS (modo local o cliente).
2. El sistema consulta la caja activa por su ID y resume **todas** las ventas desde que se abrió, aunque haya pasado la medianoche.
3. Se muestran separados: fondo inicial, ventas en efectivo, Mercado Pago/tarjetas, gastos y **efectivo esperado**. Los pagos electrónicos no incrementan el efectivo en el cajón.
4. Contar físicamente el efectivo e ingresar **Efectivo contado**. Se calcula **diferencia = contado − esperado**.
5. Si hay faltante o sobrante, escribir la observación obligatoria.
6. Pulsar **Confirmar cierre de caja**. Se ejecuta dentro de `BEGIN IMMEDIATE` con validación del estado abierto, saldo y pendientes, evitando doble cierre y nuevas ventas concurrentes.
7. La pantalla confirma el cierre y retorna al flujo de apertura. En **Historial de cajas** quedan el esperado, contado, diferencia y observaciones.

La acción **Volver, sin cerrar** solo cierra el diálogo. **Actualizar** recupera movimientos recientes. Se pueden registrar gastos directamente desde la pantalla antes de cerrar.

## Cálculo

```text
Efectivo esperado = Fondo inicial
                  + Ventas pagadas en efectivo
                  - Gastos / retiros registrados

Diferencia arqueo = Efectivo contado - Efectivo esperado
```

Se consideran exclusivamente ventas con `estado='completada'` y `caja_id` del turno. El total global de ventas se conserva por separado, con desglose de medios de pago.

## Bloqueos y concurrencia

- Con un checkout IntraShop de la misma caja en `reserved/creating/waiting/verifying/uncertain/paid`, el cierre se bloquea e indica ir a **POS Server → Conciliación**. No se da por cobrado ni por cancelado un pago ambiguo.
- Si el resumen cambia mientras el operador cuenta (ventas/gastos nuevos), se exige actualizarlo antes del cierre.
- No se puede cerrar dos veces la misma caja.
- No se permite agregar gastos después del cierre.
- En modo cliente, las respuestas HTTP 409 muestran la causa exacta; ya no se convierten únicamente en `False`.
- La aplicación no altera `libreria.db` durante la actualización de código. Las columnas se agregan con migraciones aditivas (`efectivo_esperado`, `efectivo_contado`, `diferencia_arqueo`).

## API y compatibilidad

- `GET /cajas/{id}/resumen` — resumen del turno.
- `POST /cajas/{id}/cerrar` — JSON con `importe_contado`, `observaciones`, `efectivo_esperado`, `total_ventas` y `total_gastos` (estos tres últimos validan que el resumen no se haya modificado).

Los clientes antiguos que llamen al cierre por query sin importe contado continúan funcionando por compatibilidad; el servidor registra como contado el efectivo teórico. Para un arqueo real usar siempre el nuevo método.

Las pruebas automatizadas usan bases SQLite descartables; la experiencia visual y el recorrido completo deben verificarse con Flet en la instalación del comercio.

# IntraShop: pagos concurrentes, reservas, comandas y servidor LAN

## Arquitectura de esta etapa

- Servidor POS: una única base SQLite en el servidor. No compartir el archivo SQLite por SMB/NFS.
- Tótems: UUID persistido por navegador; heartbeat cada 30 segundos.
- Asignaciones: `intrashop_mp_bindings` vincula un dispositivo a un `external_id` MP y su QR. `UNIQUE(pos_external_id)` impide compartir QR entre tótems y cajas.
- Reservas: `intrashop_checkouts` + `intrashop_reservas`. `BEGIN IMMEDIATE` valida y reserva stock en una transacción.
- La disponibilidad de tienda y las ventas POS locales/API descuentan las reservas activas.
- Cada cobro tiene su propia referencia externa, su POS MP y su operación de polling/cancelación.
- La venta pagada, el descuento definitivo de stock y el estado `completed` se confirman en una misma transacción.
- Comandas: `POST /tienda/admin/entregas/{id}/tomar` y `/liberar`, con usuario autenticado, `X-Terminal-Id` y exclusión por transacción. Solo el dueño en la misma terminal puede avanzar o entregar.

## Configuración

1. En Mercado Pago, crear un POS/QR *distinto* para cada tótem y caja física.
2. En POS → Ajustes → Mercado Pago → «Asignación de QR por dispositivo», obtener POS, detectar tótems y vincularlos.
3. El servidor almacena las asignaciones; cada tótem debe estar registrado y tener QR antes de cobrar.
4. En IntraShop → /admin se configura URL/IP y nombre del tótem. «Detectar servidor cercano» comprueba URL guardada, host web y localhost. **No** hace descubrimiento completo de subred: los navegadores limitan el escaneo LAN.
5. La caja POS dispone de un identificador estable `POS_TERMINAL_ID`. El servicio MP intenta resolver la asignación de esta caja antes de usar el POS predeterminado. La pantalla QR muestra la imagen asignada y deshabilita la impresión del archivo QR local antiguo para evitar imprimir el QR de otra caja.

## Recuperación y conciliación

- Si el servidor reinicia durante un cobro, el checkout persiste y su reserva no se libera automáticamente.
- `GET /tienda/admin/checkouts-pending`: muestra pendientes de conciliación.
- `POST /tienda/admin/checkouts/{id}/reconcile`: consulta pagos aprobados por referencia; si existe, intenta registrar la venta exactamente una vez.
- Si no se confirma pago, permanece `uncertain`; una respuesta negativa no demuestra que MP nunca vaya a aprobarlo.
- Solo un administrador, después de revisar MP, puede liberar manualmente una reserva incierta mediante `POST /tienda/admin/checkouts/{id}/release` con `{"confirmacion":"VERIFIQUE EN MERCADO PAGO QUE NO EXISTE COBRO"}`. Queda registro en `intrashop_auditoria`.

## Servidor GUI y empaquetado

```bash
python pos_server_gui.py
# Para ejecutar headless:
python pos_server.py --host 0.0.0.0 --port 8000
# Compilar GUI en el sistema operativo destino:
bash scripts/build_pos_server_gui.sh
```

La consola gráfica muestra estado del servidor, tótems y último contacto, operadores con sesión vigente y cantidad de reservas inciertas. **No es un binario ya construido**; requiere Python/Tkinter, dependencias y PyInstaller en el sistema destino.

## Limitaciones y validaciones pendientes

- No se ejecutaron pruebas de extremo a extremo con Mercado Pago real ni 2+ tótems y 2+ cajas. No habilitar producción hasta probar concurrencia y recuperación.
- Los checkouts activos todavía se reflejan en memoria para polling HTTP; tras reiniciar el servidor, se recuperan desde administración, no automáticamente en el navegador.
- El checkout MP QR fixed_amount debe validarse contra la respuesta real de Mercado Pago para evitar falsos positivos de pagos antiguos.
- El flujo de cobro de caja conserva la implementación heredada y no tiene reserva persistente de pago como IntraShop; se debe validar la integración completa en cada caja.
- Otros cambios de stock administrativos o integraciones externas pueden no consultar reservas. Deben centralizarse antes de asegurar inventario global.
- El descubrimiento de la web es por candidatos conocidos, no mDNS/UDP broadcast.
- La API key de registro de tótems sigue siendo compartida. Pendiente identidad de dispositivo y protección contra suplantación.
- Para múltiples procesos del servidor o escalado PostgreSQL/MSSQL se requiere adaptar transacciones, bloqueos y migraciones; no compartir SQLite por red.

## Pruebas mínimas antes de habilitar ventas

```bash
python -m pytest -q tests/test_intrashop_reservas.py tests/test_intrashop_entregas.py
cd intrashop && npm run build
```

En entorno de pruebas con credenciales Mercado Pago válidas:

1. Crear dos POS MP distintos y asignarlos a dos tótems; confirmar que no se puede asignar el mismo QR a ambos.
2. Stock 1 unidad: iniciar checkout desde ambos tótems a la vez. Solo uno debe obtener reserva.
3. Stock 2 unidades: iniciar dos checkouts simultáneos con QR diferentes; comprobar referencias únicas y registro de dos ventas sin duplicación.
4. Abrir la misma comanda en dos cajas y tomarla simultáneamente; solo una debe quedar asignada. Repetir con el mismo usuario conectado en ambas cajas.
5. Desconectar un tótem y reiniciar el servidor mientras MP tiene un cobro abierto. El stock debe permanecer retenido y el checkout aparecer en `checkouts-pending`.
6. Conciliar un pago aprobado y verificar que existe una sola venta y un solo descuento de stock.
7. Conciliar un checkout sin pago confirmado en MP y liberar la reserva manualmente con auditoría.
8. Verificar que la pantalla QR de cada caja muestra la imagen de su propio POS de Mercado Pago.

No se han ejecutado estas pruebas automáticamente en el repositorio desde esta sesión.

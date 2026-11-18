# POS Server — multicaja por terminal (IntraShop)

## Qué cambia

Cada terminal POS (equipo físico) tiene su propio identificador estable. POS Server
permite **una caja abierta por terminal** y múltiples terminales abiertas a la vez,
con un stock único transaccional en el servidor.

- La API key LAN **no identifica a un operador**. Para acceder a la caja asignada,
  el cliente envía `X-Terminal-Id` y un `Authorization: Bearer` obtenido al
  ingresar al POS. El servidor comprueba que coincida con la terminal usada
  al iniciar sesión y revalida permisos (`CAJA`, `VENTAS`, `CONFIGURACION`).
- `cajas.terminal_id` se agrega como columna opcional; un índice parcial
  garantiza como máximo una caja abierta por terminal en SQLite.
- Consultar caja abierta, vender, registrar gastos, consultar ventas/gastos
  y cerrar caja comprueban que el ID de caja corresponde a la terminal.
- El cierre bloquea únicamente si hay checkouts IntraShop pendientes en
  esa caja (y cualquier checkout antiguo sin caja de origen asignada).
- Cada checkout IntraShop conserva su `caja_id` desde que reserva stock,
  según la vinculación administrada del tótem con esa caja.

El modo **Kiosmico local** conserva su lógica previa de caja única.
Los clientes LAN usan un ID propio guardado **en el equipo local**, no en
`libreria.db` del servidor.

## Identificación por dispositivo

Linux: `~/.config/intrashop/pos-terminal-id` (o
`$XDG_CONFIG_HOME/intrashop/pos-terminal-id`).

Windows: `%LOCALAPPDATA%\\intrashop\\pos-terminal-id`.

No se genera un nuevo ID en cada sesión ni se guarda en una URL.
No copies este archivo a otra computadora: dos equipos con el mismo ID
compartirían la misma identidad de caja. Si se reinstala el SO o se pierde
el archivo, se debe reconfigurar esa terminal en los ajustes de Mercado Pago.

**Compatibilidad:** al actualizar desde la antigua identidad guardada como
`POS_TERMINAL_ID` en la SQLite, la identidad del cliente LAN cambia a la
local por equipo. Si tenías un QR Mercado Pago asignado a la **caja POS**
(terminal de tipo `caja`), verificá y, de ser necesario, **reasigná** el
QR al identificador nuevo desde Ajustes. Las vinculaciones de tótems
(con su propio `totem_id`) no cambian por esto.

## Primer arranque con dos computadoras POS

1. Instalar la misma versión del cliente IntraShop en **ambos equipos**, que
   apuntan a un único POS Server mediante `SERVER_URL`. No iniciar otra
   instancia de servidor apuntando a la misma SQLite.
2. Iniciar sesión con un usuario habilitado para `CAJA` y `VENTAS` en cada
   equipo. El inicio de sesión vincula el token a la terminal física.
3. Abrir caja con un importe de apertura en el POS A; abrir otra caja
   independientemente desde POS B.
4. Hacer una venta de prueba en A y otra en B. Comprobar en historial:
   `ventas.caja_id` distinto, `cajas.terminal_id` distinto y stock actualizado
   una sola vez por cada venta.
5. En **Ajustes → Mercado Pago → Asignación de QR por dispositivo**, asociar
   cada tótem con un QR MP exclusivo y seleccionar la caja específica en
   **Caja para ventas del tótem** (no usar “Automática” si hay varias
   cajas abiertas).
6. Simular pedidos desde ambos tótems, cancelar uno antes de pagar y
   confirmar otro en un entorno de pruebas controlado. Verificar que la
   venta aprobada y la comanda pertenezcan a la caja correcta.
7. Intentar cerrar A mientras tiene un checkout propio pendiente:
   debe bloquearse. La caja B puede seguir vendiendo y cerrar si sus
   pagos propios están resueltos.
8. Cerrar sesión en A y volver a ingresar: el ID local y la caja abierta
   deben conservarse, pero el token anterior debe quedar revocado.

**Precaución:** estas pruebas de código con Mercado Pago simulado no
sustituyen comprobar QR y conciliaciones reales en tus dispositivos.

## Caja antigua abierta (antes de la migración)

Una caja preexistente puede tener `terminal_id=NULL`. Por seguridad,
el servidor **no adivina a qué POS pertenece** ni la devuelve como caja
abierta de un equipo nuevo.

Si aparece el aviso “Existe una caja antigua sin terminal”:

1. Ingresá al POS con un usuario con permiso `CONFIGURACION`.
2. En **Abrir caja**, se mostrará el panel **Caja abierta de una versión anterior**.
3. Seleccioná el número que efectivamente corresponde a este POS, revisá
   la confirmación explícita y presioná **Asociar caja existente a este POS**.
4. El servidor guardará `terminal_id` y un registro en
   `pos_caja_auditoria`; **no** mueve ventas ni cambia saldos.

La adopción es irreversible desde la UI; revisá la caja elegida antes
de confirmar. Un operador sin `CONFIGURACION` debe pedir ayuda al administrador.

## Verificación automática

```bash
python -m pytest -q \
  tests/test_pos_multicaja_terminal.py \
  tests/test_pos_server_caja_ventas.py \
  tests/test_intrashop_caja_link.py
```

Se usan SQLite temporales creadas por las pruebas y mocks sin llamadas a MP.

## Limitaciones conocidas

- **POS Flet web servido desde un único proceso central:** la identidad
  local del servidor no representa por sí sola a cada navegador. No usar
  varias cajas web desde el mismo host hasta implementar identidad por
  sesión de navegador y autorización equivalente. La multicaja de este
  cambio está pensada para **clientes POS instalados en equipos físicos
  distintos**.
- Se conserva una vía de compatibilidad para API clientes sin ID de
  terminal, pero **solo** para cajas heredadas sin dueño. No pueden
  operar cajas de una terminal moderna.
- Los permisos de gastos/ventas/cierre están protegidos en los endpoints
  de caja. El historial general y ciertos endpoints administrativos
  anteriores mantienen su contrato y deberán revisarse al completar
  aislamiento de todas las operaciones de administración.

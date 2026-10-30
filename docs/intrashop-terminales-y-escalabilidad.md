# IntraShop: terminales LAN y evolución de base de datos

## Topología

- Una única instancia del servidor POS aloja FastAPI y es la autoridad para ventas, inventario, pagos y entregas.
- Todas las cajas (incluidas las que funcionan en modo cliente) utilizan el adapter HTTP `adapters/entregas.py`.
- Los tótems Astro consumen la misma API. No abren SQLite ni se conectan directamente a PostgreSQL o MSSQL.
- La confirmación de pago crea la venta y la comanda pendiente en una misma transacción. La entrega cambia únicamente el estado de preparación; nunca vuelve a descontar stock ni genera otra venta.
- La fecha de entrega se asigna automáticamente al confirmar. En la tienda LAN se permite pasar de pendiente a entregado directamente.

## Configuración de cajas cliente

En la configuración de red de cada POS, seleccionar modo `cliente`, definir `SERVER_URL=http://IP_DEL_SERVIDOR:8000` y la `API_KEY` del servidor. El permiso `ENTREGAS_INTRASHOP` debe estar habilitado en el rol del usuario.

**Seguridad pendiente:** la API actual autoriza las entregas mediante una API key compartida. El control del permiso se aplica en la interfaz Flet, pero no se valida todavía por sesión de usuario en el servidor. Por ello, la API key NO equivale a autenticación individual y no debe exponerse en navegadores de acceso público. Hasta implementar sesiones firmadas con autorización por rol en cada endpoint, usar únicamente una LAN de confianza y no habilitar entregas desde dispositivos no administrados.

## Escalabilidad de datos

El adapter HTTP es estable frente a un cambio de motor. Para pasar a PostgreSQL o MSSQL, mantener intactos los clientes y cambiar únicamente la capa de persistencia del servidor.

1. Centralizar las consultas de `intrashop_api.py` e `intrashop_entregas.py` en repositorios de datos del servidor.
2. Definir modelos y migraciones versionadas (por ejemplo, SQLAlchemy 2 + Alembic).
3. Migrar las tablas `ventas`, `venta_items`, `productos`, `movimientos_stock` e `intrashop_entregas` con claves foráneas e índices.
4. Sustituir `BEGIN IMMEDIATE` de SQLite por transacciones y bloqueo de filas del motor elegido.
5. Añadir claves de idempotencia por checkout y reservas de inventario con vencimiento.
6. Ejecutar pruebas de concurrencia con varios tótems y cajas antes de cambiar la configuración de producción.

No es necesario migrar de SQLite por instalar un segundo tótem: ambos se conectan al mismo servidor. El cambio de motor es útil cuando aumentan las escrituras concurrentes, la cantidad de sedes o los requisitos de disponibilidad y respaldo.

## Pruebas de aceptación antes de producción

- Dos cajas con usuarios diferentes visualizan la misma comanda.
- Un operador entrega y la segunda caja recibe el nuevo estado sin duplicar la operación.
- La venta entregada aparece en la vista operativa de ventas de hoy; el cobro ya estaba contabilizado.
- El servidor rechaza transiciones repetidas (HTTP 409).
- Un usuario sin permiso no puede operar entregas: **bloqueo servidor pendiente**.
- Reinicio del servidor no pierde pedidos.
- Desconexión de red no crea falsas entregas.
- Dos tótems que pagan simultáneamente no pueden vender más unidades que las disponibles: **reserva de stock pendiente**.

No se ejecutaron todavía pruebas integrales de hardware ni pagos reales.

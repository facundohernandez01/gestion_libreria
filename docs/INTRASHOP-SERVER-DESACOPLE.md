# Arquitectura de productos — noviembre 2026

## Dos productos, responsabilidades distintas

- **Kiosmico** (`main`): POS independiente. Admite SQLite local o varias cajas mediante API FastAPI. No contiene tótems, publicación de artículos Astro, entregas IntraShop ni branding IntraShop.
- **IntraShop** (`feature/mercadopago-oauth`): solución distribuible localmente con **tres ejecutables/procesos lógicos obligatorios**: POS (Flet), POS Server (FastAPI + propietario único de SQLite) y tótem (Astro empaquetado con Tauri). Pueden coexistir en una PC o distribuirse en LAN. No requiere base de datos en Internet.

## Contrato de ejecución IntraShop

1. Iniciar POS Server por separado: `python pos_server.py --headless --host 0.0.0.0 --port 8000` (o GUI `python pos_server.py`).
2. Iniciar el POS como **cliente HTTP** del servidor. En la implementación actual usar `MODO_RED=cliente`, `SERVER_URL=http://127.0.0.1:8000` cuando es la misma máquina, y `POS_EXTERNAL_SERVER=1`. **Atención:** `core/db_factory.py` prioriza el valor `MODO_RED` persistido en SQLite sobre la variable de entorno; verificar configuración efectiva antes de operar. No habilitar modo servidor desde el POS IntraShop.
3. Iniciar el tótem Astro/Tauri apuntando a POS Server por LAN. No conectarlo a SQLite.
4. Comprobar `/health`, autenticación, catálogo y cobro antes de permitir ventas.

**Estado de transición:** el POS aún conserva el selector local/cliente/servidor heredado. No se debe retirar ni cambiar silenciosamente antes de completar paridad HTTP de caja, stock, compras, configuración, backup y facturación. El objetivo es ocultarlo en la edición IntraShop, no eliminarlo del producto Kiosmico.

## Propiedad y seguridad de datos

- Solo POS Server escribe la SQLite operativa de IntraShop y almacena imágenes y comprobantes.
- Nunca transmitir credenciales o API keys por query string; usar encabezados de autenticación y permisos de operador. Las API keys compartidas heredadas de los endpoints de catálogo requieren migración controlada.
- Cancelar un QR requiere cerrar la orden en Mercado Pago y verificar el estado antes de liberar stock. Nunca asumir que cerrar un modal anula un cobro.
- Backups consistentes en servidor, restauración controlada y datos fuera de carpetas de instalación.

## Portabilidad de mejoras a main

Revisar y portar selectivamente: stepper de inicio, backups, roles/permisos, correcciones de caja, stock, compras, rendimiento y UX general. Mantener splash y branding propios de Kiosmico. Excluir módulos de tótems, catálogo Astro, entregas y QR específico de tótems. **No realizar merge completo entre ramas.** Registrar por funcionalidad los commits y pruebas de regresión.

## Orden de ejecución

1. **P0** Inventario de rutas de acceso SQLite, métodos faltantes de ApiClient, flujos de configuración y dependencias entre procesos.
2. **P0** Completar API cliente/servidor para POS IntraShop; pruebas de caja, artículos, imágenes, stock y permisos; corregir acceso local accidental.
3. **P0** Consolidar POS Server como único dueño de datos, arranque/parada, health, instancia única, migraciones y backups.
4. **P0** Revisar pagos QR: cancelar, idempotencia, reservas y concurrencia; pruebas de pagos tardíos.
5. **P1** Simplificar UX IntraShop: sin selector de modo servidor POS, configuración LAN, autodescubrimiento y estado visible.
6. **P1** Empaquetar Astro/Tauri y servidor; instalador y actualización local con persistencia de datos.
7. **P1** Pruebas E2E con una y varias cajas/tótems, reinstalación, desconexión LAN y recuperación.
8. **P2** Comparar mejoras POS frente a main y portar solo funciones generales con pruebas.

## Criterio de cierre

Instalación limpia, reinicio, edición de artículos y fotos, cobro/cancelación, entrega, backup/restauración y operación multi-caja sin acceder desde clientes a SQLite. Cada etapa requiere pruebas antes de declarar resuelta la incidencia.

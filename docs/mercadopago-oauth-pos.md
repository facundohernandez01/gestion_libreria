# Mercado Pago OAuth (POS de escritorio + IntraShop LAN)

Esta rama agrega **solo** la vinculación del vendedor con Mercado Pago mediante navegador y backend central, sin alterar activación de licencias, caja, stock ni checkout QR.

## Requisitos

1. Desplegar el backend de `plugin_marketplace` con las nuevas rutas OAuth y las variables de entorno de su documentación.
2. En `pos_server.py`, iniciar la instancia LAN habitual. Mantener SQLite y las reglas de acceso existentes.
3. Abrir el POS como administrador, Ajustes → Mercado Pago.
4. Introducir una única vez la **URL HTTPS** pública del backend central (`MP_OAUTH_HUB_URL`, también configurable en el formulario).
5. Pulsar «Conectar Mercado Pago», iniciar sesión en el marketplace, autorizar en Mercado Pago y regresar a Ajustes.
6. Esperar la confirmación «Conectado», y cargar los POS existentes. Asignar un QR distinto a cada tótem/caja.
7. «Crear nuevo QR / POS» utiliza el token OAuth **solo en el servidor LAN** y crea un QR asociado a una sucursal existente.

En modo cliente, el POS usa los endpoints autenticados `/tienda/admin/mp-oauth/start`, `/status`, `/pos`, `/pos/create` y `/disconnect`; no transmite el Access Token de Mercado Pago a la caja cliente.

## Persistencia y seguridad

- Solo el servidor POS conserva `MP_OAUTH_INSTALLATION_ID` y el secreto de instalación cifrado.
- Se crea el archivo `.mp-oauth-local.key` junto a la base de datos. Debe ser privado y respaldarse junto con la base; está en `.gitignore`.
- El refresh token permanece en el marketplace central. Los access tokens se mantienen solo en memoria de `pos_server` durante su vida útil.
- La conexión OAuth tiene prioridad cuando está activa. El método manual anterior permanece disponible **hasta migrar y comprobar cobros**. No se utilizan IDs de una tienda manual anterior al conectar otra cuenta.
- La operación en LAN funciona sin depender de mantener abierto `main.py`, pero el servidor local y una conexión con Mercado Pago son necesarios para los cobros.
- Para desconectar, utilizar Ajustes → Mercado Pago → «Desconectar».
- La plataforma central usa la identidad del usuario del marketplace para separar cuentas. La base de datos local continúa siendo exclusiva de cada comercio.

## Errores

- **403 PA_UNAUTHORIZED_RESULT_FROM_POLICIES:** denegación de Mercado Pago. No crear sucursales ficticias; revisar permisos de la aplicación y cuenta.
- **No hay sucursal:** vincular o crear una sucursal real en Mercado Pago antes de crear un POS.
- **Backend OAuth no configurado:** definir su URL HTTPS y variables de OAuth del deployment.
- **Se terminó el tiempo de autorización:** pulsar nuevamente «Conectar».

## Pruebas mínimas antes de producción

- Ejecutar `python -m compileall -q config.py services/mp_oauth_api.py services/mp_oauth_bridge.py services/mercadopago_service.py api_server.py`.
- Probar vinculación y refresh token con dos usuarios distintos del marketplace.
- Verificar que un tótem no pueda cobrar con el POS de otro comercio.
- Probar desconexión, reinicio de `pos_server.py` y reconexión sin abrir la caja.
- Verificar operaciones manuales preexistentes cuando OAuth no está activado.

# IntraShop — revisión funcional y seguridad LAN (noviembre 2026)

## Estado y alcance

Los tests incluidos **no usan una cuenta de Mercado Pago ni la impresora real**, no escanean la LAN desde CI y no tocan la SQLite operativa. Cubren el servicio de caja por HTTP, datos simulados del POS, la construcción del diálogo Flet, emparejamiento de dispositivos e interfaz de Astro con Chromium.

### Problemas y correcciones

| Área | Causa | Cambio |
|---|---|---|
| Cerrar caja POS (overlay gris) | `AlertDialog(open=True)` se pasaba a `page.show_dialog`, que exige un diálogo aún cerrado; datos consultados antes del montaje | Crear cerrado, mostrar, iniciar consulta después y usar `page.pop_dialog`. Ya no ocultar RuntimeError con overlay fallback |
| Carrito Astro | Sin botón explícito de borrar toda la línea | Botón Eliminar por producto, accesible, que borra completamente la línea y actualiza total |
| Descubrimiento LAN | Registro de IP manual | Botón en POS Server que, **solo tras confirmación**, consulta tabla de vecinos y hace 1 ping por dirección de la /24 privada. No identifica de forma certificada una PC ni vincula QR automáticamente |
| Identidad tótem | IP sola no autenticaba al dispositivo | Código de emparejamiento **de un solo uso, 10 minutos**, emitido solo desde consola POS Server; canje por cookie aleatoria HttpOnly, SameSite Strict, 30 días, vinculada con IP e ID del tótem |
| Rotación / cambio de IP | Tokens anteriores podían permanecer activos | Se revocan sesiones al cambiar IP, quitar IP o retirar tótem |
| API LAN | `API_KEY=libreria-lan` conocida públicamente | Nueva clave aleatoria de alta entropía, guardada en `~/.config/intrashop/server_keys` con permisos 0600. Se bloquea el arranque si la clave sigue siendo `libreria-lan` |
| API y navegador | CORS permitía cualquier origen | CORS denegado por defecto para otros orígenes. Astro publicado desde POS Server usa mismo origen |
| POS inicio de sesión | `login_recordado.json` guardaba contraseñas en claro | Se guardan solamente usuarios; credenciales antiguas se depuran al leer, sin reutilizar el campo clave |
| API pública | `/tienda/health` devolvía ruta de SQLite | Ya no expone ubicación del archivo |
| Identificación checkout | UUID de orden accesible podía permitir consulta/cancelación | Obtener estado y cancelar exigen cookie del **mismo** equipo/tótem |

## Primera configuración (cambios operativos importantes)

1. **POS Server**: eliminá `API_KEY=libreria-lan` del `.env` si existía; se generará una clave fuerte. Reiniciá POS Server. No copies la clave en URLs.
2. Desde la **consola física de POS Server** hacé clic en **Copiar clave LAN**. En cada POS cliente: inicio de sesión → **Configurar conexión LAN** → pegá la URL del servidor y la clave; reiniciá el POS. La clave se guarda en archivo privado del usuario (0600).
3. **POS Server → Tótems**: primero **Buscar equipos LAN**; elegí una IP detectada, confirmá la asociación al tótem y configurá su QR. Las IPs detectadas no son una prueba de identidad; reservar DHCP/MAC desde el router.
4. **Generar código de acceso** sobre el tótem. En el navegador del propio tótem ingresá el código. El comercio y el QR ya deben estar vinculados en POS Server.
5. Al borrar las cookies o cambiar de navegador, generá otro código. **La relación entre el tótem y su QR permanece intacta.**

## Credenciales de usuarios y puesta en marcha tras actualizar

Se eliminaron credenciales de administrador implícitas y los usuarios se autentican
contra su registro de la tabla `usuarios`. Las nuevas contraseñas se almacenan
mediante PBKDF2-HMAC-SHA256 con sal aleatoria; los registros legacy de texto claro
se migran a hash tras un inicio de sesión válido. Las contraseñas no se devuelven
en `/usuarios` o consultas de roles y no se guardan en `login_recordado.json`.

**Cambio obligatorio si antes ingresabas con admin/admin o una contraseña de
administrador débil:** abrí la GUI física de **POS Server** y pulsá
**«Clave ADMIN»**. Establecé una clave nueva de al menos 12 caracteres y
confirmala. Se actualiza el registro del administrador, se borra
`config.LOGIN_CLAVE` legado y se revocan las sesiones previas. El cambio no
elimina usuarios, ventas, cajas ni el histórico.

En instalaciones nuevas que no tengan una contraseña fuerte configurada, la
cuenta ADMIN se crea inicialmente deshabilitada hasta usar esa opción de
consola local. **En modo headless** hay que configurar la clave mediante una
interfaz/CLI local administrativa antes de permitir usuarios de POS.
No publicar una consola de administración por HTTP sin acceso previo.

El endpoint genérico `/config` ya no entrega `ACCESS_TOKEN`,
`LOGIN_CLAVE`, `MP_ACCESS_TOKEN` y otras claves sensibles, ni permite
modificarlas usando solamente la clave API LAN. Para esos ajustes usar la
administración local o los endpoints administrativos autenticados.

## Seguridad imprescindible para producción

**ATENCIÓN: la red LAN no es automáticamente una red segura.** En HTTP, un atacante con acceso a interceptar tráfico puede modificar la página/QR, obtener contraseñas, robar cookies o claves LAN. Las cookies y los códigos no protegen frente a MITM si los datos circulan sin cifrar. La autenticación por IP tampoco demuestra identidad de hardware.

**Para no permitir cobros por HTTP**, activar `INTRASHOP_ENFORCE_HTTPS=1`, poner FastAPI detrás de un proxy HTTPS, y **no exponer el puerto HTTP de FastAPI a la LAN**.

Ejemplo conceptual con Caddy y DNS interno `pos.intra.lan`:

```caddyfile
pos.intra.lan {
    tls internal
    reverse_proxy 127.0.0.1:8000
}
```

La máquina POS Server debe escuchar en `127.0.0.1:8000` (por ejemplo `python pos_server.py --headless --host 127.0.0.1`), con firewall que niegue conexiones LAN directas a 8000. Los equipos deben resolver `pos.intra.lan` a la IP del servidor y **confiar explícitamente en la CA del proxy**, antes de acceder a `https://pos.intra.lan/intrashop/`. No desactivar verificación TLS en Python o navegador. Si se usa un proxy, configurarlo para que reemplace correctamente `X-Forwarded-For` y solo confiar en la IP del proxy; una cabecera enviada por el navegador no es identidad.

**Importante**: `INTRASHOP_ENFORCE_HTTPS` protege únicamente endpoints de emparejamiento y checkout. POS Server completo también debe quedar detrás de HTTPS para proteger logins y la API de caja. La protección de red se completa con segmentación Wi‑Fi/VLAN, contraseña del administrador, actualizaciones y firewall. La clave LAN compartida aún da acceso a operaciones POS que dependen de ella; es un riesgo residual que exige migrar todas las escrituras a autorización por rol/sesión.

En desarrollo local, no configurar `POS_CORS_ORIGINS=*`. Si Astro de desarrollo debe llamar a otro origen, definir `POS_CORS_ORIGINS` como una lista explícita de orígenes de confianza; en producción usar un único dominio/origen.

## Pruebas automáticas

`tests/test_cierre_caja_flet_smoke.py`: construye diálogo en Flet 1.0.4, muestra después de crearlo y ejecuta arqueo.

`tests/test_pos_server_http_functional.py`: FastAPI por HTTP contra una SQLite temporal: apertura/resumen/arqueo/cierre, y canje de código de tótem con restricción IP para ver/cancelar pedidos.

`tests/test_lan_security_and_pairing.py`: identidad, revocación, IP distinta, expiración de código, escaneo limitado y seguridad por defecto.

`tests/test_intrashop_browser_e2e.py`: Chromium y Astro compilado; test funcional con backend de prueba: ver productos, emparejar, agregar, **Eliminar**, volver a agregar, iniciar pago y cancelar QR sin esperar servidor. Sin envío de dinero.

**Faltan pruebas físicas en tu entorno:** apertura/cierre de caja desde escritorio Flet y Flet web, impresora térmica, Mercado Pago real, configuración de red y un test de proxy TLS instalado. Ningún test puede demostrar ausencia total de vulnerabilidades.

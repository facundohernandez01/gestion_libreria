# IntraShop — tótems numerados y vínculo permanente en POS Server

## Problema resuelto

El UUID que antes se generaba con `localStorage.intrashop_totem_id` cambiaba al borrar caché, volver a instalar el navegador o abrir la tienda en otra sesión. Eso creaba tótems distintos y dejaba la relación con el POS/QR de Mercado Pago en el registro anterior.

**La fuente de verdad ahora es la SQLite de POS Server:** nombre, identificador, IP confirmada y relación con Mercado Pago. El navegador no crea ni renombra tótems.

## Primera configuración

1. En **POS Server → Tótems**, aparecen los IDs `totem-001` … `totem-008`, precreados y sin IP. **Crear siguiente tótem** agrega 009, 010, etc.
2. En el router, asignar **reserva DHCP por MAC** o IP estática a cada equipo. Evita que una IP cambie o se reutilice inadvertidamente.
3. Seleccionar un tótem, pulsar **Vincular / cambiar IP**, ingresar la IP del dispositivo y confirmar. El servidor comprueba que ninguna otra terminal use esa IP.
4. Elegir **Configurar QR** y asignar el POS Mercado Pago exclusivo y la caja. Esos datos quedan en el servidor y no se borran al limpiar el navegador.
5. Abrir `http://IP_DEL_SERVIDOR:8000/intrashop/` en el equipo vinculado. La tienda identifica al tótem por la IP **que observa el socket de FastAPI**, no por el ID enviado desde el navegador. La compra sólo se habilita si tiene IP confirmada y QR vinculado.
6. `/intrashop/admin` sólo configura la URL del servidor para la página web y muestra el estado del vínculo. No puede crear, cambiar ni reasignar un tótem sin autorización.

### Migración de tótems existentes

**No se borran ni renombran los UUID anteriores y tampoco se modifican sus QR.** Los registros viejos siguen apareciendo en el panel de POS Server. Seleccionar el registro con QR existente y confirmar su IP en **Vincular / cambiar IP**. La tienda recuperará su identidad histórica aunque no exista `localStorage`.

No asignar por accidente la misma IP a un slot 001 mientras el QR antiguo sigue asociado a otro registro. Debe vincularse el **tótem antiguo** si se quiere conservar el QR y las comandas previas.

## Restricciones deliberadas

- El frontend nunca llama a `/tienda/totems/register`: esa ruta devuelve HTTP 410, y el checkout exige que `totem_id` coincida con el vínculo IP guardado.
- No se usa `X-Forwarded-For` para descubrir la identidad: esas cabeceras se pueden falsificar si no hay un proxy explícitamente confiable.
- **La IP no es una credencial criptográfica.** Si un equipo distinto ocupa esa misma IP, podría hacerse pasar por el tótem. Usar red LAN confiable y reserva DHCP. Si hay dispositivos tras **NAT/proxy, VMs o varias tiendas en el mismo host/IP**, la identidad por IP no distingue terminales: desplegar detrás de IPs distintas o planificar credenciales individuales administradas.
- Si cambia la IP, el cobro queda bloqueado hasta que el administrador confirme la nueva IP en POS Server. El QR y el historial permanecen asociados al mismo ID.
- Las comandas siguen filtrándose en POS por identificador, como antes. No se cambia el flujo de entrega ni el historial.
- El navegador puede borrar toda su caché: al volver a abrir la tienda consulta `GET /tienda/totems/identity` y recibe el mismo nombre/ID/QR asignado desde POS Server.

## Rutas del servidor

- `GET /tienda/totems/identity`: identidad y estado QR por IP observada (pública en la LAN).
- `GET /tienda/admin/totems`: listado, requiere sesión de administrador POS.
- `POST /tienda/admin/totems/provision`: alta numerada, requiere administrador.
- `PUT /tienda/admin/totems/{id}/ip`: vincular/reasignar IP, requiere administrador.
- `DELETE /tienda/admin/totems/{id}/ip`: quitar IP sin borrar QR ni historial, requiere administrador.

Las pruebas automáticas usan SQLite temporal y simulan IPs; no reemplazan una prueba de red real.

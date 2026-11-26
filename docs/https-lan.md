# HTTPS local IntraShop sin DNS ni certificados pagos

## La opción para usuarios del software

**Nadie necesita tener DNS, dominio público ni conocimientos de servidores.**
IntraShop usa directamente la dirección IP privada de la computadora que
ejecuta POS Server. Ejemplo:

- POS y API: `https://192.168.1.100`
- Tienda/tótem: `https://192.168.1.100/intrashop/`

Caddy genera gratuitamente el certificado TLS con su CA privada y lo renueva
automáticamente. **El único requisito que no puede omitirse es que cada
dispositivo cliente autorice una vez la CA raíz pública del POS Server.**
No es seguro evitarlo pulsando «Continuar de todos modos» ni deshabilitando
la verificación de certificados. Solo se confía en el certificado del comercio,
no en una CA privada compartida entre instalaciones.

## Instalación guiada en Ubuntu/Kubuntu

**Desde la aplicación POS Server:** pulsar **HTTPS local**, confirmar la IP de
la PC y seguir el asistente. Este abre una terminal para solicitar una vez los
permisos administrativos, instalar/configurar Caddy y generar el archivo
`.env` necesario. **El usuario no debe editar el .env ni configurar DNS.**

También se puede ejecutar manualmente el mismo asistente desde la carpeta
de IntraShop:

```bash
python3 deploy/configurar_https_ip.py
```

Para indicar una IP concreta, por ejemplo por tener varias tarjetas de red:

```bash
python3 deploy/configurar_https_ip.py --ip 192.168.1.100
```

Para ver qué se crearía **sin modificar archivos ni instalar Caddy**:

```bash
python3 deploy/configurar_https_ip.py --ip 192.168.1.100 --mostrar-config
```

El asistente:

1. Detecta o solicita la IP IPv4 privada; nunca usa dominios ni escanea Internet.
2. Instala Caddy mediante `apt` si falta, con autorización de sudo.
3. Valida el Caddyfile antes de aplicarlo. Si existía una configuración
   ajena a IntraShop pide permiso y guarda una copia; no la reemplaza
   silenciosamente.
4. Configura Caddy en el puerto 443 y FastAPI como backend en
   `127.0.0.1:8000`. Nunca expone la API HTTP al resto de la LAN.
5. Crea o actualiza automáticamente `.env` con
   `INTRASHOP_ENFORCE_HTTPS=1` y
   `POS_PUBLIC_URL=https://IP_DEL_SERVIDOR`, conservando el resto
   de configuraciones, incluidas las credenciales existentes.
6. Intenta exportar **solo el certificado raíz público** y mostrar su
   huella SHA-256, nunca su clave privada.

**Reiniciar POS Server** después de finalizar el asistente. Si el servicio
Caddy quedó configurado correctamente, en la LAN únicamente hay que ingresar
a `https://IP_DEL_SERVIDOR/intrashop/`.

No modificar ni borrar `libreria.db`, carpetas de datos de Caddy ni sus
claves privadas. Si el IP del servidor cambia, ejecutar otra vez el
asistente y actualizar la dirección en las terminales. Por eso se recomienda
activar la **reserva DHCP** en el router, pero no hace falta que el usuario
configure DNS.

### La parte que requiere aprobación en cada cliente

Cada POS cliente, tótem, PC o tablet debe confiar en el certificado raíz
**público** emitido por el servidor. En Ubuntu, el asistente intenta
copiarlo a:

```text
~/.local/share/intrashop/certificados/intrashop-root-ca.crt
```

También puede estar en la ruta de datos de Caddy:

```text
/var/lib/caddy/.local/share/caddy/pki/authorities/local/root.crt
```

1. Exportar/copiar **solo el `.crt` público** a cada equipo autorizado,
   idealmente por USB o mediante un canal autenticado.
2. **Verificar su huella SHA-256** contra la mostrada físicamente en POS Server
   para impedir que un atacante entregue una CA falsa.
3. El operador autoriza una vez la instalación de esa CA en el equipo.
   En Windows, utilizar «Entidades de certificación raíz de confianza» con
   permisos de administrador; en Ubuntu, la carpeta
   `/usr/local/share/ca-certificates/` y `sudo update-ca-certificates`;
   Android/iPadOS/iOS tienen procedimientos y restricciones propios.
4. Confirmar que el navegador abra `https://IP_DEL_SERVIDOR/intrashop/`
   **sin advertencias de certificado**. Si el navegador mantiene una
   advertencia, no habilitar cobros hasta corregirla.

En POS Python/Linux, `httpx` puede no usar automáticamente la CA del sistema:
tras instalarla con `update-ca-certificates`, usar
`SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt` en el servicio/terminal
que arranca el POS. En Windows puede ser necesario un bundle PEM confiable
para `httpx`. **Nunca usar `verify=False`.**

Para un producto final descargable, la autorización del certificado deberá
quedar dentro del instalador de POS/tótem con un aviso explícito y
verificación de la huella; no es posible instalar una CA confiable
silenciosamente desde una página web no confiable. El asistente Linux del
servidor ya está implementado; **el instalador multiplataforma de clientes
aún es una tarea pendiente**.

## Verificación técnica

En el servidor:

```bash
ss -ltnp | grep -E ':443|:8000'
```

Esperado: Caddy en 443 y Python **solo** en `127.0.0.1:8000`, no
`0.0.0.0:8000`.

Desde un cliente con la CA autorizada:

```bash
curl -fsS https://192.168.1.100/health
```

La URL `http://192.168.1.100:8000/health` no debe estar disponible desde
la LAN. HTTPS obliga a pasar por Caddy para login, API de ventas, cierre
de caja, catálogo y cobros. La identidad del tótem y su QR siguen
administrados por POS Server, con código de emparejamiento.

## Para usuarios que *sí* tienen un dominio

Una URL con nombre (mDNS, DNS local, nombre público) es opcional y
no es un requisito del instalador. Un dominio propio con DNS-01
permite usar certificados públicos gratuitos, normalmente sin importar
la CA local en cada PC, pero requiere una integración adicional de
gestión DNS. Para pequeños comercios, el modo IP privada es más directo.

Fuentes oficiales:
- https://caddyserver.com/docs/automatic-https
- https://caddyserver.com/docs/caddyfile/directives/tls
- https://caddyserver.com/docs/caddyfile/concepts

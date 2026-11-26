# HTTPS local sin pagar certificados — IntraShop (Ubuntu + Caddy)

## Qué se obtiene

Una sola URL para POS, tótems y tienda: `https://pos.home.arpa/intrashop/`.
El navegador habla HTTPS con Caddy. Caddy entrega tráfico a FastAPI solo
por `127.0.0.1:8000` en **la misma PC**; FastAPI no queda abierto por HTTP en
la LAN. La CA y los certificados se crean gratis con `tls internal`.

**No necesita dominio público, port forwarding, IP fija pública ni conexión
entrante de Internet.** Para que los equipos confíen en el certificado hay
que distribuir una sola vez el **certificado raíz público** de Caddy,
nunca `root.key`, claves privadas ni archivos de credenciales.

## Requisitos

- La PC con POS Server tiene IP LAN estable, preferiblemente una reserva DHCP.
- Todas las PCs y tótems están en una LAN que pueden alcanzar al servidor en
  443/TCP. El servidor NO permite conexiones desde la LAN a 8000/TCP.
- DNS interno del router que resuelva `pos.home.arpa` a esa IP. Como
  alternativa temporal, incluir la misma entrada en `/etc/hosts` de cada
  Linux o `C:\Windows\System32\drivers\etc\hosts` en Windows.
- Caddy instalado como servicio en la PC servidor (Ubuntu 24.04).
- Python y el POS ya funcionan localmente; Astro compilado `pnpm run build`.
- `API_KEY` de LAN y clave ADMIN ya configuradas como credenciales seguras.

Ejemplo para IP reservada `192.168.1.100` (CAMBIAR por IP real):

```text
192.168.1.100   pos.home.arpa
```

La DNS o el archivo hosts **no** prueba identidad del servidor; instalar y
validar la CA de Caddy sí permite autenticar su certificado. No guardar
contraseñas o claves LAN en el hosts.

## 1. Instalar y configurar Caddy (servidor Ubuntu)

Instalar Caddy desde el repositorio oficial, o desde los paquetes disponibles
para Ubuntu. Confirmar `caddy version` y que el servicio arranca con
`systemctl status caddy`.

Desde la carpeta del repositorio:

```bash
sudo cp deploy/Caddyfile.intrashop-lan.example /etc/caddy/Caddyfile
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl restart caddy
sudo systemctl status caddy --no-pager
```

El ejemplo usa `pos.home.arpa`; cambiar el nombre **en Caddyfile, DNS y
POS_PUBLIC_URL a la vez** si elegís otro. Caddy utiliza `tls internal`,
generando la raíz CA local y el certificado del servidor.

**No es necesario cambiar Caddy para WebSockets de Flet:** su reverse_proxy
maneja WebSocket automáticamente.

## 2. Iniciar POS Server sólo por loopback

En el `.env` que utiliza el POS Server, colocar:

```dotenv
INTRASHOP_ENFORCE_HTTPS=1
POS_PUBLIC_URL=https://pos.home.arpa
```

No activar `POS_CORS_ORIGINS=*`. No incrustar API keys en Astro. El
`POS_PUBLIC_URL` debe coincidir exactamente con el certificado.

Iniciar mediante la misma GUI:

```bash
python pos_server.py
```

O como servicio sin GUI:

```bash
python pos_server.py --headless
```

Con `INTRASHOP_ENFORCE_HTTPS=1` el POS Server **fuerza** Uvicorn a
`127.0.0.1`, incluso si una configuración anterior pedía `0.0.0.0`.
Uvicorn procesa `X-Forwarded-Proto` y `X-Forwarded-For` exclusivamente
si llegan desde `127.0.0.1` o `::1` (Caddy local). Se rechaza todo HTTP
directo por la aplicación; nunca se permite confiar en proxies arbitrarios.

No utilizar simultáneamente otra instancia vieja del servidor en 0.0.0.0.
Si existe un servicio previo, detenerlo primero; revisar:

```bash
ss -ltnp | grep -E ':443|:8000'
```

La salida de `:8000` debe mostrar solo `127.0.0.1:8000`. Debe existir
un listener en `:443` de Caddy. Al abrir `https://pos.home.arpa/health`
desde otra PC debería aparecer el estado del POS Server. Una llamada
`http://IP_SERVIDOR:8000/health` desde la LAN **debe fallar**.

## 3. Instalar la CA en todos los equipos

En Ubuntu cuando Caddy corre como servicio de systemd, la raíz **pública**
normalmente está en:

```text
/var/lib/caddy/.local/share/caddy/pki/authorities/local/root.crt
```

Copiar **solo** ese `root.crt` a cada PC/tótem de confianza. Antes de
instalarla, comparar su huella digital con una huella obtenida directamente
en la PC servidor (fuera del canal LAN susceptible a suplantación):

```bash
openssl x509 -in root.crt -noout -fingerprint -sha256
```

En Ubuntu cliente:

```bash
sudo install -m 0644 root.crt /usr/local/share/ca-certificates/intrashop-root.crt
sudo update-ca-certificates
```

Firefox puede requerir importar la CA desde sus ajustes de certificados
si no usa el almacén de confianza del sistema. En Windows, importar
`root.crt` en el almacén **Entidades de certificación raíz de confianza**
con permisos administrativos. En Android, importar la CA del usuario por los
ajustes de seguridad/certificados; no todas las apps Android confían en CAs
de usuario. Comprobar cada navegador con `https://pos.home.arpa` sin
advertencias. **No desactivar validación TLS ni usar --insecure o -k**.

Distribuir la CA solo a dispositivos administrados. Una CA raíz es una
autoridad de confianza importante; no entregar su **clave privada** ni
permitir que cualquier equipo de la red configure el Caddy.

## 4. Conectar POS y tótems

- En POS cliente → **Configurar conexión LAN**: usar
  `https://pos.home.arpa`, sin `:8000`. Configurar la clave LAN en el
  archivo local privado de la terminal y reiniciar el POS.
- En cada tótem: entrar a `https://pos.home.arpa/intrashop/`, verificar la
  identidad IP desde POS Server, asignar el QR y luego generar el código
  temporal de emparejamiento. La cookie HttpOnly no sustituye el certificado.
- Astro compilado servido por POS Server utiliza el **mismo origen** en
  `:443` para APIs y QR; no intenta conectar a `:8000` ni reutiliza una
  URL HTTP vieja de `localStorage`.
- La GUI POS Server abre la URL HTTPS pública, no la HTTP local.

## 5. Validación y seguridad

Desde una PC cliente (CA instalada):

```bash
curl -fsS https://pos.home.arpa/health
curl -I https://pos.home.arpa/intrashop/
```

No se espera `curl -k`. Si aparece error de certificado, revisar
`root.crt`, DNS/hosts, nombre certificado y fecha/hora de las PCs.

Comprobar también que no se pueda entrar por HTTP directo a la API desde
otra PC. Mantener deshabilitado el acceso a 8000/TCP desde la LAN
mediante el bind de loopback y firewall. El puerto 80/TCP de Caddy puede
redirigir a HTTPS; nunca debe servir la aplicación sin cifrar.

Un atacante que controla una CA instalada, el router DNS, la PC servidor,
o un operador administrador sí podría manipular el servicio. HTTPS por sí
solo **no** reemplaza roles, contraseñas, actualizaciones ni auditoría.
La clave API compartida para varias cajas todavía debe migrarse a permisos
de operaciones individuales; no declarar el sistema auditado o invulnerable.

## ¿Y con un certificado público gratuito?

Es posible emitir certificados gratuitos con Let's Encrypt para un
**dominio público propio** aun si el servidor no está abierto a Internet,
usando validación DNS-01 y automatización compatible con el proveedor DNS
(normalmente un plugin DNS del proxy). En ese caso los navegadores no
necesitan instalar la raíz privada. Para una LAN sin dominio, `tls internal`
es más simple. Los certificados para `pos.home.arpa` no pueden emitirse
por una CA pública de Internet.

## Recuperación

Desactivar TLS solo para diagnóstico local: detener el servicio Caddy,
quitar temporalmente las dos variables de HTTPS y reiniciar POS Server.
**No utilizar esta opción como instalación permanente de cobros**.
Nunca reemplazar la base `libreria.db` ni borrar los datos de Caddy para
resolver problemas de certificado: se perdería la confianza de todos los
clientes y habría que redistribuir la CA.

Fuentes oficiales: https://caddyserver.com/docs/caddyfile/directives/tls,
https://caddyserver.com/docs/running y https://uvicorn.dev/settings/.

# IntraShop Suite — un instalador, tres perfiles (roadmap de distribución)

## Objetivo de producto

El cliente descarga **un único instalador de la Suite**. El asistente pregunta
qué uso tendrá la PC y prepara automáticamente los componentes necesarios,
sin mostrar puertos, .env, DNS, certificados, Python, Rust, terminales ni
copias manuales de API keys. Ningún perfil requiere una suscripción ni un
certificado TLS de pago.

Perfiles seleccionables, combinables si el hardware lo permite:

| Perfil | Se instala | Configuración del usuario |
| --- | --- | --- |
| **Servidor POS** | FastAPI/SQLite, consola de administración y servicio HTTPS local | Crear clave ADMIN, confirmar interfaz/IP LAN, autorizar Caddy |
| **Caja POS** | Aplicación Flet/Python empaquetada, ticket/impresora, conector LAN | Elegir comercio detectado, confiar en CA con verificación, iniciar sesión |
| **Tótem IntraShop** | Cliente Tauri (WebView2 en Windows) o acceso directo al catálogo desde navegador | Emparejar con código de un uso y configurar pantalla completa |

La aplicación Tauri no replica stock ni guarda QR: abre **la tienda
servida por POS Server** por HTTPS. Al cancelar o validar pagos siempre se
consulta el servidor; ningún código de pago se incrusta en el ejecutable.

## Experiencia de instalación final propuesta

1. El instalador pregunta **¿Qué querés instalar?** y muestra tres perfiles.
   Recomendar Servidor + Caja cuando sea la única PC del comercio.
2. Si es Servidor, se crea una **contraseña de administrador del comercio**
   (no una contraseña maestra universal), se inicializa la base local y
   se habilitan Caddy y el firewall sin que el usuario elija certificados.
3. El servidor obtiene su IP LAN y prepara un certificado gratuito para esa IP.
   Si hay DHCP dinámico, advierte sobre la necesidad de mantenerla o
   reservarla; no se configuran DNS ni archivos hosts.
4. En la consola POS Server, **Instalar / conectar equipos** permite:
   - **Abrir tienda**: muestra/copia solo URL HTTPS, sin tokens.
   - **Exportar kit de conexión**: CA raíz pública y huella, manifest sin
     secretos, para equipos sin conexión directa a Internet. El perfil Tótem
     incluye también `Abrir-IntraShop.url`: acceso directo Windows a la
     tienda HTTPS, sin tokens ni instalador adicional.
   - **Ver ejecutables**: solo compilaciones realmente presentes en
     `distribution/builds`. No hay descarga falsa.
   - **Elegir POS o Tótem**: mismo asistente y misma seguridad.
5. Instalador del cliente: verifica que la CA corresponde al servidor
   indicado mediante huella/código de verificación mostrado físicamente
   en la consola administrativa. Solicita una sola autorización para
   confiar en ella. No exige elegir almacén de certificados ni ruta.
6. Se valida HTTPS y el estado del POS Server. Si falla, se explica qué
   ocurre (servidor apagado, IP cambiada, CA no reconocida, reloj del
   equipo, puerto 443 bloqueado) sin ocultar el error.
7. El Tótem exige un **código efímero de un uso** generado desde la consola
   después de vincular su IP y su QR. El POS cliente necesita un operador
   autenticado y permisos de caja. La identidad persistente sigue en SQLite
   del servidor, no en localStorage.
8. El asistente confirma conexión, caja/tótem, QR habilitado y versión de
   cliente. Permite regresar a pasos anteriores y reparar instalación.

## Contraseñas y roles

- **Clave ADMIN por comercio**, almacenada con hash PBKDF2 y salt; nunca
  contraseña universal o incluida en un ejecutable.
- POS Server exige ADMIN para cambiar IP/QR, emitir códigos temporales,
  exportar kits y copiar claves LAN. El desbloqueo local dura diez minutos.
- La contraseña ADMIN existente es necesaria para rotarla; en primera
  instalación sin usuario activo se configura desde la consola física.
- Cada **operador POS** tiene usuario y rol, sin contraseñas compartidas.
- Cada **tótem** se autoriza con código de un uso, cookie HttpOnly y
  asociación al servidor. El token no viaja en URL ni en instaladores.
- Ante pérdida de administrador, el proceso de recuperación deberá
  usar pruebas de posesión del equipo/almacén de datos y un flujo local
  auditado; **no habrá una clave de soporte estática que permita entrar a
  todos los comercios**.

## Certificados y modo portable

La CA privada del comercio permanece en POS Server. Un cliente nuevo puede
descargar **solo el certificado raíz público** y lo acepta tras confirmar la
huella mostrada en la consola del comercio. Este es el mínimo requisito
de seguridad para impedir suplantación de servidor y QR.

**Windows Tauri:** el WebView2 de Windows necesita que el sistema confíe en
la CA o que se implemente un mecanismo equivalente de verificación nativa
auditado. No se puede ofrecer un portable que muestre cualquier certificado
sin verificación. El instalador Windows podrá importar la CA al almacén
de **usuario actual** tras una aprobación explícita, sin pedirle que elija
un almacén ni una carpeta. El modo realmente portable necesitará un
mecanismo nativo de confianza/pinning probado; no está implementado.

**Acceso por navegador:** el certificado privado debe estar instalado y
confiado en el dispositivo; un sitio web no puede instalarse su propia CA
silenciosamente. Android/iPadOS tienen restricciones particulares.

**IP cambiante:** los certificados contienen IP SAN. Si cambia, regenerar
el certificado del servidor y reconectar dispositivos. Se recomienda reserva
DHCP como opción simplificadora, no configurar DNS manualmente.

## Estado real del código — noviembre 2026

**Implementado en rama de desarrollo:**
- POS Server con consola, detección LAN, asociación IP/QR, código de tótem.
- API, POS Flet y Astro sobre HTTPS local por IP mediante Caddy.
- Asistente Ubuntu/KDE que instala Caddy y prepara automáticamente el .env
  tras confirmación administrativa.
- Nuevo asistente de dispositivos desde POS Server, opciones POS/Server/Tótem.
- Servicio `services/installation_kits.py`: genera un ZIP seguro, con
  certificado **público**/huella/URL, sin contraseñas, API keys ni tokens.
- Detección local de compilaciones reales, sin enlaces de descarga
  inventados.

**No implementado todavía — bloquea distribución comercial:**
- Instalador **único Windows** que incluya los tres programas y soporte
  reparación, desinstalación y actualizaciones.
- Cliente **Tauri compilado y validado** en Windows; la estructura
  `intrashop/src-tauri` existe pero hoy no completa el aprovisionamiento
  seguro de un servidor remoto ni la instalación de su CA.
- Instalador Windows/Linux de clientes que importe CA con aprobación y
  verificación de huella sin intervención técnica.
- Firma de ejecutables, verificación de integridad de releases y
  política de actualizaciones seguras; el lector de builds local no
  prueba firma digital.
- Configuración automática de credenciales independientes por POS/rol
  en lugar de depender de una API key compartida.
- Tests físicos finales de impresora térmica, Mercado Pago real,
  cancelaciones simultáneas y WebView2.

**No mostrar botones «Descargar .exe» ni proclamar "versión portable lista"
hasta que estos puntos estén verificados.** El asistente actual es la
primera etapa operativa del flujo de distribución; no sustituye aún al
bootstrapper instalable.

## Empaquetado previsto

Publicar `IntraShop-Suite-Setup.exe` como bootstrapper principal,
con perfiles opcionales integrados:

- POS de caja: aprovechar pipeline Windows Flet que hoy produce
  `kiosmico-windows` en GitHub Actions.
- POS Server: empaquetar con PyInstaller, backend y frontend compilado
  Astro, Caddy y servicio Windows como prerequisitos administrados.
- IntraShop Tauri: construir MSIX/NSIS o MSI verificable con
  `tauri build`, configurar el servidor por un manifest local confiable
  y no habilitar IPC de Tauri a orígenes web remotos.
- Integrador: un solo wizard invoca los instaladores internos adecuados,
  reporta estado real, configura autorun y maneja reversión sin tocar
  `libreria.db`.

La distribución por releases deberá incluir firmas digitales,
SHA-256 y procedencia de CI; no se deben ejecutar binarios encontrados
arbitrariamente por la LAN.

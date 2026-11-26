# IntraShop Suite — compilaciones para el asistente local

Esta carpeta contiene únicamente documentación. El repositorio **no incluye
instaladores binarios ni una versión Windows/Tauri lista para producción**.

El panel de **POS Server → Instalar / conectar equipos** muestra ejecutables
únicamente cuando el administrador copia una compilación real en
`distribution/builds/`. No descarga binarios arbitrarios de Internet,
no crea enlaces ficticios y no ofrece ejecutables si la carpeta está vacía.

Nombres admitidos según el perfil:
- POS caja: `Kiosmico-<versión>.exe` o `POS-<versión>.msi`.
- POS Server: `IntraShopServer-<versión>.exe` / `.msi`.
- Tótem Tauri: `IntraShop-<versión>-setup.exe` / `.msi` /
  `IntraShop-<versión>-portable.zip`.

**Descubrimiento no implica verificación de seguridad.** Un archivo local
puede tener un nombre válido y ser peligroso; el asistente solo abre la
carpeta, no ejecuta ni publica el archivo. Antes de ofrecer descargas al
cliente deben existir firmas digitales, comprobación SHA-256 independiente,
control de versiones y un canal de distribución autenticado.

El ZIP de **conexión** exportado desde POS Server incluye solo:
`conexion.json`, `intrashop-root-ca.crt`, `INSTRUCCIONES.txt`, y en
perfil Tótem el acceso web `Abrir-IntraShop.url`. Nunca es un instalador
de software ni contiene secretos. Para confiar la CA, el cliente debe
comprobar la huella mostrada por la consola física del comercio.

Arquitectura y faltantes: [Distribución unificada](../docs/distribucion-unificada.md).

## Compilación automatizada

Ejecutar **IntraShop Suite distribution** desde GitHub Actions. Genera POS y POS Server portables (ZIP) y tótem Tauri (instaladores) para Windows y Linux. El artefacto final `intrashop-suite` conserva la carpeta `distribution/builds/` que reconoce el wizard. Descargar y extraer en una instalación de confianza; no mezclar archivos de diferentes versiones. El manifiesto SHA-256 registra integridad, no sustituye una firma digital. El workflow falla si falta cualquiera de los seis builds. No publica una release ni incluye bases de datos de comercios.

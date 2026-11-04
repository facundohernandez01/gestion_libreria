# IntraShop Server Manager — prototipo aislado

Rama: feature/intrashop-server-dotnet. No sustituye pos_server.py ni modifica main.py.

## Requisitos de desarrollo

Windows 10/11, .NET 10 SDK y Python con dependencias del repositorio (solo si se prueba sin backend empaquetado).

## Compilar

Desde Windows, en la raíz del repositorio:

```powershell
dotnet build .\intrashop-server\IntraShop.ServerManager\IntraShop.ServerManager.csproj -c Release
```

Ejecutar el EXE resultante. En «Ejecutable FastAPI» configurar la ruta absoluta a python.exe del entorno virtual para desarrollo, o a pos_server.exe cuando exista un backend empaquetado. Para el modo Python el directorio de trabajo debe coincidir con la raíz del repositorio; la detección automática es provisional y depende de la ubicación de salida de dotnet.

## Alcance actual

- Consultar GET /health para identificar el servidor POS.
- Iniciar pos_server.py --headless mediante Python o un ejecutable empaquetado.
- Detener solo el proceso iniciado por este panel.
- Abrir /intrashop/ en el navegador.

## Pendientes antes de distribuir

- Separar dependencias FastAPI de Flet y generar backend onedir.
- Servicio Windows con parada ordenada; el prototipo usa terminación forzada y **no es apto para producción**.
- Configuración persistente de rutas y puerto; validación de procesos concurrentes.
- Panel de tótems, QR y conciliación mediante API autenticada.
- Build reproducible, instalador y medición real de RAM/tamaño.
- Definir migraciones y copias de seguridad de SQLite.

No usar este prototipo para operar cobros reales hasta implementar cierre ordenado y pruebas de integración.


## Compilación Windows: .NET + backend

El script `build-backend.ps1` **solo** genera el motor Python. Para compilar exclusivamente la interfaz C#:

```powershell
.\intrashop-server\scripts\build-dotnet.ps1
```

Para crear la distribución combinada (administrador .NET + FastAPI empaquetado):

```powershell
.\intrashop-server\scripts\build-release.ps1
```

Salida:

```text
intrashop-server/release/
  IntraShop.ServerManager.exe
  backend/
    pos_server.exe
    _internal/
```

El administrador detecta el backend en esa ubicación de manera predeterminada. La publicación .NET es `win-x64`, autocontenida y de archivo único; no necesita el runtime .NET instalado por separado. El backend continúa siendo Python y se distribuye junto al administrador, sin instalar Python. **Esto no genera todavía un Setup.exe**: la carpeta release es una distribución portable para pruebas. No utilizar con cobros reales hasta completar parada ordenada y validación de integridad.

Para repetir la publicación .NET usando un backend Python ya empaquetado:

```powershell
.\intrashop-server\scripts\build-release.ps1 -SkipBackend
```

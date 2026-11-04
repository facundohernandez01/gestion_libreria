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

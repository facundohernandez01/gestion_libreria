# Desacople progresivo del servidor IntraShop

Rama de trabajo: `feature/mercadopago-oauth`. No depende de .NET.

## Primera etapa (opt-in, compatible con instalaciones existentes)

El backend FastAPI ya puede ejecutarse independientemente de Flet:

```bash
python pos_server.py --headless --host 0.0.0.0 --port 8000
```

La consola Tkinter original mantiene las secciones Tótems, Asignaciones QR,
Operadores POS y Conciliación:

```bash
python pos_server.py
```

Para evitar que el POS inicie una segunda instancia de FastAPI, configurar
`POS_EXTERNAL_SERVER=1` **antes de lanzar** `main.py`. Por ejemplo:

```bash
POS_EXTERNAL_SERVER=1 python main.py
```

Este indicador únicamente desactiva el inicio automático desde la interfaz
POS. No cambia por sí solo el modo de acceso a datos. En el mismo equipo,
el modo `servidor` continúa usando SQLite local; los puestos remotos deben
usar `MODO_RED=cliente` con `SERVER_URL` apuntando al servidor.

**Precaución:** POS y backend deben compartir la misma base real. No ejecutar
dos servidores contra bases distintas ni mover archivos de SQLite con
procesos abiertos. La transición al servicio externo todavía requiere
validar paridad funcional de `ApiClient` y las operaciones de stock/caja.

## Pendientes

1. Administrador Tkinter en bandeja del sistema, instancia única y parada ordenada.
2. Proceso servidor independiente de la ventana administradora y detección de
   instancias existentes; política explícita para salir sin detener servicio.
3. Persistencia de datos, secretos OAuth y respaldos fuera de la carpeta de instalación.
4. Completar y probar métodos HTTP faltantes del modo cliente.
5. Empaquetado del servidor sin Flet, instalador conjunto y pruebas Windows.

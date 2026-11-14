# Operación manual: POS Server, backups y comprobación IntraShop

Esta guía se aplica a la edición IntraShop distribuida (POS cliente HTTP + POS Server propietario de SQLite + tótem). **Ejecutar la restauración exclusivamente en la PC servidor**. Elegir un backup en Ajustes > Backup del POS cliente muestra una vista previa, **NO importa ningún registro**.

## 0. Preparación (sin alterar la base)

En la máquina donde corre POS Server, abrir una terminal y ejecutar:

```bash
cd ~/Escritorio/gestion_libreria
git status --short
source .venv/bin/activate
python -c 'from core.settings import settings; print("BASE REAL:", settings.db_path)'
```

Si el entorno virtual tiene otro nombre, adaptar la ruta. Confirmar que la ruta impresa pertenece a POS Server y no a otra copia local. No ejecutar `git reset --hard`, `git clean` ni cambiar de rama con cambios locales sin guardarlos.

Para verificar el servidor si ya está iniciado:

```bash
curl -fsS http://127.0.0.1:8000/health
```

Nunca poner la API key, token Bearer ni Access Token en la URL o en un comando que quede en el historial.

## 1. Hacer una copia válida de los datos actuales

Con POS Server funcionando, ingresar al POS con sesión de administrador y abrir **Ajustes > Backup > EXPORTAR BACKUP**. Guardar el archivo fuera del directorio de instalación, por ejemplo en un disco externo. El cliente pide al servidor una copia consistente y la descarga. Verificar que el archivo exista y no tenga tamaño cero.

En **ELEGIR BACKUP** se validan integridad y conteos, pero **no hay importación automática**: es solo vista previa. No confundir un número de productos mostrado con productos efectivamente restaurados.

## 2. Decidir el modo de restauración

| Modo | Uso | Qué sucede |
| --- | --- | --- |
| `reemplazar` | Recuperar exactamente el estado guardado | Reemplaza el contenido operativo del servidor; las ventas y cambios posteriores al backup no se conservan en esa base |
| `fusionar` | Incorporar registros faltantes desde otra base | Agrega productos con códigos nuevos y ciertos registros no duplicados; **no modifica stock, precios ni descripción de productos existentes**, ni sustituye configuración actual |

Para el caso «veo productos en el backup pero no aparecen en el sistema», comprobar primero si falta aplicar la restauración o si se está usando `fusionar` con productos cuyos códigos ya existen. **No usar `reemplazar` sin revisar qué datos nuevos se perderían.**

## 3. Detener POS Server y confirmar que la SQLite no esté abierta

Cerrar la GUI de POS Server, el servidor arrancado desde terminal o detener el servicio, según cómo esté instalado:

```bash
systemctl --user stop intrashop-pos.service
```

El comando anterior solo aplica si se creó ese servicio. Si POS Server se abrió manualmente, detenerlo desde la terminal o GUI correspondiente. Confirmar que no exista **otra instancia** del servidor utilizando la base.

```bash
ss -ltnp | grep ':8000' || true
```

Una línea escuchando en el puerto 8000 indica que todavía hay un proceso a revisar. Que no haya escucha en el puerto **no garantiza** que SQLite esté cerrada; el script de restauración también inspecciona procesos. Detener los tótems y cajas para no generar operaciones durante la recuperación.

## 4. Simulación (obligatoria) y restauración real

En la máquina servidor, ubicarse en el repositorio y preparar las rutas:

```bash
cd ~/Escritorio/gestion_libreria
source .venv/bin/activate
DB_REAL="$(python -c 'from core.settings import settings; print(settings.db_path)')"
BACKUP="$HOME/Descargas/mi_backup.db"
test -f "$DB_REAL" && test -f "$BACKUP"
python -m pip install psutil
```

**Sustituir `mi_backup.db` por el nombre real**, sin mover ni renombrar la base activa.

Primero simular, sin cambios:

```bash
python tools/restaurar_backup_servidor.py "$BACKUP" --db "$DB_REAL" --modo reemplazar
```

Revisar cuidadosamente `BACKUP`, `DESTINO`, `VALIDACIÓN` y `ACTUAL`. Si el objetivo es una fusión, usar `--modo fusionar` en ambos comandos.

Solo si el destino, la copia y el modo son correctos, ejecutar:

```bash
python tools/restaurar_backup_servidor.py "$BACKUP" --db "$DB_REAL" --modo reemplazar --aplicar
```

Escribir `DETENIDO` si lo solicita y `RESTAURAR` para confirmar. La herramienta comprueba procesos abiertos, crea un **backup de seguridad de la base anterior**, aplica la operación y muestra conteos posteriores. Guardar la ruta del backup de seguridad que informa. Si aparece cualquier error, no reintentar repetidamente ni arrancar simultáneamente dos servidores; conservar copias y revisar la causa.

## 5. Reiniciar y comprobar

Si el servidor se gestiona por `systemd`:

```bash
systemctl --user start intrashop-pos.service
systemctl --user status intrashop-pos.service --no-pager
```

Si se ejecuta manualmente, iniciar **solo una instancia**:

```bash
python pos_server.py --headless --host 0.0.0.0 --port 8000
```

En otra terminal:

```bash
curl -fsS http://127.0.0.1:8000/health
```

Luego abrir el POS cliente y verificar artículos por código, stock, proveedores, órdenes de compra, historial de cajas y ventas (sin operaciones ficticias en producción). Comprobar que POS Server muestra la base real; si el POS parece vacío, investigar URL de conexión y ruta de SQLite antes de repetir la importación.

## 6. Pruebas manuales del circuito, con datos de prueba

1. **Red:** POS conecta por HTTP a la IP LAN del servidor y muestra estado saludable; no abre una SQLite propia.
2. **Catálogo:** crear o editar artículo desde POS, marcar disponible en tienda; comprobar aparición en el tótem y persistencia tras reinicio.
3. **Compras:** alta de proveedor, orden de reposición, recepción parcial y final; revisar stock y movimientos una sola vez.
4. **Venta y entrega:** usar una caja de prueba, confirmar un pago simulado, verificar venta, descuento único de stock y comanda; confirmar entrega en un solo POS.
5. **QR:** cancelar la operación antes de pagar, verificar el cierre efectivo de la orden remota y ausencia de venta; también probar reinicio y pérdida de conexión. **No asumir que cerrar el modal equivale a cancelar en Mercado Pago**.
6. **Backup:** exportar, validar y ensayar restauración en una **base descartable separada** antes de recuperar la de producción. Comparar conteos y artículos reales.

Mantener `INTRASHOP_MP_ORDERS_V1=0` hasta validar credenciales, asociación de POS/tótems, firma de webhook y pagos reales en entorno controlado. La API Orders v1 es opt-in, no una migración automática. Ver [guía Orders v1](mercadopago-orders-v1-migracion-segura.md).

## 7. Pruebas de regresión sin afectar la base productiva

```bash
python -m pytest -q tests/test_api_client_parity.py \
  tests/test_backup_roundtrip.py \
  tests/test_backup_validation.py \
  tests/test_backup_client_export.py \
  tests/test_backup_streaming.py
```

Estos tests crean bases temporales o usan HTTP simulado. **No apuntar tests experimentales a `DB_PATH` de producción.**

## Alcance y pendientes

La importación remota directa desde el POS está bloqueada intencionalmente para evitar sustituir la SQLite mientras FastAPI la usa. Para ofrecer restauración remota segura en el futuro hacen falta mantenimiento coordinado, detención del servicio, rollback comprobado, reinicio y autorización administrativa; una simple carga de archivo HTTP no alcanza.

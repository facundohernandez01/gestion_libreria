# Runbook de verificación — POS Server, POS cliente, IntraShop/Tauri

Esta rama contiene PR #3 + #4 + #5 y la corrección de Tauri del PR #6.
Todas las operaciones de pruebas automatizadas utilizan SQLite temporal; no
subir, copiar ni borrar la `libreria.db` productiva.

## 1. Actualizar el clon sin tocar datos operativos

```bash
cd ~/Escritorio/intrashop-multicaja
git branch --show-current
git status --short
git pull --ff-only origin feat/pos-server-multicaja-terminal-20261118
```

Verificar la rama antes de tirar del remoto. No usar `git reset --hard`,
`git clean -fd`, ni iniciar simultáneamente dos servidores contra la misma DB.

## 2. Probar el backend sin POS Server activo

```bash
python -m pytest -q \
  tests/test_pos_multicaja_terminal.py \
  tests/test_pos_client_server_url.py \
  tests/test_pos_server_devices_snapshot.py \
  tests/test_intrashop_caja_link.py
python -m compileall -q api_client.py componente_login.py pos_auth.py core/
```

Probar con la misma `.venv` que usa el POS.

## 3. Iniciar POS Server y confirmar conectividad

Cerrar las instancias previas de `pos_server.py` para evitar probar
contra código antiguo en el puerto 8000. En la primera terminal:

```bash
python pos_server.py
```

En otra terminal (dejar el servidor funcionando):

```bash
curl -fsS http://127.0.0.1:8000/health
python -c "from core.settings import settings; print(settings.db_path)"
```

El servidor debe responder su health y mostrar la base correcta.
La GUI de POS Server tiene que listar dispositivos o mostrar **0 tótems** sin
quedar en «Cargando dispositivos…».

## 4. Login POS cliente y caja por terminal

```bash
python main.py
```

Ingresar las credenciales reales configuradas para esta base de prueba.
El flujo esperado en el log HTTP es:

- **POST /pos/auth/login → 200** una sola vez por intento.
- **GET /cajas/abierta → 200**, con caja propia o `null`; **nunca 403**.
- Si no hay caja abierta, abrirla desde esta terminal.
- Crear una venta de prueba, registrar un gasto de prueba, consultar historial
  y comprobar que los importes y `caja_id` sean correctos.
- Iniciar sesión desde un segundo POS **en otra computadora** y repetir.
  Ambos deben compartir stock pero no caja.

Si el equipo que ejecuta `main.py` es otro, abrir **Configurar conexión LAN
de esta terminal** en la pantalla de login, escribir
`http://IP-REAL-DEL-SERVIDOR:8000`, guardar y reiniciar el POS.
La preferencia se guarda en la carpeta local `~/.config/intrashop/`
(Linux) o en `%LOCALAPPDATA%\\intrashop\\` (Windows); no en `libreria.db`.
La API key no se envía como parámetro de URL.

## 5. IntraShop en modo Tauri (desarrollo y empaquetado)

```bash
cd ~/Escritorio/intrashop-multicaja/intrashop
npm install
npm run tauri dev
```

Debe abrir la portada del catálogo en la raíz de la aplicación, no
mostrar el aviso de Astro «base path /intrashop/».
Comprobar navegación a **Administración de tienda** y **Comandas**.

Ingresar la IP real de POS Server en Administración de tienda, guardar el
nombre del tótem, y comprobar que se registre en el panel POS Server.
La URL del servidor se almacena en el dispositivo; no incrustar tokens
ni claves de Mercado Pago en Astro/Tauri.

## 6. Verificar ambos builds sin sobrescribir archivos

```bash
cd ~/Escritorio/intrashop-multicaja/intrashop
npm run build:tauri
node scripts/check-build.mjs tauri
npm run build
node scripts/check-build.mjs server
```

- `dist-tauri/` es exclusivo para el empaquetado Tauri (rutas `/`).
- `dist/` queda publicado por POS Server en `/intrashop/`.
- Ambos deben coexistir sin borrarse ni cambiar de base.
- La configuración `src-tauri/tauri.conf.json` apunta a
  `../dist-tauri`; `npm run tauri build` compila el desktop automáticamente.

## 7. Pago, stock y comandas

En una **base de pruebas** y con el POS Server actualizado:

1. Abrir dos cajas de terminales distintas, desde dos equipos POS.
2. Registrar al menos un tótem en IntraShop y asignar su POS Mercado Pago
   y su `caja_id` en Ajustes. Con varias cajas abiertas la asignación
   explícita es obligatoria.
3. Probar carrito, stock, QR, cancelación y comprobación del cierre del QR;
   no liberar una reserva de pago incierto sin confirmación del proveedor.
4. Confirmar un pago de prueba y verificar una sola venta, descuento único
   de stock, `caja_id` correcto y comanda pendiente de entrega.
5. Tomar, preparar y entregar la comanda desde un operador autorizado.
   Intentar tomarla simultáneamente desde otro POS: no debe duplicarse.
6. Comprobar que cerrar la caja A no cierre la caja B ni desvíe sus ventas.

No introducir pagos reales hasta validar las cancelaciones del proveedor
y la conciliación de forma independiente.

## Cambios de rama

El PR #6 es un parche independiente contra `feature/mercadopago-oauth`.
Para probar ese parche sin cambiar la rama original en otro clon, ejecutar:

```bash
git fetch origin
git switch --track origin/fix/intrashop-tauri-dual-base-20261118
```

No están fusionados los PR #3, #4, #5 o #6. La rama multicaja sí incluye
las correcciones necesarias para probar en el clon actual.

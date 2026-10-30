# IntraShop — múltiples tótems y asignación de cajas

## Modelo implementado

- Cada navegador de tótem mantiene un UUID estable en `localStorage.intrashop_totem_id`.
- El administrador define el nombre en `/admin`; el dispositivo se registra en `POST /tienda/totems/register`.
- `POST /tienda/checkout` envía el UUID y la venta pagada guarda el identificador y el nombre del tótem en `intrashop_entregas`.
- El servidor almacena todos los pedidos, sin aplicar filtros por caja.
- `GET /tienda/admin/entregas/totems` devuelve el registro central a un operador autenticado con permiso de entregas.
- Cada caja guarda su filtro `INTRASHOP_TOTEMS_FILTRO` en la configuración SQLite **local**. Una lista vacía significa todos, incluso nuevos tótems.
- El panel Flet muestra el origen y filtra las comandas visualmente. La confirmación sigue ejecutándose en el servidor y se valida por sesión.
- Los pedidos anteriores sin `totem_id` se conservan y se muestran únicamente al seleccionar Todos.

## Operación

1. En cada tótem, abrir `/admin`, definir nombre (por ejemplo «Entrada 1») y guardar. Verificar confirmación de registro.
2. En cada caja POS, iniciar sesión con un rol que tenga `ENTREGAS_INTRASHOP`; para configurar filtros, también `CONFIGURACION`.
3. Abrir Comandas IntraShop y elegir «Todos los tótems» o marcar los dispositivos deseados.
4. Guardar selección. Al volver a abrir el POS, se recupera el filtro local.
5. Una comanda entregada se actualiza centralmente para todas las cajas, independientemente de los filtros.

## Limitaciones actuales

- La asignación es **filtro operativo**, no restricción de seguridad: un usuario con sesión de entregas válida puede consultar la API central sin filtro. No usar para separar sucursales o datos confidenciales.
- El registro de tótems utiliza la API key de instalación; falta aprovisionamiento individual con credenciales de dispositivo y prevención de suplantación.
- El identificador se guarda por perfil de navegador. Borrar datos locales o cambiar de navegador genera un nuevo UUID; el registro anterior permanece.
- La API de Mercado Pago sigue serializando checkouts activos en un único servidor; varios tótems pueden navegar, pero no cobrar simultáneamente. Hace falta rediseñar la concurrencia, la persistencia de jobs y las reservas de stock para múltiples cobros.
- Las pruebas se añadieron al repositorio, pero no se ejecutaron en terminales reales.

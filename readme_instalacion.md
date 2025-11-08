# Sistema de Gestión para Librería/Kiosko

Sistema de punto de venta (POS) para gestión de ventas, stock y caja para librerías y kioskos.

## 📋 Características

- **Gestión de Caja**: Apertura y cierre de caja con control de efectivo
- **Ventas**: Registro de ventas con búsqueda por código de barras o descripción
- **Stock**: Control automático de inventario con alertas de stock bajo
- **Productos**: Gestión completa de artículos con precios y categorías
- **Reportes**: Visualización de ventas del día y movimientos de caja
- **Import/Export**: Importación y exportación de productos en Excel

## 🔧 Instalación

### Requisitos previos

- Python 3.8 o superior
- pip (gestor de paquetes de Python)

### Instalación de dependencias

```bash
# Crear entorno virtual (recomendado)
python -m venv venv

# Activar entorno virtual
# En Windows:
venv\Scripts\activate
# En Linux/Mac:
source venv/bin/activate

# Instalar dependencias
pip install flet
pip install pandas
pip install openpyxl
```

## 📁 Estructura del proyecto

```
libreria-pos/
│
├── main.py                          # Archivo principal
├── database_manager.py              # Gestor de base de datos
├── libreria.db                      # Base de datos SQLite (se crea automáticamente)
│
├── componente_abrir_caja.py         # Componente de apertura de caja
├── componente_ventana_principal.py  # Ventana principal
├── componente_nueva_venta.py        # Modal de nueva venta
├── componente_gestion_articulos.py  # Gestión de productos
├── componente_producto.py           # Modal de producto
├── componente_cerrar_caja.py        # Modal de cierre de caja
├── componente_gestion_stock.py      # Gestión de stock
│
└── README.md                        # Este archivo
```

## 🚀 Uso

### Ejecutar la aplicación

```bash
python main.py
```

### Flujo de trabajo

1. **Abrir Caja**: Al iniciar, se debe abrir la caja ingresando el monto inicial
2. **Registrar Ventas**: 
   - Usar el botón del teclado para buscar por descripción
   - Usar el botón del lector de barras para buscar por código
3. **Gestionar Stock**: Verificar alertas de stock bajo y realizar ajustes
4. **Cerrar Caja**: Al final del día, cerrar caja con registro de gastos

## 📊 Funcionalidades principales

### Apertura de Caja
- Registro de fecha y hora automática
- Ingreso de monto inicial
- Observaciones opcionales

### Ventas
- Búsqueda rápida por código o descripción
- Soporte para lector de códigos de barras
- Carrito de compras con ajuste de cantidades
- Verificación automática de stock
- Generación de tickets (configurable)

### Gestión de Productos
- CRUD completo de productos
- Cálculo automático de márgenes de ganancia
- Importación masiva desde Excel
- Exportación de catálogo a Excel
- Control de stock mínimo

### Control de Stock
- Alertas visuales de stock bajo/crítico
- Ajuste manual de inventario
- Historial de movimientos
- Actualización automática en ventas

### Cierre de Caja
- Cálculo automático de totales
- Registro de gastos del día
- Resumen de ventas y movimientos
- Observaciones de cierre

## 📝 Formato de Excel para importación

El archivo Excel debe contener las siguientes columnas:

| codigo | descripcion | categoria | marca | precio_lista | precio_costo | stock_inicial | stock_minimo |
|--------|-------------|-----------|-------|--------------|--------------|---------------|--------------|
| 7790001001234 | Cuaderno 84 hojas | Libreria | Rivadavia | 1500.00 | 900.00 | 50 | 10 |

**Columnas obligatorias**: codigo, descripcion, precio_lista

**Columnas opcionales**: categoria, marca, precio_costo, stock_inicial, stock_minimo

## 🔌 Configuración de lector de códigos de barras

El sistema está diseñado para trabajar con lectores de códigos de barras USB que emulan teclado. 

**Configuración recomendada**:
- El lector debe estar configurado para enviar ENTER después del código
- No requiere configuración adicional en el software

## 💾 Base de datos

El sistema utiliza SQLite para almacenar:
- Productos
- Cajas (aperturas y cierres)
- Ventas y sus items
- Gastos
- Movimientos de stock

La base de datos se crea automáticamente en el primer uso con datos de prueba.

## 🎨 Personalización

### Temas y colores
El sistema usa Flet con tema oscuro por defecto. Para cambiar:

```python
# En main.py
self.page.theme_mode = ft.ThemeMode.LIGHT  # Tema claro
```

### Impresión de tickets
La función de impresión está preparada para usar:
- **Windows**: win32print
- **Linux**: CUPS
- Impresoras térmicas compatibles con ESC/POS

## 🐛 Solución de problemas

### La aplicación no inicia
- Verificar que todas las dependencias estén instaladas
- Comprobar la versión de Python (debe ser 3.8+)

### Error al importar Excel
- Verificar que el archivo tenga las columnas requeridas
- Asegurarse de que los datos sean del tipo correcto

### Stock no se actualiza
- Verificar que la venta se haya confirmado correctamente
- Revisar la tabla de movimientos_stock en la base de datos

## 📞 Soporte

Para reportar problemas o sugerir mejoras, crear un issue en el repositorio del proyecto.

## 📄 Licencia

Este proyecto es de código abierto y está disponible bajo la licencia MIT.

---

**Versión**: 1.0.0  
**Última actualización**: Noviembre 2024
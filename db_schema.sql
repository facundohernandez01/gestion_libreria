-- Esquema de referencia (la app usa el SCHEMA embebido en database_manager.py).
-- Se mantiene sincronizado sólo como documentación.
CREATE TABLE IF NOT EXISTS proveedores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT UNIQUE NOT NULL,
    cuit TEXT DEFAULT '',
    telefono TEXT DEFAULT '',
    email TEXT DEFAULT '',
    direccion TEXT DEFAULT '',
    notas TEXT DEFAULT '',
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fecha_modificacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS proveedor_contactos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proveedor_id INTEGER NOT NULL,
    nombre TEXT NOT NULL,
    telefono TEXT DEFAULT '',
    email TEXT DEFAULT '',
    FOREIGN KEY (proveedor_id) REFERENCES proveedores(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS productos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT UNIQUE NOT NULL,
    descripcion TEXT NOT NULL,
    categoria TEXT DEFAULT '',
    marca TEXT DEFAULT '',
    precio_lista REAL NOT NULL CHECK(precio_lista >= 0),
    precio_costo REAL DEFAULT 0 CHECK(precio_costo >= 0),
    stock_inicial INTEGER DEFAULT 0,
    stock_actual INTEGER DEFAULT 0,
    stock_minimo INTEGER DEFAULT 5,
    proveedor_id INTEGER REFERENCES proveedores(id),
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fecha_modificacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clave TEXT UNIQUE NOT NULL,
    valor TEXT
);
CREATE TABLE IF NOT EXISTS cajas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_apertura TIMESTAMP NOT NULL,
    fecha_cierre TIMESTAMP,
    importe_apertura REAL NOT NULL,
    importe_cierre REAL,
    total_ventas REAL DEFAULT 0,
    total_gastos REAL DEFAULT 0,
    observaciones_apertura TEXT DEFAULT '',
    observaciones_cierre TEXT DEFAULT '',
    estado TEXT DEFAULT 'abierta' CHECK(estado IN ('abierta', 'cerrada'))
);
CREATE TABLE IF NOT EXISTS ventas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    caja_id INTEGER NOT NULL,
    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    total REAL NOT NULL,
    estado TEXT DEFAULT 'completada' CHECK(estado IN ('completada', 'cancelada')),
    metodo_pago TEXT DEFAULT 'efectivo',
    comprobante TEXT DEFAULT '',
    numero_factura TEXT,
    cae TEXT,
    vencimiento_cae TEXT,
    FOREIGN KEY (caja_id) REFERENCES cajas(id)
);
CREATE TABLE IF NOT EXISTS venta_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    venta_id INTEGER NOT NULL,
    producto_id INTEGER NOT NULL,
    cantidad INTEGER NOT NULL CHECK(cantidad > 0),
    precio_unitario REAL NOT NULL,
    subtotal REAL NOT NULL,
    FOREIGN KEY (venta_id) REFERENCES ventas(id),
    FOREIGN KEY (producto_id) REFERENCES productos(id)
);
CREATE TABLE IF NOT EXISTS gastos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    caja_id INTEGER NOT NULL,
    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    monto REAL NOT NULL CHECK(monto > 0),
    concepto TEXT NOT NULL,
    FOREIGN KEY (caja_id) REFERENCES cajas(id)
);
CREATE TABLE IF NOT EXISTS movimientos_stock (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    producto_id INTEGER NOT NULL,
    tipo TEXT NOT NULL CHECK(tipo IN ('venta', 'ajuste', 'devolucion', 'ingreso')),
    cantidad INTEGER NOT NULL,
    stock_anterior INTEGER NOT NULL,
    stock_nuevo INTEGER NOT NULL,
    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    referencia_id INTEGER,
    observaciones TEXT DEFAULT '',
    FOREIGN KEY (producto_id) REFERENCES productos(id)
);
CREATE TABLE IF NOT EXISTS ordenes_compra (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fecha_modificacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fecha_confirmacion TIMESTAMP,
    estado TEXT NOT NULL DEFAULT 'en_proceso'
        CHECK(estado IN ('en_proceso', 'confirmada', 'cancelada')),
    observaciones TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS orden_compra_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    orden_id INTEGER NOT NULL,
    producto_id INTEGER NOT NULL,
    proveedor_id INTEGER,
    cantidad INTEGER NOT NULL CHECK(cantidad > 0),
    precio_costo REAL DEFAULT 0 CHECK(precio_costo >= 0),
    subtotal REAL DEFAULT 0,
    FOREIGN KEY (orden_id) REFERENCES ordenes_compra(id) ON DELETE CASCADE,
    FOREIGN KEY (producto_id) REFERENCES productos(id),
    FOREIGN KEY (proveedor_id) REFERENCES proveedores(id)
);
CREATE INDEX IF NOT EXISTS idx_productos_codigo ON productos(codigo);
CREATE INDEX IF NOT EXISTS idx_proveedores_nombre ON proveedores(nombre);
CREATE INDEX IF NOT EXISTS idx_contactos_proveedor ON proveedor_contactos(proveedor_id);
CREATE INDEX IF NOT EXISTS idx_ordenes_estado ON ordenes_compra(estado);
CREATE INDEX IF NOT EXISTS idx_orden_items_orden ON orden_compra_items(orden_id);
CREATE INDEX IF NOT EXISTS idx_orden_items_producto ON orden_compra_items(producto_id);
CREATE INDEX IF NOT EXISTS idx_productos_descripcion ON productos(descripcion);
CREATE INDEX IF NOT EXISTS idx_ventas_caja ON ventas(caja_id);
CREATE INDEX IF NOT EXISTS idx_ventas_fecha ON ventas(fecha);
CREATE INDEX IF NOT EXISTS idx_venta_items_venta ON venta_items(venta_id);
CREATE INDEX IF NOT EXISTS idx_movimientos_producto ON movimientos_stock(producto_id);

-- Datos de prueba
INSERT INTO productos (codigo, descripcion, categoria, marca, precio_lista, precio_costo, stock_inicial, stock_actual, stock_minimo) VALUES
('7790001001234', 'Cuaderno Rivadavia 84 hojas', 'Libreria', 'Rivadavia', 1500.00, 900.00, 50, 50, 10),
('7790001001235', 'Lapicera BIC Cristal Azul', 'Libreria', 'BIC', 350.00, 200.00, 100, 100, 20),
('7790001001236', 'Resma A4 Author 75g', 'Libreria', 'Author', 4500.00, 3200.00, 30, 30, 5),
('7790001001237', 'Goma de borrar Faber Castell', 'Libreria', 'Faber Castell', 280.00, 150.00, 80, 80, 15),
('7790001001238', 'Regla 30cm Maped', 'Libreria', 'Maped', 420.00, 250.00, 60, 60, 10),
('7790001001239', 'Coca Cola 500ml', 'Bebidas', 'Coca Cola', 800.00, 500.00, 100, 100, 20),
('7790001001240', 'Galletitas Oreo 118g', 'Golosinas', 'Oreo', 950.00, 650.00, 80, 80, 15),
('7790001001241', 'Chocolate Milka 100g', 'Golosinas', 'Milka', 1200.00, 850.00, 60, 60, 12),
('7790001001242', 'Agua Mineral Villavicencio 500ml', 'Bebidas', 'Villavicencio', 450.00, 280.00, 120, 120, 25),
('7790001001243', 'Caramelos Menthoplus', 'Golosinas', 'Menthoplus', 180.00, 100.00, 150, 150, 30),
('7790001001244', 'Corrector Liquid Paper', 'Libreria', 'Liquid Paper', 650.00, 400.00, 40, 40, 8),
('7790001001245', 'Block de dibujo A4', 'Libreria', 'El Nene', 890.00, 550.00, 35, 35, 7),
('7790001001246', 'Marcadores Faber x12', 'Libreria', 'Faber Castell', 3200.00, 2100.00, 25, 25, 5),
('7790001001247', 'Alfajor Jorgito Simple', 'Golosinas', 'Jorgito', 550.00, 350.00, 90, 90, 20),
('7790001001248', 'Jugo Baggio 1L Naranja', 'Bebidas', 'Baggio', 980.00, 650.00, 50, 50, 10);

-- Abrir una caja de prueba
INSERT INTO cajas (fecha_apertura, importe_apertura, observaciones_apertura, estado) 
VALUES (datetime('now'), 5000.00, 'Apertura de prueba', 'abierta');
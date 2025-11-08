-- Tabla de productos
CREATE TABLE productos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT UNIQUE NOT NULL,
    descripcion TEXT NOT NULL,
    categoria TEXT,
    marca TEXT,
    precio_lista REAL NOT NULL,
    precio_costo REAL,
    stock_inicial INTEGER DEFAULT 0,
    stock_actual INTEGER DEFAULT 0,
    stock_minimo INTEGER DEFAULT 5,
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fecha_modificacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabla de cajas
CREATE TABLE cajas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_apertura TIMESTAMP NOT NULL,
    fecha_cierre TIMESTAMP,
    importe_apertura REAL NOT NULL,
    importe_cierre REAL,
    total_ventas REAL DEFAULT 0,
    total_gastos REAL DEFAULT 0,
    observaciones_apertura TEXT,
    observaciones_cierre TEXT,
    estado TEXT DEFAULT 'abierta' CHECK(estado IN ('abierta', 'cerrada'))
);

-- Tabla de ventas
CREATE TABLE ventas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    caja_id INTEGER NOT NULL,
    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    total REAL NOT NULL,
    estado TEXT DEFAULT 'completada' CHECK(estado IN ('completada', 'cancelada')),
    FOREIGN KEY (caja_id) REFERENCES cajas(id)
);

-- Tabla de items de venta
CREATE TABLE venta_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    venta_id INTEGER NOT NULL,
    producto_id INTEGER NOT NULL,
    cantidad INTEGER NOT NULL,
    precio_unitario REAL NOT NULL,
    subtotal REAL NOT NULL,
    FOREIGN KEY (venta_id) REFERENCES ventas(id),
    FOREIGN KEY (producto_id) REFERENCES productos(id)
);

-- Tabla de gastos
CREATE TABLE gastos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    caja_id INTEGER NOT NULL,
    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    monto REAL NOT NULL,
    concepto TEXT NOT NULL,
    FOREIGN KEY (caja_id) REFERENCES cajas(id)
);

-- Tabla de movimientos de stock
CREATE TABLE movimientos_stock (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    producto_id INTEGER NOT NULL,
    tipo TEXT NOT NULL CHECK(tipo IN ('venta', 'ajuste', 'devolucion')),
    cantidad INTEGER NOT NULL,
    stock_anterior INTEGER NOT NULL,
    stock_nuevo INTEGER NOT NULL,
    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    referencia_id INTEGER,
    observaciones TEXT,
    FOREIGN KEY (producto_id) REFERENCES productos(id)
);

-- Índices para mejorar rendimiento
CREATE INDEX idx_productos_codigo ON productos(codigo);
CREATE INDEX idx_productos_descripcion ON productos(descripcion);
CREATE INDEX idx_ventas_caja ON ventas(caja_id);
CREATE INDEX idx_ventas_fecha ON ventas(fecha);
CREATE INDEX idx_venta_items_venta ON venta_items(venta_id);
CREATE INDEX idx_venta_items_producto ON venta_items(producto_id);
CREATE INDEX idx_movimientos_producto ON movimientos_stock(producto_id);

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
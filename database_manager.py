"""
database_manager.py
Gestor de base de datos para el sistema de librería/kiosko
"""

import sqlite3
from datetime import datetime
from typing import List, Optional, Tuple
import os
import flet as ft
from flet import Icons

class DatabaseManager:
    def __init__(self, db_path: str = "libreria.db"):
        self.db_path = db_path
        self.init_database()
    
    def get_connection(self):
        """Obtiene una conexión a la base de datos"""
        return sqlite3.connect(self.db_path)
    
    def init_database(self):
        """Inicializa la base de datos si no existe"""
        if not os.path.exists(self.db_path):
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.executescript("""
                CREATE TABLE IF NOT EXISTS productos (
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
                    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
                    observaciones_apertura TEXT,
                    observaciones_cierre TEXT,
                    estado TEXT DEFAULT 'abierta'
                );
                
                CREATE TABLE IF NOT EXISTS ventas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    caja_id INTEGER NOT NULL,
                    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    total REAL NOT NULL,
                    estado TEXT DEFAULT 'completada',
                    FOREIGN KEY (caja_id) REFERENCES cajas(id)
                );
                
                CREATE TABLE IF NOT EXISTS venta_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    venta_id INTEGER NOT NULL,
                    producto_id INTEGER NOT NULL,
                    cantidad INTEGER NOT NULL,
                    precio_unitario REAL NOT NULL,
                    subtotal REAL NOT NULL,
                    FOREIGN KEY (venta_id) REFERENCES ventas(id),
                    FOREIGN KEY (producto_id) REFERENCES productos(id)
                );
                
                CREATE TABLE IF NOT EXISTS gastos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    caja_id INTEGER NOT NULL,
                    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    monto REAL NOT NULL,
                    concepto TEXT NOT NULL,
                    FOREIGN KEY (caja_id) REFERENCES cajas(id)
                );
                
                CREATE TABLE IF NOT EXISTS movimientos_stock (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    producto_id INTEGER NOT NULL,
                    tipo TEXT NOT NULL,
                    cantidad INTEGER NOT NULL,
                    stock_anterior INTEGER NOT NULL,
                    stock_nuevo INTEGER NOT NULL,
                    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    referencia_id INTEGER,
                    observaciones TEXT,
                    FOREIGN KEY (producto_id) REFERENCIAS productos(id)
                );
            """)
            
            conn.commit()
            conn.close()
    
    # ==================== PRODUCTOS ====================
    
    def buscar_productos(self, termino: str, campo: str = "descripcion") -> List[dict]:
        """Busca productos por código o descripción"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        if campo == "codigo":
            query = "SELECT * FROM productos WHERE codigo LIKE ? ORDER BY descripcion"
        elif campo == "categoria":
            query = "SELECT * FROM productos WHERE categoria LIKE ? ORDER BY descripcion"
        else:
            query = "SELECT * FROM productos WHERE descripcion LIKE ? ORDER BY descripcion"
        
        cursor.execute(query, (f"%{termino}%",))
        columns = [desc[0] for desc in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        conn.close()
        return results
    
    def obtener_producto(self, producto_id: int) -> Optional[dict]:
        """Obtiene un producto por ID"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM productos WHERE id = ?", (producto_id,))
        row = cursor.fetchone()
        
        if row:
            columns = [desc[0] for desc in cursor.description]
            result = dict(zip(columns, row))
        else:
            result = None
        
        conn.close()
        return result
    
    def obtener_producto_por_codigo(self, codigo: str) -> Optional[dict]:
        """Obtiene un producto por código de barras"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM productos WHERE codigo = ?", (codigo,))
        row = cursor.fetchone()
        
        if row:
            columns = [desc[0] for desc in cursor.description]
            result = dict(zip(columns, row))
        else:
            result = None
        
        conn.close()
        return result
    
    def guardar_producto(self, producto: dict) -> int:
        """Guarda o actualiza un producto (verifica si ya existe por código)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Verificar si existe un producto con el mismo código
            cursor.execute("SELECT id FROM productos WHERE codigo = ?", (producto['codigo'],))
            existente = cursor.fetchone()
            
            if existente:
                # Si existe, actualizamos ese registro
                producto_id = existente[0]
                cursor.execute("""
                    UPDATE productos 
                    SET descripcion=?, categoria=?, marca=?, 
                        precio_lista=?, precio_costo=?, stock_actual=?, stock_minimo=?
                    WHERE id=?
                """, (
                    producto['descripcion'],
                    producto.get('categoria', ''),
                    producto.get('marca', ''),
                    producto['precio_lista'],
                    producto.get('precio_costo', 0),
                    producto.get('stock_actual', 0),
                    producto.get('stock_minimo', 5),
                    producto_id
                ))
            elif producto.get('id'):
                # Si viene con ID (por formulario), también actualizamos
                cursor.execute("""
                    UPDATE productos 
                    SET codigo=?, descripcion=?, categoria=?, marca=?, 
                        precio_lista=?, precio_costo=?, stock_actual=?, stock_minimo=?
                    WHERE id=?
                """, (
                    producto['codigo'],
                    producto['descripcion'],
                    producto.get('categoria', ''),
                    producto.get('marca', ''),
                    producto['precio_lista'],
                    producto.get('precio_costo', 0),
                    producto['stock_actual'],
                    producto.get('stock_minimo', 5),
                    producto['id']
                ))
                producto_id = producto['id']
            else:
                # Si no existe, insertamos uno nuevo
                cursor.execute("""
                    INSERT INTO productos 
                    (codigo, descripcion, categoria, marca, precio_lista, precio_costo, 
                    stock_inicial, stock_actual, stock_minimo)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    producto['codigo'],
                    producto['descripcion'],
                    producto.get('categoria', ''),
                    producto.get('marca', ''),
                    producto['precio_lista'],
                    producto.get('precio_costo', 0),
                    producto.get('stock_inicial', 0),
                    producto.get('stock_inicial', 0),
                    producto.get('stock_minimo', 5)
                ))
                producto_id = cursor.lastrowid
            
            conn.commit()
            return producto_id
        except Exception as e:
            conn.rollback()
            print(f"Error guardando producto: {e}")
            return 0
        finally:
            conn.close()

    
    def actualizar_stock(self, producto_id: int, cantidad: int, tipo: str, 
                        referencia_id: Optional[int] = None, observaciones: str = "") -> bool:
        """Actualiza el stock de un producto y registra el movimiento"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Obtener stock actual
            cursor.execute("SELECT stock_actual FROM productos WHERE id = ?", (producto_id,))
            result = cursor.fetchone()
            if not result:
                return False
            
            stock_actual = result[0]
            
            # Calcular nuevo stock
            if tipo == "venta":
                nuevo_stock = stock_actual - cantidad
            else:  # ajuste, devolucion
                nuevo_stock = stock_actual + cantidad
            
            if nuevo_stock < 0:
                print(f"Error: Stock negativo para producto {producto_id}")
                return False
            
            # Actualizar stock del producto
            cursor.execute("UPDATE productos SET stock_actual = ? WHERE id = ?", 
                          (nuevo_stock, producto_id))
            
            # Registrar movimiento
            cursor.execute("""
                INSERT INTO movimientos_stock 
                (producto_id, tipo, cantidad, stock_anterior, stock_nuevo, referencia_id, observaciones)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (producto_id, tipo, cantidad, stock_actual, nuevo_stock, referencia_id, observaciones))
            
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            print(f"Error actualizando stock: {e}")
            return False
        finally:
            conn.close()
    
    # ==================== CAJAS ====================
    
    def obtener_caja_abierta(self) -> Optional[dict]:
        """Obtiene la caja actualmente abierta"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM cajas WHERE estado = 'abierta' ORDER BY fecha_apertura DESC LIMIT 1")
        row = cursor.fetchone()
        
        if row:
            columns = [desc[0] for desc in cursor.description]
            result = dict(zip(columns, row))
        else:
            result = None
        
        conn.close()
        return result
    
    def abrir_caja(self, importe_apertura: float, observaciones: str = "") -> int:
        """Abre una nueva caja"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO cajas (fecha_apertura, importe_apertura, observaciones_apertura, estado)
                VALUES (?, ?, ?, 'abierta')
            """, (datetime.now(), importe_apertura, observaciones))
            
            caja_id = cursor.lastrowid
            conn.commit()
            return caja_id
        except Exception as e:
            conn.rollback()
            print(f"Error abriendo caja: {e}")
            return 0
        finally:
            conn.close()
    
    def cerrar_caja(self, caja_id: int, observaciones: str = "") -> bool:
        """Cierra una caja y calcula los totales"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Calcular totales
            cursor.execute("SELECT SUM(total) FROM ventas WHERE caja_id = ? AND estado = 'completada'", (caja_id,))
            total_ventas = cursor.fetchone()[0] or 0
            
            cursor.execute("SELECT SUM(monto) FROM gastos WHERE caja_id = ?", (caja_id,))
            total_gastos = cursor.fetchone()[0] or 0
            
            cursor.execute("SELECT importe_apertura FROM cajas WHERE id = ?", (caja_id,))
            importe_apertura = cursor.fetchone()[0]
            
            importe_cierre = importe_apertura + total_ventas - total_gastos
            
            # Cerrar caja
            cursor.execute("""
                UPDATE cajas 
                SET fecha_cierre = ?, importe_cierre = ?, total_ventas = ?, 
                    total_gastos = ?, observaciones_cierre = ?, estado = 'cerrada'
                WHERE id = ?
            """, (datetime.now(), importe_cierre, total_ventas, total_gastos, observaciones, caja_id))
            
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            print(f"Error cerrando caja: {e}")
            return False
        finally:
            conn.close()
    
    # ==================== VENTAS ====================
    
    def obtener_ventas_del_dia(self, caja_id: int) -> List[dict]:
        """Obtiene todas las ventas de la caja actual"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT v.*, COUNT(vi.id) as items_count
            FROM ventas v
            LEFT JOIN venta_items vi ON v.id = vi.venta_id
            WHERE v.caja_id = ? AND v.estado = 'completada'
            GROUP BY v.id
            ORDER BY v.fecha DESC
        """, (caja_id,))
        
        columns = [desc[0] for desc in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        conn.close()
        return results
    
    def obtener_items_venta(self, venta_id: int) -> List[dict]:
        """Obtiene los items de una venta específica"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT vi.*, p.descripcion as producto_nombre
            FROM venta_items vi
            JOIN productos p ON vi.producto_id = p.id
            WHERE vi.venta_id = ?
        """, (venta_id,))
        
        columns = [desc[0] for desc in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        conn.close()
        return results
    
    def crear_venta(self, caja_id: int, items: List[dict]) -> Tuple[int, bool]:
        """Crea una nueva venta con sus items"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Calcular total
            total = sum(item['precio_unitario'] * item['cantidad'] for item in items)
            
            # Crear venta
            cursor.execute("""
                INSERT INTO ventas (caja_id, fecha, total, estado)
                VALUES (?, ?, ?, 'completada')
            """, (caja_id, datetime.now(), total))
            
            venta_id = cursor.lastrowid
            
            # Agregar items y actualizar stock
            for item in items:
                subtotal = item['precio_unitario'] * item['cantidad']
                
                cursor.execute("""
                    INSERT INTO venta_items (venta_id, producto_id, cantidad, precio_unitario, subtotal)
                    VALUES (?, ?, ?, ?, ?)
                """, (venta_id, item['producto_id'], item['cantidad'], item['precio_unitario'], subtotal))
            
            conn.commit()
            
            # Actualizar stock (fuera de la transacción principal para mejor manejo de errores)
            for item in items:
                self.actualizar_stock(item['producto_id'], item['cantidad'], 
                                    "venta", venta_id, f"Venta #{venta_id}")
            
            return venta_id, True
        except Exception as e:
            conn.rollback()
            print(f"Error creando venta: {e}")
            return 0, False
        finally:
            conn.close()
    
    def set_config(self, clave: str, valor: str):
        """Guarda o actualiza un valor de configuración"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO config (clave, valor)
                VALUES (?, ?)
                ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor
            """, (clave, valor))
            conn.commit()
        except Exception as e:
            print(f"Error guardando configuración: {e}")
        finally:
            conn.close()

    def get_config(self, clave: str) -> Optional[str]:
        """Obtiene un valor de configuración"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT valor FROM config WHERE clave = ?", (clave,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None

    def get_all_config(self) -> dict:
        """Devuelve todas las configuraciones en un diccionario"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT clave, valor FROM config")
        result = dict(cursor.fetchall())
        conn.close()
        return result
    
    def get_config_value(self, clave):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT valor FROM config WHERE clave = ?", (clave,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None

    # ==================== GASTOS ====================
    
    def agregar_gasto(self, caja_id: int, monto: float, concepto: str) -> int:
        """Registra un gasto en la caja"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO gastos (caja_id, monto, concepto, fecha)
                VALUES (?, ?, ?, ?)
            """, (caja_id, monto, concepto, datetime.now()))
            
            gasto_id = cursor.lastrowid
            conn.commit()
            return gasto_id
        except Exception as e:
            conn.rollback()
            print(f"Error agregando gasto: {e}")
            return 0
        finally:
            conn.close()
    
    def obtener_gastos_caja(self, caja_id: int) -> List[dict]:
        """Obtiene todos los gastos de una caja"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM gastos WHERE caja_id = ? ORDER BY fecha DESC", (caja_id,))
        columns = [desc[0] for desc in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        conn.close()
        return results
    
    # ==================== REPORTES Y UTILIDADES ====================
    
    def obtener_productos_bajo_stock(self) -> List[dict]:
        """Obtiene productos con stock bajo o crítico"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM productos 
            WHERE stock_actual <= stock_minimo 
            ORDER BY stock_actual ASC
        """)
        
        columns = [desc[0] for desc in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        conn.close()
        return results
    
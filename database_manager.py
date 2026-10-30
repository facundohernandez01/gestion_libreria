"""Gestor de base de datos SQLite — capa Repository.

Buenas prácticas aplicadas:
- Conexiones por context-manager + row_factory (dicts sin zip manual).
- init idempotente (CREATE TABLE IF NOT EXISTS siempre, no solo si falta el .db).
- Transacción atómica en crear_venta (venta + items + stock + movimientos).
- Sin imports de UI (antes importaba flet sin usar).
- Validación de campo de búsqueda para evitar SQL injection por nombre de columna.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

logger = logging.getLogger(__name__)

SCHEMA = """
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
CREATE TABLE IF NOT EXISTS roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT UNIQUE NOT NULL COLLATE NOCASE,
    descripcion TEXT DEFAULT '',
    permisos TEXT NOT NULL DEFAULT '{}',
    es_admin INTEGER NOT NULL DEFAULT 0,
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fecha_modificacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario TEXT UNIQUE NOT NULL COLLATE NOCASE,
    clave TEXT NOT NULL,
    nombre TEXT DEFAULT '',
    rol_id INTEGER,
    activo INTEGER NOT NULL DEFAULT 1,
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fecha_modificacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (rol_id) REFERENCES roles(id) ON DELETE SET NULL
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
    usuario_apertura TEXT DEFAULT '',
    usuario_cierre TEXT DEFAULT '',
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
    usuario TEXT DEFAULT '',
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
    usuario TEXT DEFAULT '',
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
    usuario TEXT DEFAULT '',
    FOREIGN KEY (producto_id) REFERENCES productos(id)
);
CREATE TABLE IF NOT EXISTS ordenes_compra (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fecha_modificacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fecha_confirmacion TIMESTAMP,
    estado TEXT NOT NULL DEFAULT 'en_proceso'
        CHECK(estado IN ('en_proceso', 'parcial', 'confirmada', 'cancelada')),
    observaciones TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS orden_compra_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    orden_id INTEGER NOT NULL,
    producto_id INTEGER NOT NULL,
    proveedor_id INTEGER,
    cantidad INTEGER NOT NULL CHECK(cantidad > 0),
    cantidad_recibida INTEGER NOT NULL DEFAULT 0,
    precio_costo REAL DEFAULT 0 CHECK(precio_costo >= 0),
    subtotal REAL DEFAULT 0,
    FOREIGN KEY (orden_id) REFERENCES ordenes_compra(id) ON DELETE CASCADE,
    FOREIGN KEY (producto_id) REFERENCES productos(id),
    FOREIGN KEY (proveedor_id) REFERENCES proveedores(id)
);
CREATE TABLE IF NOT EXISTS orden_compra_recepciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    orden_id INTEGER NOT NULL,
    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    remito TEXT DEFAULT '',
    observaciones TEXT DEFAULT '',
    cancelo_restante INTEGER NOT NULL DEFAULT 0,
    usuario TEXT DEFAULT '',
    FOREIGN KEY (orden_id) REFERENCES ordenes_compra(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS orden_compra_recepcion_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recepcion_id INTEGER NOT NULL,
    item_id INTEGER NOT NULL,
    producto_id INTEGER NOT NULL,
    cantidad INTEGER NOT NULL CHECK(cantidad > 0),
    FOREIGN KEY (recepcion_id) REFERENCES orden_compra_recepciones(id) ON DELETE CASCADE,
    FOREIGN KEY (item_id) REFERENCES orden_compra_items(id) ON DELETE CASCADE,
    FOREIGN KEY (producto_id) REFERENCES productos(id)
);
CREATE INDEX IF NOT EXISTS idx_productos_codigo ON productos(codigo);
CREATE INDEX IF NOT EXISTS idx_proveedores_nombre ON proveedores(nombre);
CREATE INDEX IF NOT EXISTS idx_contactos_proveedor ON proveedor_contactos(proveedor_id);
CREATE INDEX IF NOT EXISTS idx_ordenes_estado ON ordenes_compra(estado);
CREATE INDEX IF NOT EXISTS idx_orden_items_orden ON orden_compra_items(orden_id);
CREATE INDEX IF NOT EXISTS idx_orden_items_producto ON orden_compra_items(producto_id);
CREATE INDEX IF NOT EXISTS idx_recepciones_orden ON orden_compra_recepciones(orden_id);
CREATE INDEX IF NOT EXISTS idx_recepcion_items_item ON orden_compra_recepcion_items(item_id);
CREATE INDEX IF NOT EXISTS idx_productos_descripcion ON productos(descripcion);
CREATE INDEX IF NOT EXISTS idx_ventas_caja ON ventas(caja_id);
CREATE INDEX IF NOT EXISTS idx_ventas_fecha ON ventas(fecha);
CREATE INDEX IF NOT EXISTS idx_venta_items_venta ON venta_items(venta_id);
 CREATE INDEX IF NOT EXISTS idx_movimientos_producto ON movimientos_stock(producto_id);
 """

_MOVIMIENTOS_SQL = re.search(
    r"CREATE TABLE IF NOT EXISTS movimientos_stock \(.*?\n\);", SCHEMA, re.S
).group(0)

_ORDENES_SQL = re.search(
    r"CREATE TABLE IF NOT EXISTS ordenes_compra \(.*?\n\);", SCHEMA, re.S
).group(0)


CAMPOS_BUSQUEDA_VALIDOS = {"descripcion", "codigo", "categoria"}


class DatabaseManager:
    """Repository único de persistencia (patrón Repository + Singleton ligero)."""

    def __init__(self, db_path: str | None = None):
        if db_path is None:
            try:
                from core.settings import settings  # import tardío, evita ciclo

                db_path = settings.db_path
            except Exception:
                db_path = os.getenv("DB_PATH", "libreria.db")
        self.db_path = db_path
        self.usuario_actual = (os.getenv("USUARIO_ACTUAL", "") or "").strip()
        # Asegurar carpeta padre
        parent = Path(self.db_path).parent
        if str(parent) not in ("", "."):
            parent.mkdir(parents=True, exist_ok=True)
        self.init_database()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            yield conn
            # commit lo hace cada método explícitamente
        finally:
            conn.close()

    def get_connection(self) -> sqlite3.Connection:
        """Compatibilidad: devuelve conexión con Row factory (cerrar manualmente)."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    # ---------- schema ----------
    def init_database(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            # Migraciones livianas: columnas que pueden faltar en DBs viejas
            for ddl in (
                "ALTER TABLE ventas ADD COLUMN metodo_pago TEXT DEFAULT 'efectivo'",
                "ALTER TABLE ventas ADD COLUMN comprobante TEXT DEFAULT ''",
                "ALTER TABLE ventas ADD COLUMN numero_factura TEXT",
                "ALTER TABLE ventas ADD COLUMN cae TEXT",
                "ALTER TABLE ventas ADD COLUMN vencimiento_cae TEXT",
                "ALTER TABLE productos ADD COLUMN fecha_modificacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
                "ALTER TABLE productos ADD COLUMN proveedor_id INTEGER",
                "ALTER TABLE ordenes_compra ADD COLUMN fecha_confirmacion TIMESTAMP",
                "ALTER TABLE ordenes_compra ADD COLUMN fecha_modificacion TIMESTAMP",
                "ALTER TABLE orden_compra_items ADD COLUMN cantidad_recibida INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE cajas ADD COLUMN usuario_apertura TEXT DEFAULT ''",
                "ALTER TABLE cajas ADD COLUMN usuario_cierre TEXT DEFAULT ''",
                "ALTER TABLE ventas ADD COLUMN usuario TEXT DEFAULT ''",
                "ALTER TABLE gastos ADD COLUMN usuario TEXT DEFAULT ''",
                "ALTER TABLE movimientos_stock ADD COLUMN usuario TEXT DEFAULT ''",
                "ALTER TABLE ordenes_compra ADD COLUMN usuario TEXT DEFAULT ''",
                "ALTER TABLE orden_compra_recepciones ADD COLUMN usuario TEXT DEFAULT ''",
            ):
                try:
                    conn.execute(ddl)
                except sqlite3.OperationalError as e:
                    if "duplicate column" not in str(e).lower():
                        logger.debug("migración omitida: %s", e)
            self._migrar_movimientos_stock(conn)
            self._migrar_ordenes_compra(conn)
            self._sembrar_roles_usuarios(conn)
            # Órdenes ya confirmadas antes de existir «cantidad_recibida»:
            # se consideran recibidas por completo.
            conn.execute(
                """UPDATE orden_compra_items SET cantidad_recibida = cantidad
                   WHERE cantidad_recibida = 0 AND orden_id IN
                         (SELECT id FROM ordenes_compra WHERE estado='confirmada')""")
            conn.commit()

    def _migrar_movimientos_stock(self, conn) -> None:
        """Agrega 'ingreso' al CHECK de tipo si la tabla es de una versión vieja.

        SQLite no permite ALTER de un CHECK: se reconstruye la tabla.
        """
        row = conn.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type='table' AND name='movimientos_stock'"
        ).fetchone()
        if not row or "'ingreso'" in (row[0] or ""):
            return
        logger.info("migrando movimientos_stock: agregando 'ingreso' al CHECK de tipo")
        conn.execute("PRAGMA foreign_keys=OFF")
        try:
            conn.execute("BEGIN")
            conn.execute(_MOVIMIENTOS_SQL.replace(
                "IF NOT EXISTS movimientos_stock", "movimientos_stock_mig"))
            conn.execute(
                """INSERT INTO movimientos_stock_mig
                   (id, producto_id, tipo, cantidad, stock_anterior, stock_nuevo,
                    fecha, referencia_id, observaciones)
                   SELECT id, producto_id, tipo, cantidad, stock_anterior,
                          stock_nuevo, fecha, referencia_id, observaciones
                   FROM movimientos_stock""")
            conn.execute("DROP TABLE movimientos_stock")
            conn.execute(
                "ALTER TABLE movimientos_stock_mig RENAME TO movimientos_stock")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_movimientos_producto "
                "ON movimientos_stock(producto_id)")
            conn.commit()
        except Exception:  # noqa: BLE001
            conn.rollback()
            logger.error("migración de movimientos_stock fallida")
        finally:
            conn.execute("PRAGMA foreign_keys=ON")

    def _migrar_ordenes_compra(self, conn) -> None:
        """Agrega el estado 'parcial' al CHECK de ordenes_compra (DBs viejas).

        SQLite no permite ALTER de un CHECK: se reconstruye la tabla.
        """
        row = conn.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type='table' AND name='ordenes_compra'"
        ).fetchone()
        if not row or "'parcial'" in (row[0] or ""):
            return
        logger.info("migrando ordenes_compra: agregando estado 'parcial'")
        conn.execute("PRAGMA foreign_keys=OFF")
        try:
            conn.execute("BEGIN")
            conn.execute(_ORDENES_SQL.replace(
                "IF NOT EXISTS ordenes_compra", "ordenes_compra_mig"))
            conn.execute(
                """INSERT INTO ordenes_compra_mig
                   (id, fecha_creacion, fecha_modificacion, fecha_confirmacion,
                    estado, observaciones)
                   SELECT id, fecha_creacion, fecha_modificacion,
                          fecha_confirmacion, estado, observaciones
                   FROM ordenes_compra""")
            conn.execute("DROP TABLE ordenes_compra")
            conn.execute(
                "ALTER TABLE ordenes_compra_mig RENAME TO ordenes_compra")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_ordenes_estado "
                "ON ordenes_compra(estado)")
            conn.commit()
        except Exception:  # noqa: BLE001
            conn.rollback()
            logger.error("migración de ordenes_compra fallida")
        finally:
            conn.execute("PRAGMA foreign_keys=ON")

    def set_usuario_actual(self, usuario: str) -> None:
        self.usuario_actual = (usuario or "").strip()

    def _usuario(self) -> str:
        return (self.usuario_actual or "sistema").strip()[:80]

    # ---------- roles / usuarios ----------
    def _sembrar_roles_usuarios(self, conn) -> None:
        """Crea los roles base (ADMIN/CAJA) y el usuario admin inicial."""
        from core.permisos import (normalizar, permisos_caja,
                                   permisos_todos)

        base = (
            ("ADMIN", "Acceso total al sistema", permisos_todos(), 1),
            ("CAJA", "Caja, ventas, artículos y stock", permisos_caja(), 0),
        )
        for nombre, descripcion, permisos, es_admin in base:
            row = conn.execute(
                "SELECT id, es_admin FROM roles WHERE nombre=? COLLATE NOCASE",
                (nombre,),
            ).fetchone()
            if row:
                if es_admin and not row["es_admin"]:
                    conn.execute(
                        "UPDATE roles SET es_admin=1, permisos=? WHERE id=?",
                        (json.dumps(normalizar(permisos_todos())), row["id"]),
                    )
                continue
            conn.execute(
                """INSERT INTO roles (nombre, descripcion, permisos, es_admin)
                   VALUES (?, ?, ?, ?)""",
                (nombre, descripcion,
                 json.dumps(normalizar(permisos)), es_admin),
            )

        admin_rol = conn.execute(
            "SELECT id FROM roles WHERE es_admin=1 ORDER BY id LIMIT 1"
        ).fetchone()
        total = conn.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]
        if not total:
            fila_user = conn.execute(
                "SELECT valor FROM config WHERE clave='LOGIN_USUARIO'"
            ).fetchone()
            fila_clave = conn.execute(
                "SELECT valor FROM config WHERE clave='LOGIN_CLAVE'"
            ).fetchone()
            usuario = ((fila_user["valor"] if fila_user else "") or "admin").strip()
            clave = ((fila_clave["valor"] if fila_clave else "") or "admin").strip()
            conn.execute(
                """INSERT INTO usuarios (usuario, clave, nombre, rol_id, activo)
                   VALUES (?, ?, ?, ?, 1)""",
                (usuario, clave, "Administrador",
                 admin_rol["id"] if admin_rol else None),
            )
        conn.commit()

    @staticmethod
    def _rol_dict(fila) -> dict:
        from core.permisos import normalizar

        data = dict(fila)
        data["es_admin"] = bool(data.get("es_admin"))
        data["permisos"] = normalizar(data.get("permisos"))
        if data["es_admin"]:
            from core.permisos import permisos_todos

            data["permisos"] = permisos_todos()
        return data

    def listar_roles(self) -> List[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT r.*,
                          (SELECT COUNT(*) FROM usuarios u
                           WHERE u.rol_id=r.id) AS usuarios_count
                   FROM roles r
                   ORDER BY r.es_admin DESC, r.nombre COLLATE NOCASE"""
            ).fetchall()
            return [self._rol_dict(r) for r in rows]

    def obtener_rol(self, rol_id: int) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM roles WHERE id=?", (rol_id,)).fetchone()
            return self._rol_dict(row) if row else None

    def guardar_rol(self, datos: dict) -> Tuple[int, str]:
        from core.permisos import normalizar

        nombre = str(datos.get("nombre", "") or "").strip()
        descripcion = str(datos.get("descripcion", "") or "").strip()
        if not nombre:
            return 0, "Ingresá un nombre para el rol"
        permisos = normalizar(datos.get("permisos"))
        try:
            rol_id = int(datos.get("id") or 0)
        except (TypeError, ValueError):
            rol_id = 0
        with self._connect() as conn:
            try:
                if rol_id:
                    actual = conn.execute(
                        "SELECT es_admin FROM roles WHERE id=?", (rol_id,)
                    ).fetchone()
                    if not actual:
                        return 0, "El rol no existe"
                    if actual["es_admin"]:
                        conn.execute(
                            """UPDATE roles SET descripcion=?,
                               fecha_modificacion=CURRENT_TIMESTAMP WHERE id=?""",
                            (descripcion, rol_id),
                        )
                    else:
                        conn.execute(
                            """UPDATE roles SET nombre=?, descripcion=?,
                               permisos=?, fecha_modificacion=CURRENT_TIMESTAMP
                               WHERE id=?""",
                            (nombre, descripcion, json.dumps(permisos), rol_id),
                        )
                    conn.commit()
                    return rol_id, ""
                cur = conn.execute(
                    """INSERT INTO roles (nombre, descripcion, permisos, es_admin)
                       VALUES (?, ?, ?, 0)""",
                    (nombre, descripcion, json.dumps(permisos)),
                )
                conn.commit()
                return int(cur.lastrowid), ""
            except sqlite3.IntegrityError:
                conn.rollback()
                return 0, "Ya existe un rol con ese nombre"
            except Exception as e:  # noqa: BLE001
                conn.rollback()
                logger.error("guardar_rol: %s", e)
                return 0, str(e)

    def eliminar_rol(self, rol_id: int) -> Tuple[bool, str]:
        with self._connect() as conn:
            try:
                row = conn.execute(
                    "SELECT es_admin FROM roles WHERE id=?", (rol_id,)
                ).fetchone()
                if not row:
                    return False, "El rol no existe"
                if row["es_admin"]:
                    return False, "El rol ADMIN no se puede eliminar"
                usados = conn.execute(
                    "SELECT COUNT(*) FROM usuarios WHERE rol_id=?", (rol_id,)
                ).fetchone()[0]
                if usados:
                    return False, (f"El rol está asignado a {usados} usuario(s). "
                                   "Cambiales el rol antes de eliminarlo.")
                conn.execute("DELETE FROM roles WHERE id=?", (rol_id,))
                conn.commit()
                return True, ""
            except Exception as e:  # noqa: BLE001
                conn.rollback()
                logger.error("eliminar_rol: %s", e)
                return False, str(e)

    @staticmethod
    def _usuario_dict(fila) -> dict:
        from core.permisos import normalizar, permisos_todos

        data = dict(fila)
        data["activo"] = bool(data.get("activo"))
        data["es_admin"] = bool(data.get("rol_es_admin"))
        data["permisos"] = (permisos_todos() if data["es_admin"]
                            else normalizar(data.get("rol_permisos") or "{}"))
        data["rol"] = data.get("rol_nombre") or ""
        return data

    def listar_usuarios(self) -> List[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT u.*, r.nombre AS rol_nombre,
                          r.es_admin AS rol_es_admin, r.permisos AS rol_permisos
                   FROM usuarios u
                   LEFT JOIN roles r ON r.id = u.rol_id
                   ORDER BY u.activo DESC, u.usuario COLLATE NOCASE"""
            ).fetchall()
            return [self._usuario_dict(r) for r in rows]

    def obtener_usuario(self, usuario_id: int) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT u.*, r.nombre AS rol_nombre,
                          r.es_admin AS rol_es_admin, r.permisos AS rol_permisos
                   FROM usuarios u LEFT JOIN roles r ON r.id = u.rol_id
                   WHERE u.id=?""",
                (usuario_id,),
            ).fetchone()
            return self._usuario_dict(row) if row else None

    def _admins_activos(self, conn, excluir_id: int = 0) -> int:
        row = conn.execute(
            """SELECT COUNT(*) FROM usuarios u
               JOIN roles r ON r.id = u.rol_id
               WHERE r.es_admin=1 AND u.activo=1 AND u.id != ?""",
            (int(excluir_id or 0),),
        ).fetchone()
        return int(row[0] or 0)

    def guardar_usuario(self, datos: dict) -> Tuple[int, str]:
        usuario = str(datos.get("usuario", "") or "").strip()
        clave = str(datos.get("clave", "") or "").strip()
        nombre = str(datos.get("nombre", "") or "").strip()
        activo = 1 if datos.get("activo", True) else 0
        try:
            usuario_id = int(datos.get("id") or 0)
            rol_id = int(datos.get("rol_id") or 0)
        except (TypeError, ValueError):
            return 0, "Datos inválidos"
        if not usuario:
            return 0, "Ingresá un nombre de usuario"
        if not rol_id:
            return 0, "Elegí un rol"
        with self._connect() as conn:
            try:
                rol = conn.execute(
                    "SELECT id, es_admin FROM roles WHERE id=?", (rol_id,)
                ).fetchone()
                if not rol:
                    return 0, "El rol elegido no existe"
                if usuario_id:
                    actual = conn.execute(
                        """SELECT u.*, r.es_admin AS rol_es_admin
                           FROM usuarios u LEFT JOIN roles r ON r.id=u.rol_id
                           WHERE u.id=?""",
                        (usuario_id,),
                    ).fetchone()
                    if not actual:
                        return 0, "El usuario no existe"
                    pierde_admin = (actual["rol_es_admin"] and actual["activo"]
                                    and (not rol["es_admin"] or not activo))
                    if pierde_admin and self._admins_activos(conn, usuario_id) == 0:
                        return 0, "Debe quedar al menos un usuario ADMIN activo"
                    if clave:
                        conn.execute(
                            """UPDATE usuarios SET usuario=?, clave=?, nombre=?,
                               rol_id=?, activo=?,
                               fecha_modificacion=CURRENT_TIMESTAMP WHERE id=?""",
                            (usuario, clave, nombre or usuario, rol_id, activo,
                             usuario_id),
                        )
                    else:
                        conn.execute(
                            """UPDATE usuarios SET usuario=?, nombre=?, rol_id=?,
                               activo=?, fecha_modificacion=CURRENT_TIMESTAMP
                               WHERE id=?""",
                            (usuario, nombre or usuario, rol_id, activo,
                             usuario_id),
                        )
                    conn.commit()
                    return usuario_id, ""
                if not clave:
                    return 0, "Ingresá una clave para el nuevo usuario"
                cur = conn.execute(
                    """INSERT INTO usuarios (usuario, clave, nombre, rol_id, activo)
                       VALUES (?, ?, ?, ?, ?)""",
                    (usuario, clave, nombre or usuario, rol_id, activo),
                )
                conn.commit()
                return int(cur.lastrowid), ""
            except sqlite3.IntegrityError:
                conn.rollback()
                return 0, "Ya existe un usuario con ese nombre"
            except Exception as e:  # noqa: BLE001
                conn.rollback()
                logger.error("guardar_usuario: %s", e)
                return 0, str(e)

    def eliminar_usuario(self, usuario_id: int) -> Tuple[bool, str]:
        with self._connect() as conn:
            try:
                row = conn.execute(
                    """SELECT u.id, u.activo, r.es_admin
                       FROM usuarios u LEFT JOIN roles r ON r.id=u.rol_id
                       WHERE u.id=?""",
                    (usuario_id,),
                ).fetchone()
                if not row:
                    return False, "El usuario no existe"
                if (row["es_admin"] and row["activo"]
                        and self._admins_activos(conn, usuario_id) == 0):
                    return False, "No se puede eliminar el último ADMIN activo"
                conn.execute("DELETE FROM usuarios WHERE id=?", (usuario_id,))
                conn.commit()
                return True, ""
            except Exception as e:  # noqa: BLE001
                conn.rollback()
                logger.error("eliminar_usuario: %s", e)
                return False, str(e)

    def autenticar_usuario(self, usuario: str, clave: str) -> Optional[dict]:
        usuario = (usuario or "").strip()
        clave = (clave or "").strip()
        if not usuario:
            return None
        with self._connect() as conn:
            row = conn.execute(
                """SELECT u.*, r.nombre AS rol_nombre,
                          r.es_admin AS rol_es_admin, r.permisos AS rol_permisos
                   FROM usuarios u LEFT JOIN roles r ON r.id=u.rol_id
                   WHERE u.usuario=? COLLATE NOCASE""",
                (usuario,),
            ).fetchone()
            if row:
                if not row["activo"] or str(row["clave"] or "") != clave:
                    return None
                return self._usuario_dict(row)
            # Compatibilidad con la clave única de versiones anteriores.
            cfg_user = (self.get_config_value("LOGIN_USUARIO") or "admin").strip()
            cfg_clave = (self.get_config_value("LOGIN_CLAVE") or "admin").strip()
            if usuario == cfg_user and clave == cfg_clave:
                admin = conn.execute(
                    """SELECT u.*, r.nombre AS rol_nombre,
                              r.es_admin AS rol_es_admin, r.permisos AS rol_permisos
                       FROM usuarios u JOIN roles r ON r.id=u.rol_id
                       WHERE r.es_admin=1 ORDER BY u.id LIMIT 1"""
                ).fetchone()
                if admin:
                    return self._usuario_dict(admin)
                from core.permisos import permisos_todos

                return {"id": 0, "usuario": cfg_user, "nombre": "Administrador",
                        "rol": "ADMIN", "rol_id": 0, "es_admin": True,
                        "activo": True, "permisos": permisos_todos()}
        return None

    # ---------- productos ----------
    def buscar_productos(self, termino: str = "", campo: str = "descripcion", limit: int = 200) -> List[dict]:
        campo = campo if campo in CAMPOS_BUSQUEDA_VALIDOS else "descripcion"
        with self._connect() as conn:
            cur = conn.execute(
                f"""SELECT p.*, pr.nombre AS proveedor_nombre
                    FROM productos p
                    LEFT JOIN proveedores pr ON pr.id = p.proveedor_id
                    WHERE p.{campo} LIKE ?
                    ORDER BY p.descripcion LIMIT ?""",
                (f"%{termino or ''}%", limit),
            )
            return [dict(r) for r in cur.fetchall()]

    def obtener_producto(self, producto_id: int) -> Optional[dict]:
        with self._connect() as conn:
            cur = conn.execute(
                """SELECT p.*, pr.nombre AS proveedor_nombre
                   FROM productos p
                   LEFT JOIN proveedores pr ON pr.id = p.proveedor_id
                   WHERE p.id = ?""",
                (producto_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def obtener_producto_por_codigo(self, codigo: str) -> Optional[dict]:
        with self._connect() as conn:
            cur = conn.execute(
                """SELECT p.*, pr.nombre AS proveedor_nombre
                   FROM productos p
                   LEFT JOIN proveedores pr ON pr.id = p.proveedor_id
                   WHERE p.codigo = ?""",
                (codigo.strip(),),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def guardar_producto(self, producto: dict) -> int:
        """Inserta o actualiza por `codigo`. Valida obligatorios. Retorna id o 0."""
        codigo = str(producto.get("codigo", "")).strip()
        descripcion = str(producto.get("descripcion", "")).strip()
        try:
            precio_lista = float(producto.get("precio_lista", 0))
        except (TypeError, ValueError):
            logger.warning("precio_lista inválido: %r", producto.get("precio_lista"))
            return 0
        if not codigo or not descripcion or precio_lista < 0:
            logger.warning("producto inválido (codigo/descripcion/precio): %r", producto)
            return 0
        try:
            precio_costo = float(producto.get("precio_costo") or 0)
            stock_minimo = int(producto.get("stock_minimo", 5) or 5)
        except (TypeError, ValueError):
            return 0
        proveedor_enviado = "proveedor_id" in producto
        try:
            proveedor_id = int(producto.get("proveedor_id"))
        except (TypeError, ValueError):
            proveedor_id = None

        with self._connect() as conn:
            try:
                if proveedor_id is not None:
                    if not conn.execute("SELECT 1 FROM proveedores WHERE id=?", (proveedor_id,)).fetchone():
                        proveedor_id = None
                cur = conn.execute("SELECT id, stock_actual, proveedor_id FROM productos WHERE codigo = ?", (codigo,))
                existente = cur.fetchone()
                if existente:
                    pid = existente["id"]
                    # Si es edición con stock_actual explícito se respeta; si no, se conserva.
                    if "stock_actual" in producto and producto["stock_actual"] not in (None, ""):
                        stock_actual = int(producto["stock_actual"])
                    else:
                        stock_actual = existente["stock_actual"]
                    if not proveedor_enviado:
                        proveedor_id = existente["proveedor_id"]
                    conn.execute(
                        """UPDATE productos SET descripcion=?, categoria=?, marca=?,
                           precio_lista=?, precio_costo=?, stock_actual=?, stock_minimo=?,
                           proveedor_id=?, fecha_modificacion=CURRENT_TIMESTAMP WHERE id=?""",
                        (
                            descripcion,
                            str(producto.get("categoria", "") or ""),
                            str(producto.get("marca", "") or ""),
                            precio_lista,
                            precio_costo,
                            stock_actual,
                            stock_minimo,
                            proveedor_id,
                            pid,
                        ),
                    )
                    anterior = int(existente["stock_actual"] or 0)
                    if stock_actual != anterior:
                        conn.execute(
                            """INSERT INTO movimientos_stock
                               (producto_id, tipo, cantidad, stock_anterior, stock_nuevo,
                                observaciones, usuario)
                               VALUES (?, 'ajuste', ?, ?, ?, ?, ?)""",
                            (pid, abs(stock_actual - anterior), anterior, stock_actual,
                             "Ajuste manual desde edición de producto",
                             self._usuario()),
                        )
                    conn.commit()
                    return pid
                # Alta nueva
                try:
                    stock_ini = int(producto.get("stock_inicial", producto.get("stock_actual", 0)) or 0)
                except (TypeError, ValueError):
                    stock_ini = 0
                cur = conn.execute(
                    """INSERT INTO productos
                       (codigo, descripcion, categoria, marca, precio_lista, precio_costo,
                        stock_inicial, stock_actual, stock_minimo, proveedor_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        codigo,
                        descripcion,
                        str(producto.get("categoria", "") or ""),
                        str(producto.get("marca", "") or ""),
                        precio_lista,
                        precio_costo,
                        stock_ini,
                        stock_ini,
                        stock_minimo,
                        proveedor_id,
                    ),
                )
                pid = int(cur.lastrowid)
                if stock_ini > 0:
                    conn.execute(
                        """INSERT INTO movimientos_stock
                           (producto_id, tipo, cantidad, stock_anterior, stock_nuevo,
                            observaciones, usuario)
                           VALUES (?, 'ingreso', ?, 0, ?, ?, ?)""",
                        (pid, stock_ini, stock_ini, "Stock inicial",
                         self._usuario()),
                    )
                conn.commit()
                return pid
            except sqlite3.IntegrityError as e:
                conn.rollback()
                logger.error("integridad guardando producto %s: %s", codigo, e)
                return 0

    def eliminar_producto(self, producto_id: int) -> bool:
        with self._connect() as conn:
            try:
                cur = conn.execute("DELETE FROM productos WHERE id = ?", (producto_id,))
                conn.commit()
                return cur.rowcount > 0
            except sqlite3.IntegrityError:
                conn.rollback()
                logger.warning("no se puede eliminar producto %s: tiene movimientos", producto_id)
                return False

    def actualizar_stock(
        self,
        producto_id: int,
        cantidad: int,
        tipo: str = "ajuste",
        referencia_id: Optional[int] = None,
        observaciones: str = "",
    ) -> bool:
        """Ajuste simple de stock (positivo suma, negativo resta según tipo)."""
        if tipo not in ("venta", "ajuste", "devolucion", "ingreso"):
            return False
        if cantidad < 0:
            return False
        with self._connect() as conn:
            try:
                cur = conn.execute("SELECT stock_actual FROM productos WHERE id = ?", (producto_id,))
                row = cur.fetchone()
                if not row:
                    return False
                anterior = int(row["stock_actual"])
                nuevo = anterior - cantidad if tipo == "venta" else anterior + cantidad
                if nuevo < 0:
                    logger.warning("stock negativo bloqueado prod=%s", producto_id)
                    return False
                conn.execute("UPDATE productos SET stock_actual=?, fecha_modificacion=CURRENT_TIMESTAMP WHERE id=?", (nuevo, producto_id))
                conn.execute(
                    """INSERT INTO movimientos_stock
                       (producto_id, tipo, cantidad, stock_anterior, stock_nuevo,
                        referencia_id, observaciones, usuario)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (producto_id, tipo, cantidad, anterior, nuevo, referencia_id,
                     observaciones, self._usuario()),
                )
                conn.commit()
                return True
            except Exception as e:  # noqa: BLE001
                conn.rollback()
                logger.error("actualizar_stock: %s", e)
                return False

    # ---------- proveedores ----------
    def listar_proveedores(self, termino: str = "", limit: int = 500) -> List[dict]:
        termino = (termino or "").strip()
        with self._connect() as conn:
            sql = """SELECT p.*,
                            (SELECT COUNT(*) FROM proveedor_contactos c
                             WHERE c.proveedor_id = p.id) AS contactos_count
                     FROM proveedores p"""
            params: list = []
            if termino:
                sql += " WHERE p.nombre LIKE ? OR p.cuit LIKE ? OR p.telefono LIKE ?"
                like = f"%{termino}%"
                params = [like, like, like]
            sql += " ORDER BY p.nombre LIMIT ?"
            params.append(int(limit))
            cur = conn.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]

    def obtener_proveedor(self, proveedor_id: int) -> Optional[dict]:
        with self._connect() as conn:
            cur = conn.execute("SELECT * FROM proveedores WHERE id=?", (proveedor_id,))
            row = cur.fetchone()
            if not row:
                return None
            data = dict(row)
            cur = conn.execute(
                "SELECT * FROM proveedor_contactos WHERE proveedor_id=? ORDER BY nombre",
                (proveedor_id,),
            )
            data["contactos"] = [dict(r) for r in cur.fetchall()]
            return data

    def guardar_proveedor(self, datos: dict, contactos: Optional[List[dict]] = None) -> int:
        """Alta/edición de proveedor (por id o por nombre único). Retorna id o 0."""
        nombre = str(datos.get("nombre", "")).strip()
        if not nombre:
            return 0
        proveedor_id = datos.get("id")
        try:
            proveedor_id = int(proveedor_id) if proveedor_id else None
        except (TypeError, ValueError):
            proveedor_id = None
        campos = {
            "cuit": str(datos.get("cuit", "") or "").strip(),
            "telefono": str(datos.get("telefono", "") or "").strip(),
            "email": str(datos.get("email", "") or "").strip(),
            "direccion": str(datos.get("direccion", "") or "").strip(),
            "notas": str(datos.get("notas", "") or "").strip(),
        }
        with self._connect() as conn:
            try:
                if proveedor_id is None:
                    row = conn.execute(
                        "SELECT id FROM proveedores WHERE lower(nombre)=lower(?)", (nombre,)
                    ).fetchone()
                    proveedor_id = int(row["id"]) if row else None
                if proveedor_id:
                    conn.execute(
                        """UPDATE proveedores SET nombre=?, cuit=?, telefono=?, email=?,
                           direccion=?, notas=?, fecha_modificacion=CURRENT_TIMESTAMP
                           WHERE id=?""",
                        (nombre, campos["cuit"], campos["telefono"], campos["email"],
                         campos["direccion"], campos["notas"], proveedor_id),
                    )
                else:
                    cur = conn.execute(
                        """INSERT INTO proveedores (nombre, cuit, telefono, email, direccion, notas)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (nombre, campos["cuit"], campos["telefono"], campos["email"],
                         campos["direccion"], campos["notas"]),
                    )
                    proveedor_id = int(cur.lastrowid)
                if contactos is not None:
                    conn.execute("DELETE FROM proveedor_contactos WHERE proveedor_id=?", (proveedor_id,))
                    for c in contactos:
                        c_nombre = str(c.get("nombre", "") or "").strip()
                        if not c_nombre:
                            continue
                        conn.execute(
                            """INSERT INTO proveedor_contactos
                               (proveedor_id, nombre, telefono, email) VALUES (?, ?, ?, ?)""",
                            (proveedor_id, c_nombre,
                             str(c.get("telefono", "") or "").strip(),
                             str(c.get("email", "") or "").strip()),
                        )
                conn.commit()
                return proveedor_id
            except sqlite3.IntegrityError as e:
                conn.rollback()
                logger.error("guardar_proveedor: %s", e)
                return 0

    def eliminar_proveedor(self, proveedor_id: int) -> bool:
        with self._connect() as conn:
            try:
                en_ordenes = conn.execute(
                    "SELECT COUNT(*) FROM orden_compra_items WHERE proveedor_id=?",
                    (proveedor_id,),
                ).fetchone()[0]
                if int(en_ordenes or 0) > 0:
                    logger.warning("proveedor %s referenciado por órdenes de compra", proveedor_id)
                    return False
                conn.execute("UPDATE productos SET proveedor_id=NULL WHERE proveedor_id=?", (proveedor_id,))
                conn.execute("DELETE FROM proveedor_contactos WHERE proveedor_id=?", (proveedor_id,))
                cur = conn.execute("DELETE FROM proveedores WHERE id=?", (proveedor_id,))
                conn.commit()
                return cur.rowcount > 0
            except Exception as e:  # noqa: BLE001
                conn.rollback()
                logger.error("eliminar_proveedor: %s", e)
                return False

    def obtener_o_crear_proveedor(self, nombre: str) -> Optional[int]:
        nombre = str(nombre or "").strip()
        if not nombre:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM proveedores WHERE lower(nombre)=lower(?)", (nombre,)
            ).fetchone()
            if row:
                return int(row["id"])
            try:
                cur = conn.execute("INSERT INTO proveedores (nombre) VALUES (?)", (nombre,))
                conn.commit()
                return int(cur.lastrowid)
            except sqlite3.IntegrityError:
                conn.rollback()
                row = conn.execute(
                    "SELECT id FROM proveedores WHERE lower(nombre)=lower(?)", (nombre,)
                ).fetchone()
                return int(row["id"]) if row else None

    # ---------- órdenes de compra / reposición ----------
    @staticmethod
    def _normalizar_items_orden(items: List[dict]) -> List[tuple]:
        normalizados: list[tuple] = []
        for it in items or []:
            try:
                producto_id = int(it.get("producto_id"))
                cantidad = int(it.get("cantidad"))
            except (TypeError, ValueError):
                continue
            if cantidad <= 0:
                continue
            proveedor_id = it.get("proveedor_id")
            try:
                proveedor_id = int(proveedor_id) if proveedor_id not in (None, "", 0, "0") else None
            except (TypeError, ValueError):
                proveedor_id = None
            try:
                precio = float(it.get("precio_costo") or 0)
            except (TypeError, ValueError):
                precio = 0.0
            if precio < 0:
                precio = 0.0
            normalizados.append(
                (producto_id, proveedor_id, cantidad, precio, round(precio * cantidad, 2))
            )
        return normalizados

    def crear_orden_compra(self, items: List[dict], observaciones: str = "") -> int:
        normalizados = self._normalizar_items_orden(items)
        if not normalizados:
            return 0
        with self._connect() as conn:
            try:
                cur = conn.execute(
                    """INSERT INTO ordenes_compra
                       (estado, observaciones, usuario)
                       VALUES ('en_proceso', ?, ?)""",
                    (observaciones or "", self._usuario()),
                )
                orden_id = int(cur.lastrowid)
                for producto_id, proveedor_id, cantidad, precio, subtotal in normalizados:
                    conn.execute(
                        """INSERT INTO orden_compra_items
                           (orden_id, producto_id, proveedor_id, cantidad, precio_costo, subtotal)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (orden_id, producto_id, proveedor_id, cantidad, precio, subtotal),
                    )
                conn.commit()
                return orden_id
            except Exception as e:  # noqa: BLE001
                conn.rollback()
                logger.error("crear_orden_compra: %s", e)
                return 0

    def actualizar_orden_compra(self, orden_id: int, items: List[dict],
                                observaciones: Optional[str] = None) -> bool:
        normalizados = self._normalizar_items_orden(items)
        if not normalizados:
            return False
        with self._connect() as conn:
            try:
                row = conn.execute(
                    "SELECT estado FROM ordenes_compra WHERE id=?", (orden_id,)
                ).fetchone()
                if not row or row["estado"] != "en_proceso":
                    return False
                conn.execute("DELETE FROM orden_compra_items WHERE orden_id=?", (orden_id,))
                for producto_id, proveedor_id, cantidad, precio, subtotal in normalizados:
                    conn.execute(
                        """INSERT INTO orden_compra_items
                           (orden_id, producto_id, proveedor_id, cantidad, precio_costo, subtotal)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (orden_id, producto_id, proveedor_id, cantidad, precio, subtotal),
                    )
                if observaciones is None:
                    conn.execute(
                        "UPDATE ordenes_compra SET fecha_modificacion=CURRENT_TIMESTAMP WHERE id=?",
                        (orden_id,),
                    )
                else:
                    conn.execute(
                        """UPDATE ordenes_compra SET observaciones=?,
                           fecha_modificacion=CURRENT_TIMESTAMP WHERE id=?""",
                        (observaciones or "", orden_id),
                    )
                conn.commit()
                return True
            except Exception as e:  # noqa: BLE001
                conn.rollback()
                logger.error("actualizar_orden_compra: %s", e)
                return False

    def confirmar_orden_compra(self, orden_id: int) -> Tuple[bool, str]:
        """Recibe la totalidad de lo pendiente y confirma la orden."""
        detalle = self.obtener_orden_compra(int(orden_id))
        if not detalle:
            return False, "La orden no existe"
        if detalle.get("estado") not in ("en_proceso", "parcial"):
            return False, (f"La orden está {detalle.get('estado')} "
                           "y no se puede confirmar")
        recepciones = {
            int(it["id"]): int(it["cantidad"]) - int(it.get("cantidad_recibida") or 0)
            for it in (detalle.get("items") or [])
            if int(it["cantidad"]) - int(it.get("cantidad_recibida") or 0) > 0
        }
        if not recepciones:
            return False, "La orden no tiene cantidades pendientes"
        return self.recibir_orden_compra(
            int(orden_id), recepciones, observaciones="Confirmación total")

    def recibir_orden_compra(self, orden_id: int, recepciones,
                             remito: str = "", observaciones: str = "",
                             cancelar_restante: bool = False) -> Tuple[bool, str]:
        """Registra una recepción (parcial o total) de una orden de compra.

        ``recepciones`` puede ser un dict ``{item_id: cantidad}`` o una lista de
        dicts con ``item_id`` y ``cantidad``. Suma stock y deja la orden en
        estado ``parcial`` o ``confirmada`` según lo pendiente.
        """
        if isinstance(recepciones, dict):
            pares = [(k, v) for k, v in recepciones.items()]
        else:
            pares = [(r.get("item_id"), r.get("cantidad")) for r in (recepciones or [])]
        cantidades: dict[int, int] = {}
        for item_id, cant in pares:
            try:
                item_id = int(item_id)
                cant = int(cant)
            except (TypeError, ValueError):
                continue
            if cant > 0:
                cantidades[item_id] = cantidades.get(item_id, 0) + cant

        with self._connect() as conn:
            try:
                orden = conn.execute(
                    "SELECT id, estado, observaciones FROM ordenes_compra WHERE id=?",
                    (orden_id,),
                ).fetchone()
                if not orden:
                    return False, "La orden no existe"
                if orden["estado"] not in ("en_proceso", "parcial"):
                    return False, (f"La orden está {orden['estado']} "
                                   "y no se puede recepcionar")
                items = {int(r["id"]): r for r in conn.execute(
                    "SELECT * FROM orden_compra_items WHERE orden_id=?",
                    (orden_id,)).fetchall()}
                if not items:
                    return False, "La orden no tiene artículos"

                for item_id, cant in cantidades.items():
                    item = items.get(item_id)
                    if not item:
                        return False, f"El ítem #{item_id} no pertenece a la orden"
                    pendiente = int(item["cantidad"]) - int(item["cantidad_recibida"] or 0)
                    if cant > pendiente:
                        return False, (f"«{item['producto_id']}»: no se puede recibir "
                                       f"{cant} cuando quedan {pendiente}")

                if not cantidades and not cancelar_restante:
                    return False, "Ingresá al menos una cantidad a recibir"

                cur = conn.execute(
                    """INSERT INTO orden_compra_recepciones
                       (orden_id, remito, observaciones, cancelo_restante,
                        usuario)
                       VALUES (?, ?, ?, ?, ?)""",
                    (orden_id, (remito or "").strip(), (observaciones or "").strip(),
                     1 if cancelar_restante else 0, self._usuario()),
                )
                recepcion_id = int(cur.lastrowid)

                for item_id, cant in cantidades.items():
                    item = items[item_id]
                    pid = int(item["producto_id"])
                    producto = conn.execute(
                        "SELECT stock_actual FROM productos WHERE id=?", (pid,)
                    ).fetchone()
                    if not producto:
                        return False, f"El producto #{pid} ya no existe"
                    anterior = int(producto["stock_actual"])
                    nuevo = anterior + cant
                    conn.execute(
                        """UPDATE productos SET stock_actual=?,
                           fecha_modificacion=CURRENT_TIMESTAMP WHERE id=?""",
                        (nuevo, pid),
                    )
                    obs_mov = f"Recepción orden de compra #{orden_id}"
                    if remito:
                        obs_mov += f" · remito {remito}"
                    conn.execute(
                        """INSERT INTO movimientos_stock
                           (producto_id, tipo, cantidad, stock_anterior, stock_nuevo,
                            referencia_id, observaciones, usuario)
                           VALUES (?, 'ingreso', ?, ?, ?, ?, ?, ?)""",
                        (pid, cant, anterior, nuevo, orden_id, obs_mov,
                         self._usuario()),
                    )
                    conn.execute(
                        """UPDATE orden_compra_items
                           SET cantidad_recibida = cantidad_recibida + ?
                           WHERE id=?""",
                        (cant, item_id),
                    )
                    conn.execute(
                        """INSERT INTO orden_compra_recepcion_items
                           (recepcion_id, item_id, producto_id, cantidad)
                           VALUES (?, ?, ?, ?)""",
                        (recepcion_id, item_id, pid, cant),
                    )

                if cancelar_restante:
                    for item_id, item in items.items():
                        recibida_total = (int(item["cantidad_recibida"] or 0)
                                          + int(cantidades.get(item_id, 0)))
                        pendiente = int(item["cantidad"]) - recibida_total
                        if pendiente <= 0:
                            continue
                        if recibida_total <= 0:
                            conn.execute(
                                "DELETE FROM orden_compra_items WHERE id=?", (item_id,))
                        else:
                            conn.execute(
                                """UPDATE orden_compra_items
                                   SET cantidad=?, cantidad_recibida=?, subtotal=?
                                   WHERE id=?""",
                                (recibida_total, recibida_total,
                                 round(float(item["precio_costo"] or 0) * recibida_total, 2),
                                 item_id),
                            )

                pendientes = conn.execute(
                    """SELECT COALESCE(SUM(cantidad - cantidad_recibida), 0)
                       FROM orden_compra_items WHERE orden_id=?""",
                    (orden_id,),
                ).fetchone()[0] or 0
                pendientes = int(pendientes)

                if pendientes > 0:
                    conn.execute(
                        """UPDATE ordenes_compra SET estado='parcial',
                           fecha_modificacion=CURRENT_TIMESTAMP WHERE id=?""",
                        (orden_id,),
                    )
                    estado_msg = f"Recepción parcial registrada. Quedan {pendientes} unidades pendientes."
                else:
                    conn.execute(
                        """UPDATE ordenes_compra SET estado='confirmada',
                           fecha_confirmacion=CURRENT_TIMESTAMP,
                           fecha_modificacion=CURRENT_TIMESTAMP WHERE id=?""",
                        (orden_id,),
                    )
                    estado_msg = "Recepción registrada. La orden quedó confirmada."
                conn.commit()
                return True, estado_msg
            except Exception as e:  # noqa: BLE001
                conn.rollback()
                logger.error("recibir_orden_compra: %s", e)
                return False, str(e)

    def cancelar_orden_compra(self, orden_id: int) -> bool:
        with self._connect() as conn:
            try:
                cur = conn.execute(
                    """UPDATE ordenes_compra SET estado='cancelada',
                       fecha_modificacion=CURRENT_TIMESTAMP
                       WHERE id=? AND estado IN ('en_proceso', 'parcial')""",
                    (orden_id,),
                )
                conn.commit()
                return cur.rowcount > 0
            except Exception as e:  # noqa: BLE001
                conn.rollback()
                logger.error("cancelar_orden_compra: %s", e)
                return False

    def listar_ordenes_compra(self, estado: Optional[str] = None,
                              proveedor: str = "", desde: str = "",
                              hasta: str = "", ordenar: str = "fecha",
                              ascendente: bool = False) -> List[dict]:
        """Lista órdenes con filtros por estado, proveedor y rango de fechas.

        ``desde``/``hasta`` en formato YYYY-MM-DD. ``ordenar`` acepta:
        numero, fecha, estado, proveedores, items, unidades, total, pendientes.
        """
        columnas = {
            "numero": "oc.id",
            "fecha": "oc.fecha_creacion",
            "usuario": "oc.usuario",
            "estado": "oc.estado",
            "proveedores": "proveedores",
            "items": "items_count",
            "unidades": "unidades",
            "recibidas": "unidades_recibidas",
            "total": "total",
            "pendientes": "pendientes",
        }
        orden_sql = columnas.get((ordenar or "fecha").lower(), "oc.fecha_creacion")
        direccion = "ASC" if ascendente else "DESC"
        with self._connect() as conn:
            sql = """SELECT oc.*,
                            COUNT(i.id) AS items_count,
                            COALESCE(SUM(i.cantidad), 0) AS unidades,
                            COALESCE(SUM(i.cantidad_recibida), 0) AS unidades_recibidas,
                            COALESCE(SUM(i.cantidad - i.cantidad_recibida), 0) AS pendientes,
                            COALESCE(SUM(i.subtotal), 0) AS total,
                            GROUP_CONCAT(DISTINCT COALESCE(pr.nombre, 'Sin proveedor')) AS proveedores
                     FROM ordenes_compra oc
                     LEFT JOIN orden_compra_items i ON i.orden_id = oc.id
                     LEFT JOIN productos p ON p.id = i.producto_id
                     LEFT JOIN proveedores pr ON pr.id = COALESCE(i.proveedor_id, p.proveedor_id)
                     """
            where: list[str] = []
            params: list = []
            if estado:
                where.append("oc.estado = ?")
                params.append(estado)
            if (proveedor or "").strip():
                where.append(
                    """EXISTS (SELECT 1 FROM orden_compra_items oi
                               LEFT JOIN productos op ON op.id = oi.producto_id
                               LEFT JOIN proveedores opr
                                 ON opr.id = COALESCE(oi.proveedor_id, op.proveedor_id)
                               WHERE oi.orden_id = oc.id AND opr.nombre LIKE ?)""")
                params.append(f"%{proveedor.strip()}%")
            if (desde or "").strip():
                where.append("date(oc.fecha_creacion) >= date(?)")
                params.append(desde.strip())
            if (hasta or "").strip():
                where.append("date(oc.fecha_creacion) <= date(?)")
                params.append(hasta.strip())
            if where:
                sql += " WHERE " + " AND ".join(where)
            sql += (f" GROUP BY oc.id ORDER BY {orden_sql} {direccion}, oc.id DESC")
            cur = conn.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]

    def obtener_orden_compra(self, orden_id: int) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM ordenes_compra WHERE id=?", (orden_id,)
            ).fetchone()
            if not row:
                return None
            data = dict(row)
            cur = conn.execute(
                """SELECT i.id, i.orden_id, i.producto_id, i.cantidad,
                          i.cantidad_recibida,
                          (i.cantidad - i.cantidad_recibida) AS cantidad_pendiente,
                          i.precio_costo, i.subtotal,
                          i.proveedor_id AS proveedor_item_id,
                          p.codigo AS producto_codigo,
                          p.descripcion AS producto_nombre, p.stock_actual,
                          p.stock_minimo,
                          COALESCE(i.proveedor_id, p.proveedor_id) AS proveedor_id,
                          COALESCE(pr.nombre, 'Sin proveedor') AS proveedor_nombre
                   FROM orden_compra_items i
                   JOIN productos p ON p.id = i.producto_id
                   LEFT JOIN proveedores pr ON pr.id = COALESCE(i.proveedor_id, p.proveedor_id)
                   WHERE i.orden_id=?
                   ORDER BY COALESCE(pr.nombre, 'Sin proveedor'), p.descripcion""",
                (orden_id,),
            )
            data["items"] = [dict(r) for r in cur.fetchall()]
            data["recepciones"] = self._recepciones_de_orden(conn, orden_id)
            data["pendientes"] = sum(int(i["cantidad_pendiente"] or 0)
                                     for i in data["items"])
            return data

    @staticmethod
    def _recepciones_de_orden(conn, orden_id: int) -> List[dict]:
        cur = conn.execute(
            """SELECT r.*, u.descripcion AS producto_nombre, u.codigo AS producto_codigo,
                      ri.cantidad, ri.item_id
               FROM orden_compra_recepciones r
               LEFT JOIN orden_compra_recepcion_items ri ON ri.recepcion_id = r.id
               LEFT JOIN productos u ON u.id = ri.producto_id
               WHERE r.orden_id=?
               ORDER BY r.fecha DESC, r.id DESC""",
            (orden_id,),
        )
        agrupadas: dict[int, dict] = {}
        for fila in cur.fetchall():
            fila = dict(fila)
            rec = agrupadas.setdefault(fila["id"], {
                "id": fila["id"], "fecha": fila["fecha"],
                "remito": fila.get("remito") or "",
                "observaciones": fila.get("observaciones") or "",
                "cancelo_restante": bool(fila.get("cancelo_restante")),
                "usuario": fila.get("usuario") or "",
                "items": [],
            })
            if fila.get("item_id") is not None:
                rec["items"].append({
                    "producto_nombre": fila.get("producto_nombre") or "",
                    "producto_codigo": fila.get("producto_codigo") or "",
                    "cantidad": int(fila.get("cantidad") or 0),
                })
        return list(agrupadas.values())

    def contar_ordenes_compra(self, estado: str = "en_proceso") -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM ordenes_compra WHERE estado=?", (estado,)
            ).fetchone()
            return int(row[0] or 0)

    def contar_ordenes_pendientes(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM ordenes_compra "
                "WHERE estado IN ('en_proceso', 'parcial')"
            ).fetchone()
            return int(row[0] or 0)

    def buscar_ordenes_pendientes_producto(self, producto_id: int) -> List[dict]:
        """Órdenes con cantidad pendiente para un producto (para recepcionar)."""
        with self._connect() as conn:
            cur = conn.execute(
                """SELECT oc.id AS orden_id, oc.fecha_creacion, oc.estado,
                          i.id AS item_id, i.cantidad, i.cantidad_recibida,
                          (i.cantidad - i.cantidad_recibida) AS pendiente,
                          i.precio_costo,
                          i.proveedor_id AS proveedor_item_id,
                          COALESCE(pr.nombre, 'Sin proveedor') AS proveedor_nombre
                   FROM orden_compra_items i
                   JOIN ordenes_compra oc ON oc.id = i.orden_id
                   JOIN productos p ON p.id = i.producto_id
                   LEFT JOIN proveedores pr
                     ON pr.id = COALESCE(i.proveedor_id, p.proveedor_id)
                   WHERE i.producto_id = ?
                     AND oc.estado IN ('en_proceso', 'parcial')
                     AND i.cantidad > i.cantidad_recibida
                   ORDER BY oc.fecha_creacion ASC, oc.id ASC""",
                (producto_id,),
            )
            return [dict(r) for r in cur.fetchall()]

    def ingresar_stock_directo(self, producto_id: int, cantidad: int,
                               remito: str = "", observaciones: str = "") -> Tuple[bool, str]:
        """Ingreso de stock sin orden de compra (escaneo directo)."""
        try:
            cantidad = int(cantidad)
        except (TypeError, ValueError):
            return False, "Cantidad inválida"
        if cantidad <= 0:
            return False, "La cantidad debe ser mayor a cero"
        with self._connect() as conn:
            try:
                producto = conn.execute(
                    "SELECT descripcion, stock_actual FROM productos WHERE id=?",
                    (producto_id,),
                ).fetchone()
                if not producto:
                    return False, "Producto no encontrado"
                anterior = int(producto["stock_actual"])
                nuevo = anterior + cantidad
                conn.execute(
                    """UPDATE productos SET stock_actual=?,
                       fecha_modificacion=CURRENT_TIMESTAMP WHERE id=?""",
                    (nuevo, producto_id),
                )
                obs = observaciones or "Ingreso directo de stock"
                if remito:
                    obs += f" · remito {remito}"
                conn.execute(
                    """INSERT INTO movimientos_stock
                       (producto_id, tipo, cantidad, stock_anterior, stock_nuevo,
                        referencia_id, observaciones, usuario)
                       VALUES (?, 'ingreso', ?, ?, ?, NULL, ?, ?)""",
                    (producto_id, cantidad, anterior, nuevo, obs,
                     self._usuario()),
                )
                conn.commit()
                return True, (f"{producto['descripcion']}: {anterior} → {nuevo} "
                              f"(+{cantidad})")
            except Exception as e:  # noqa: BLE001
                conn.rollback()
                logger.error("ingresar_stock_directo: %s", e)
                return False, str(e)

    # ---------- stock / trazabilidad ----------
    def obtener_stock_productos(self) -> List[dict]:
        """Productos con estado y prioridad de reposición (agotados primero)."""
        with self._connect() as conn:
            cur = conn.execute(
                """SELECT p.*, pr.nombre AS proveedor_nombre,
                          CASE
                            WHEN p.stock_actual <= 0 THEN 'agotado'
                            WHEN p.stock_actual <= p.stock_minimo THEN 'bajo'
                            WHEN p.stock_minimo > 0
                                 AND p.stock_actual <= p.stock_minimo * 2 THEN 'por_agotar'
                            ELSE 'ok'
                          END AS estado_stock,
                          CASE
                            WHEN p.stock_actual <= 0 THEN 0
                            WHEN p.stock_actual <= p.stock_minimo THEN 1
                            WHEN p.stock_minimo > 0
                                 AND p.stock_actual <= p.stock_minimo * 2 THEN 2
                            ELSE 3
                          END AS prioridad_stock,
                          CASE WHEN p.stock_minimo > 0
                               THEN CAST(p.stock_actual AS REAL) / p.stock_minimo
                               ELSE 999999 END AS ratio_stock
                   FROM productos p
                   LEFT JOIN proveedores pr ON pr.id = p.proveedor_id
                   ORDER BY prioridad_stock ASC, ratio_stock ASC, p.descripcion"""
            )
            return [dict(r) for r in cur.fetchall()]

    def obtener_movimientos_stock_detallado(self, producto_id: Optional[int] = None,
                                            limit: int = 500) -> List[dict]:
        with self._connect() as conn:
            sql = """SELECT m.*, p.descripcion AS producto_nombre, p.codigo AS producto_codigo,
                            v.fecha AS venta_fecha, v.total AS venta_total,
                            v.metodo_pago AS venta_metodo_pago,
                            oc.fecha_creacion AS orden_fecha,
                            oc.fecha_confirmacion AS orden_fecha_confirmacion,
                            oc.estado AS orden_estado,
                            GROUP_CONCAT(DISTINCT COALESCE(pr.nombre, 'Sin proveedor')) AS orden_proveedores
                     FROM movimientos_stock m
                     JOIN productos p ON p.id = m.producto_id
                     LEFT JOIN ventas v ON m.tipo = 'venta' AND v.id = m.referencia_id
                     LEFT JOIN ordenes_compra oc ON m.tipo = 'ingreso' AND oc.id = m.referencia_id
                     LEFT JOIN orden_compra_items oi ON oi.orden_id = oc.id
                                                      AND oi.producto_id = m.producto_id
                     LEFT JOIN proveedores pr ON pr.id = COALESCE(oi.proveedor_id, p.proveedor_id)
                     """
            params: list = []
            if producto_id:
                sql += " WHERE m.producto_id = ?"
                params.append(int(producto_id))
            sql += " GROUP BY m.id ORDER BY m.fecha DESC, m.id DESC LIMIT ?"
            params.append(int(limit))
            cur = conn.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]

    def resumen_movimientos_producto(self, producto_id: int) -> dict:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT
                     COALESCE(SUM(CASE WHEN tipo='ingreso' THEN cantidad ELSE 0 END),0) AS ingresos,
                     COALESCE(SUM(CASE WHEN tipo='venta' THEN cantidad ELSE 0 END),0) AS ventas,
                     COALESCE(SUM(CASE WHEN tipo='devolucion' THEN cantidad ELSE 0 END),0) AS devoluciones,
                     COALESCE(SUM(CASE WHEN tipo='ajuste' THEN stock_nuevo - stock_anterior ELSE 0 END),0) AS ajuste_neto
                   FROM movimientos_stock WHERE producto_id=?""",
                (int(producto_id),),
            ).fetchone()
            return dict(row) if row else {}

    # ---------- primer uso / mantenimiento ----------
    def es_primer_uso(self) -> bool:
        valor = self.get_config_value("PRIMER_USO")
        if valor is not None and str(valor).strip() != "":
            return str(valor).strip().lower() in ("1", "si", "sí", "true", "yes", "on")
        # Compatibilidad: una base existente con datos no debe mostrar el asistente.
        with self._connect() as conn:
            productos = conn.execute("SELECT COUNT(*) FROM productos").fetchone()[0]
            ventas = conn.execute("SELECT COUNT(*) FROM ventas").fetchone()[0]
        primer_uso = int(productos or 0) == 0 and int(ventas or 0) == 0
        if not primer_uso:
            self.set_config("PRIMER_USO", "NO")
        return primer_uso

    def marcar_primer_uso(self, activo: bool) -> None:
        self.set_config("PRIMER_USO", "SI" if activo else "NO")

    def contar_datos(self) -> dict:
        tablas = ("productos", "ventas", "venta_items", "cajas", "gastos",
                  "movimientos_stock", "proveedores", "proveedor_contactos",
                  "ordenes_compra", "orden_compra_items")
        with self._connect() as conn:
            return {
                t: int(conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
                for t in tablas
            }

    def limpiar_datos_prueba(self, borrar_ventas: bool = True,
                             borrar_productos: bool = True) -> dict:
        """Borra datos de prueba. Si se borran productos, también ventas (FK)."""
        if borrar_productos:
            borrar_ventas = True
        resumen = self.contar_datos()
        with self._connect() as conn:
            try:
                if borrar_ventas:
                    conn.execute("DELETE FROM movimientos_stock WHERE tipo IN ('venta','devolucion')")
                    conn.execute("DELETE FROM venta_items")
                    conn.execute("DELETE FROM ventas")
                    conn.execute("DELETE FROM gastos")
                    conn.execute("DELETE FROM cajas")
                if borrar_productos:
                    conn.execute("DELETE FROM orden_compra_items")
                    conn.execute("DELETE FROM ordenes_compra")
                    conn.execute("DELETE FROM movimientos_stock")
                    conn.execute("DELETE FROM productos")
                tablas_reset = []
                if borrar_ventas:
                    tablas_reset += ["ventas", "venta_items", "cajas", "gastos"]
                if borrar_productos:
                    tablas_reset += ["productos", "ordenes_compra", "orden_compra_items"]
                for tabla in tablas_reset:
                    try:
                        conn.execute("DELETE FROM sqlite_sequence WHERE name=?", (tabla,))
                    except sqlite3.OperationalError:
                        pass
                if borrar_ventas or borrar_productos:
                    try:
                        conn.execute("DELETE FROM sqlite_sequence WHERE name='movimientos_stock'")
                    except sqlite3.OperationalError:
                        pass
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return resumen

    # ---------- cajas ----------
    def listar_cajas(self, filtro: str = "", desde: str = "",
                     hasta: str = "") -> List[dict]:
        """Historial de cajas.

        ``filtro``: nro de caja (id) o fecha de apertura (YYYY-MM-DD).
        ``desde``/``hasta``: rango de fechas de apertura (YYYY-MM-DD).
        """
        with self._connect() as conn:
            sql = "SELECT * FROM cajas"
            where: list[str] = []
            params: list = []
            if filtro and filtro.strip():
                where.append("(CAST(id AS TEXT) LIKE ? OR "
                             "strftime('%Y-%m-%d', fecha_apertura) LIKE ?)")
                params += [f"%{filtro.strip()}%", f"%{filtro.strip()}%"]
            if (desde or "").strip():
                where.append("date(fecha_apertura) >= date(?)")
                params.append(desde.strip())
            if (hasta or "").strip():
                where.append("date(fecha_apertura) <= date(?)")
                params.append(hasta.strip())
            if where:
                sql += " WHERE " + " AND ".join(where)
            sql += " ORDER BY fecha_apertura DESC"
            cur = conn.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]

    def obtener_ventas_por_caja(self, caja_id: int) -> List[dict]:
        """Ventas (con conteo de items) de una caja, ordenadas por fecha."""
        with self._connect() as conn:
            cur = conn.execute(
                """SELECT v.*, COUNT(vi.id) AS items_count FROM ventas v
                   LEFT JOIN venta_items vi ON v.id = vi.venta_id
                   WHERE v.caja_id=? AND v.estado='completada'
                   GROUP BY v.id ORDER BY v.fecha DESC""",
                (caja_id,),
            )
            return [dict(r) for r in cur.fetchall()]

    def obtener_caja_abierta(self) -> Optional[dict]:
        with self._connect() as conn:
            cur = conn.execute("SELECT * FROM cajas WHERE estado='abierta' ORDER BY fecha_apertura DESC LIMIT 1")
            row = cur.fetchone()
            return dict(row) if row else None

    def abrir_caja(self, importe_apertura: float, observaciones: str = "") -> int:
        if importe_apertura is None or float(importe_apertura) < 0:
            return 0
        if self.obtener_caja_abierta():
            logger.warning("ya hay una caja abierta")
            return 0
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO cajas
                   (fecha_apertura, importe_apertura, observaciones_apertura,
                    usuario_apertura, estado)
                   VALUES (?, ?, ?, ?, 'abierta')""",
                (datetime.now(), float(importe_apertura), observaciones or "",
                 self._usuario()),
            )
            conn.commit()
            return int(cur.lastrowid)

    def cerrar_caja(self, caja_id: int, observaciones: str = "") -> bool:
        with self._connect() as conn:
            try:
                cur = conn.execute("SELECT SUM(total) FROM ventas WHERE caja_id=? AND estado='completada'", (caja_id,))
                total_ventas = cur.fetchone()[0] or 0
                cur = conn.execute("SELECT SUM(monto) FROM gastos WHERE caja_id=?", (caja_id,))
                total_gastos = cur.fetchone()[0] or 0
                cur = conn.execute("SELECT importe_apertura FROM cajas WHERE id=?", (caja_id,))
                row = cur.fetchone()
                if not row:
                    return False
                cierre = float(row[0]) + float(total_ventas) - float(total_gastos)
                conn.execute(
                    """UPDATE cajas SET fecha_cierre=?, importe_cierre=?,
                       total_ventas=?, total_gastos=?, observaciones_cierre=?,
                       usuario_cierre=?, estado='cerrada' WHERE id=?""",
                    (datetime.now(), cierre, total_ventas, total_gastos,
                     observaciones or "", self._usuario(), caja_id),
                )
                conn.commit()
                return True
            except Exception as e:  # noqa: BLE001
                conn.rollback()
                logger.error("cerrar_caja: %s", e)
                return False

    # ---------- ventas (ATÓMICA) ----------
    def crear_venta(
        self, caja_id: int, items: List[dict], metodo_pago: str = "efectivo", comprobante: str = ""
    ) -> Tuple[int, bool]:
        """Crea venta + items + descuento de stock en UNA transacción.

        Retorna (venta_id, True) o (0, False). Valida stock antes de descontar.
        """
        if not caja_id or not items:
            return 0, False
        with self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                # validar caja abierta
                cur = conn.execute("SELECT id FROM cajas WHERE id=? AND estado='abierta'", (caja_id,))
                if not cur.fetchone():
                    logger.warning("crear_venta sin caja abierta: %s", caja_id)
                    return 0, False
                # validar stock y calcular total
                total = 0.0
                stocks: dict[int, int] = {}
                for it in items:
                    pid = int(it["producto_id"])
                    cant = int(it["cantidad"])
                    precio = float(it["precio_unitario"])
                    if cant <= 0 or precio < 0:
                        return 0, False
                    cur = conn.execute("SELECT stock_actual FROM productos WHERE id=?", (pid,))
                    row = cur.fetchone()
                    if not row or __import__("intrashop_checkout_store").available(conn, pid) < cant:
                        logger.warning("stock insuficiente prod=%s", pid)
                        return 0, False
                    stocks[pid] = int(row["stock_actual"])
                    total += precio * cant
                cur = conn.execute(
                    """INSERT INTO ventas
                       (caja_id, fecha, total, estado, metodo_pago, comprobante,
                        usuario)
                       VALUES (?, ?, ?, 'completada', ?, ?, ?)""",
                    (caja_id, datetime.now(), round(total, 2), metodo_pago,
                     comprobante or "", self._usuario()),
                )
                venta_id = int(cur.lastrowid)
                for it in items:
                    pid = int(it["producto_id"])
                    cant = int(it["cantidad"])
                    precio = float(it["precio_unitario"])
                    subtotal = round(precio * cant, 2)
                    conn.execute(
                        "INSERT INTO venta_items (venta_id, producto_id, cantidad, precio_unitario, subtotal) VALUES (?, ?, ?, ?, ?)",
                        (venta_id, pid, cant, precio, subtotal),
                    )
                    anterior = stocks[pid]
                    nuevo = anterior - cant
                    conn.execute("UPDATE productos SET stock_actual=?, fecha_modificacion=CURRENT_TIMESTAMP WHERE id=?", (nuevo, pid))
                    conn.execute(
                        """INSERT INTO movimientos_stock
                           (producto_id, tipo, cantidad, stock_anterior, stock_nuevo,
                            referencia_id, observaciones, usuario)
                           VALUES (?, 'venta', ?, ?, ?, ?, ?, ?)""",
                        (pid, cant, anterior, nuevo, venta_id,
                         f"Venta #{venta_id}", self._usuario()),
                    )
                conn.commit()
                return venta_id, True
            except Exception as e:  # noqa: BLE001
                conn.rollback()
                logger.error("crear_venta: %s", e)
                return 0, False

    def actualizar_factura_venta(
        self, venta_id: int, numero_factura, cae, vencimiento_cae
    ) -> bool:
        """Actualiza una venta con los datos de facturación AFIP.

        Si la DB es vieja y le faltan las columnas, las agrega primero.
        """
        with self._connect() as conn:
            try:
                cur = conn.execute(
                    "SELECT COUNT(*) FROM pragma_table_info('ventas') "
                    "WHERE name IN ('numero_factura', 'cae', 'vencimiento_cae')"
                )
                if int(cur.fetchone()[0]) < 3:
                    for col in ("numero_factura", "cae", "vencimiento_cae"):
                        try:
                            conn.execute(f"ALTER TABLE ventas ADD COLUMN {col} TEXT")
                        except sqlite3.OperationalError:
                            pass
                    conn.commit()
                conn.execute(
                    "UPDATE ventas SET numero_factura=?, cae=?, vencimiento_cae=? WHERE id=?",
                    (str(numero_factura), str(cae), str(vencimiento_cae), venta_id),
                )
                conn.commit()
                return True
            except Exception as e:  # noqa: BLE001
                conn.rollback()
                logger.error("actualizar_factura_venta: %s", e)
                return False

    def obtener_ventas_del_dia(self, caja_id: int) -> List[dict]:
        with self._connect() as conn:
            cur = conn.execute(
                """SELECT v.*, COUNT(vi.id) AS items_count FROM ventas v
                   LEFT JOIN venta_items vi ON v.id = vi.venta_id
                   WHERE v.caja_id=? AND v.estado='completada'
                   GROUP BY v.id ORDER BY v.fecha DESC""",
                (caja_id,),
            )
            return [dict(r) for r in cur.fetchall()]

    def obtener_items_venta(self, venta_id: int) -> List[dict]:
        with self._connect() as conn:
            cur = conn.execute(
                """SELECT vi.*, p.descripcion AS producto_nombre FROM venta_items vi
                   JOIN productos p ON vi.producto_id = p.id WHERE vi.venta_id=?""",
                (venta_id,),
            )
            return [dict(r) for r in cur.fetchall()]

    def obtener_ventas_por_fechas(self, desde_iso: str, hasta_iso: str) -> List[dict]:
        """Ventas (con conteo de items) en un rango ISO 'YYYY-MM-DD HH:MM:SS'."""
        with self._connect() as conn:
            cur = conn.execute(
                """SELECT v.*, COUNT(vi.id) AS items_count FROM ventas v
                   LEFT JOIN venta_items vi ON v.id = vi.venta_id
                   WHERE v.fecha BETWEEN ? AND ?
                   GROUP BY v.id ORDER BY v.fecha DESC""",
                (desde_iso, hasta_iso),
            )
            return [dict(r) for r in cur.fetchall()]

    def obtener_detalle_ventas(self, desde_iso: str, hasta_iso: str) -> List[dict]:
        """Detalle plano venta+items para el reporte (como en reporte.py del build)."""
        with self._connect() as conn:
            cur = conn.execute(
                """SELECT v.id, v.fecha, v.estado, v.total, v.metodo_pago,
                          vi.cantidad, vi.precio_unitario, vi.subtotal, vi.producto_id,
                          p.descripcion AS nombre_producto,
                          COUNT(vi.id) OVER (PARTITION BY v.id) AS cantidad_items
                   FROM ventas v
                   LEFT JOIN venta_items vi ON v.id = vi.venta_id
                   LEFT JOIN productos p ON vi.producto_id = p.id
                   WHERE v.fecha BETWEEN ? AND ?
                   ORDER BY v.fecha DESC, v.id""",
                (desde_iso, hasta_iso),
            )
            return [dict(r) for r in cur.fetchall()]

    def obtener_top_productos(self, desde_iso: str, hasta_iso: str, limit: int = 10) -> List[dict]:
        """Productos más vendidos en un rango: cantidad, monto y nº de ventas."""
        with self._connect() as conn:
            cur = conn.execute(
                """SELECT p.id, p.descripcion,
                          COALESCE(SUM(vi.cantidad), 0) AS cantidad_total,
                          COALESCE(SUM(vi.subtotal), 0) AS monto_total,
                          COUNT(DISTINCT v.id) AS num_ventas
                   FROM venta_items vi
                   JOIN ventas v ON vi.venta_id = v.id
                   JOIN productos p ON vi.producto_id = p.id
                   WHERE v.fecha BETWEEN ? AND ? AND v.estado = 'completada'
                   GROUP BY p.id
                   ORDER BY cantidad_total DESC, monto_total DESC
                   LIMIT ?""",
                (desde_iso, hasta_iso, int(limit)),
            )
            return [dict(r) for r in cur.fetchall()]

    def obtener_ventas_por_dia(self, desde_iso: str, hasta_iso: str) -> List[dict]:
        """Totales y cantidad de ventas agrupados por día (para gráficos)."""
        with self._connect() as conn:
            cur = conn.execute(
                """SELECT date(fecha) AS dia,
                          COUNT(*) AS cantidad,
                          ROUND(SUM(total), 2) AS total
                   FROM ventas
                   WHERE fecha BETWEEN ? AND ? AND estado = 'completada'
                   GROUP BY date(fecha)
                   ORDER BY dia""",
                (desde_iso, hasta_iso),
            )
            return [dict(r) for r in cur.fetchall()]

    # ---------- config ----------
    def set_config(self, clave: str, valor: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO config (clave, valor) VALUES (?, ?) ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor",
                (clave, valor),
            )
            conn.commit()

    def get_config(self, clave: str) -> Optional[str]:
        return self.get_config_value(clave)

    def get_config_value(self, clave: str) -> Optional[str]:
        with self._connect() as conn:
            cur = conn.execute("SELECT valor FROM config WHERE clave=?", (clave,))
            row = cur.fetchone()
            return row["valor"] if row else None

    def get_all_config(self) -> dict:
        with self._connect() as conn:
            cur = conn.execute("SELECT clave, valor FROM config")
            return {r["clave"]: r["valor"] for r in cur.fetchall()}

    # ---------- gastos ----------
    def agregar_gasto(self, caja_id: int, monto: float, concepto: str) -> int:
        if not concepto or not concepto.strip() or float(monto) <= 0:
            return 0
        with self._connect() as conn:
            try:
                cur = conn.execute(
                    """INSERT INTO gastos
                       (caja_id, monto, concepto, fecha, usuario)
                       VALUES (?, ?, ?, ?, ?)""",
                    (caja_id, float(monto), concepto.strip(), datetime.now(),
                     self._usuario()),
                )
                conn.commit()
                return int(cur.lastrowid)
            except Exception as e:  # noqa: BLE001
                conn.rollback()
                logger.error("agregar_gasto: %s", e)
                return 0

    def obtener_gastos_caja(self, caja_id: int) -> List[dict]:
        with self._connect() as conn:
            cur = conn.execute("SELECT * FROM gastos WHERE caja_id=? ORDER BY fecha DESC", (caja_id,))
            return [dict(r) for r in cur.fetchall()]

    # ---------- reportes ----------
    def obtener_productos_bajo_stock(self) -> List[dict]:
        with self._connect() as conn:
            cur = conn.execute("SELECT * FROM productos WHERE stock_actual <= stock_minimo ORDER BY stock_actual ASC")
            return [dict(r) for r in cur.fetchall()]

    def obtener_movimientos_stock(self, producto_id: Optional[int] = None, limit: int = 100) -> List[dict]:
        with self._connect() as conn:
            if producto_id:
                cur = conn.execute(
                    """SELECT m.*, p.descripcion AS producto_nombre FROM movimientos_stock m
                       JOIN productos p ON m.producto_id=p.id
                       WHERE m.producto_id=? ORDER BY m.fecha DESC LIMIT ?""",
                    (producto_id, limit),
                )
            else:
                cur = conn.execute(
                    """SELECT m.*, p.descripcion AS producto_nombre FROM movimientos_stock m
                       JOIN productos p ON m.producto_id=p.id
                       ORDER BY m.fecha DESC LIMIT ?""",
                    (limit,),
                )
            return [dict(r) for r in cur.fetchall()]

"""Cliente HTTP para modo multi-usuario (cliente).

Implementa la misma interfaz pública mínima que DatabaseManager para que la app
pueda funcionar indistintamente en modo local o cliente.
"""
from __future__ import annotations

import os
from typing import Any, Optional

import httpx


class ApiClient:
    def __init__(self, base_url: str, api_key: str = "libreria-lan"):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._headers = {"X-API-Key": api_key}

    def _get(self, path, params=None):
        r = httpx.get(self.base_url + path, params=params, headers=self._headers, timeout=15)
        r.raise_for_status()
        return r.json()

    def _admin_headers(self):
        from adapters import entregas
        token = entregas._session_token
        if not token:
            raise PermissionError("Iniciá sesión como administrador POS para gestionar usuarios y roles")
        return {**self._headers, "Authorization": "Bearer " + token}

    def _admin_request(self, method, path, json=None):
        response = httpx.request(method, self.base_url + path,
                                 json=json, headers=self._admin_headers(), timeout=15)
        response.raise_for_status()
        return response.json()

    def listar_roles(self):
        return self._admin_request("GET", "/roles")

    def obtener_rol(self, rol_id):
        return self._admin_request("GET", f"/roles/{int(rol_id)}")

    def guardar_rol(self, datos):
        result = self._admin_request("POST", "/roles", json=datos)
        return result["id"], result["error"]

    def eliminar_rol(self, rol_id):
        result = self._admin_request("DELETE", f"/roles/{int(rol_id)}")
        return result["ok"], result["error"]

    def listar_usuarios(self):
        return self._admin_request("GET", "/usuarios")

    def obtener_usuario(self, usuario_id):
        return self._admin_request("GET", f"/usuarios/{int(usuario_id)}")

    def guardar_usuario(self, datos):
        result = self._admin_request("POST", "/usuarios", json=datos)
        return result["id"], result["error"]

    def eliminar_usuario(self, usuario_id):
        result = self._admin_request("DELETE", f"/usuarios/{int(usuario_id)}")
        return result["ok"], result["error"]

    def _post(self, path, json=None, params=None):
        r = httpx.post(self.base_url + path, json=json, params=params, headers=self._headers, timeout=15)
        r.raise_for_status()
        return r.json()

    def autenticar_usuario(self, usuario: str, clave: str):
        try:
            from core.terminal_identity import terminal_id
            response = httpx.post(self.base_url + "/pos/auth/login",
                json={"usuario": usuario, "clave": clave},
                headers={"X-Terminal-Id": terminal_id()}, timeout=8)
            if response.status_code != 200:
                return None
            data = response.json()
            from adapters.entregas import set_session
            set_session(data["access_token"])
            return {"usuario": data["usuario"], "nombre": data["usuario"],
                    "rol": data.get("rol", "OPERADOR"), "es_admin": data.get("es_admin", False),
                    "permisos": data.get("permisos", {}), "activo": True}
        except Exception:
            return None

    def health(self) -> bool:
        try:
            return httpx.get(self.base_url + "/health", timeout=5).status_code == 200
        except Exception:
            return False

    def get_config(self, clave: str) -> Optional[str]:
        return self.get_config_value(clave)

    def get_config_value(self, clave: str) -> Optional[str]:
        try:
            data = self._get("/config")
            return data.get(clave)
        except Exception:
            return None

    def set_config(self, clave: str, valor: str) -> None:
        try:
            self._post("/config", json={"clave": clave, "valor": valor})
        except Exception:
            pass

    def get_all_config(self) -> dict:
        try:
            return self._get("/config")
        except Exception:
            return {}

    def buscar_productos(self, termino: str = "", campo: str = "descripcion", limit: int = 200):
        return self._get("/productos", params={"termino": termino, "campo": campo})[:limit]

    def guardar_producto(self, producto: dict) -> int:
        """Crea o actualiza un producto mediante el servidor LAN."""
        result = self._post("/productos", json=producto)
        return int(result.get("id", 0))


    def obtener_config_tienda_producto(self, producto_id: int) -> dict:
        return self._get(f"/tienda/admin/productos/{int(producto_id)}")

    def actualizar_config_tienda_producto(self, producto_id: int, *, disponible: bool,
                                          imagen_base64=None, imagen_nombre="producto.jpg",
                                          imagen_url=None) -> dict:
        response = httpx.put(
            self.base_url + f"/tienda/admin/productos/{int(producto_id)}",
            json={"disponible": disponible, "imagen_base64": imagen_base64,
                  "imagen_nombre": imagen_nombre, "imagen_url": imagen_url},
            headers=self._headers, timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def listar_cajas(self, filtro: str = "", desde: str = "", hasta: str = ""):
        return self._get("/cajas/historial",
                         params={"filtro": filtro, "desde": desde, "hasta": hasta})

    def obtener_ventas_por_caja(self, caja_id: int):
        return self._get(f"/cajas/{int(caja_id)}/ventas")

    def obtener_caja_abierta(self):
        return self._get("/cajas/abierta")

    def abrir_caja(self, importe_apertura: float = 0.0, observaciones: str = ""):
        return self._post("/cajas/abrir", params={"importe_apertura": importe_apertura, "observaciones": observaciones})["id"]

    def cerrar_caja(self, caja_id: int, observaciones: str = ""):
        return self._post(f"/cajas/{caja_id}/cerrar", params={"observaciones": observaciones})

    def crear_venta(self, caja_id, items, metodo_pago="efectivo", comprobante=""):
        r = self._post("/ventas", json={
            "caja_id": caja_id, "items": items,
            "metodo_pago": metodo_pago, "comprobante": comprobante,
        })
        return r["venta_id"], True

    def obtener_ventas_del_dia(self, caja_id: int):
        return self._get(f"/ventas/dia/{caja_id}")

    def obtener_items_venta(self, venta_id: int):
        return self._get(f"/ventas/{venta_id}/items")

    def actualizar_factura_venta(self, venta_id, numero_factura, cae, vencimiento_cae):
        try:
            self._post("/ventas/factura", json={
                "venta_id": venta_id, "numero_factura": str(numero_factura),
                "cae": str(cae), "vencimiento_cae": str(vencimiento_cae),
            })
            return True
        except Exception:
            return False

    def obtener_productos_bajo_stock(self):
        return self._get("/productos/bajo_stock")

    def obtener_top_productos(self, desde_iso: str, hasta_iso: str, limit: int = 10):
        return self._get("/reportes/top_productos",
                         params={"desde": desde_iso, "hasta": hasta_iso, "limit": limit})

    def obtener_ventas_por_dia(self, desde_iso: str, hasta_iso: str):
        return self._get("/reportes/ventas_por_dia",
                         params={"desde": desde_iso, "hasta": hasta_iso})

    # compat con código que espera atributos
    @property
    def db_path(self):
        return self.base_url


    # Proveedores y reposición: operaciones siempre en POS Server.
    def listar_proveedores(self, termino="", limit=500):
        return self._get("/proveedores", {"termino": termino, "limit": limit})

    def obtener_proveedor(self, proveedor_id):
        return self._get(f"/proveedores/{int(proveedor_id)}")

    def guardar_proveedor(self, datos, contactos=None):
        return self._post("/proveedores", {"datos": datos, "contactos": contactos})["id"]

    def eliminar_proveedor(self, proveedor_id):
        return self._post(f"/proveedores/{int(proveedor_id)}/eliminar")["ok"]

    def obtener_o_crear_proveedor(self, nombre):
        return self._post("/proveedores/obtener-o-crear", {"nombre": nombre})["id"]

    def crear_orden_compra(self, items, observaciones=""):
        return self._post("/reposicion/ordenes", {"items": items, "observaciones": observaciones})["id"]

    def actualizar_orden_compra(self, orden_id, items, observaciones=None):
        return self._post(f"/reposicion/ordenes/{int(orden_id)}/actualizar", {"items": items, "observaciones": observaciones})["ok"]

    def confirmar_orden_compra(self, orden_id):
        r = self._post(f"/reposicion/ordenes/{int(orden_id)}/confirmar")
        return r["ok"], r["mensaje"]

    def recibir_orden_compra(self, orden_id, recepciones, remito="", observaciones="", cancelar_restante=False):
        r = self._post(f"/reposicion/ordenes/{int(orden_id)}/recibir", {"recepciones": recepciones, "remito": remito, "observaciones": observaciones, "cancelar_restante": cancelar_restante})
        return r["ok"], r["mensaje"]

    def cancelar_orden_compra(self, orden_id):
        return self._post(f"/reposicion/ordenes/{int(orden_id)}/cancelar")["ok"]

    def listar_ordenes_compra(self, estado=None, proveedor="", desde="", hasta="", ordenar="fecha", ascendente=False):
        return self._get("/reposicion/ordenes", {"estado": estado, "proveedor": proveedor, "desde": desde, "hasta": hasta, "ordenar": ordenar, "ascendente": ascendente})

    def obtener_orden_compra(self, orden_id):
        return self._get(f"/reposicion/ordenes/{int(orden_id)}")

    def contar_ordenes_compra(self, estado="en_proceso"):
        return self._get("/reposicion/ordenes/contar", {"estado": estado})["total"]

    def contar_ordenes_pendientes(self):
        return self._get("/reposicion/ordenes/pendientes")["total"]

    def buscar_ordenes_pendientes_producto(self, producto_id):
        return self._get(f"/reposicion/productos/{int(producto_id)}/pendientes")

    def ingresar_stock_directo(self, producto_id, cantidad, remito="", observaciones=""):
        r = self._post(f"/reposicion/productos/{int(producto_id)}/ingresar", {"cantidad": cantidad, "remito": remito, "observaciones": observaciones})
        return r["ok"], r["mensaje"]

    def obtener_stock_productos(self):
        return self._get("/reposicion/stock")

    def obtener_movimientos_stock_detallado(self, producto_id=None, limit=500):
        return self._get("/reposicion/movimientos/detallados", {"producto_id": producto_id, "limit": limit})

    def resumen_movimientos_producto(self, producto_id):
        return self._get(f"/reposicion/productos/{int(producto_id)}/resumen")

    def obtener_movimientos_stock(self, producto_id=None, limit=100):
        return self._get("/reposicion/movimientos", {"producto_id": producto_id, "limit": limit})


    # Paridad de consultas y operaciones generales con DatabaseManager.
    def obtener_producto(self, producto_id):
        return self._get(f"/productos/{int(producto_id)}")

    def obtener_producto_por_codigo(self, codigo):
        return self._get("/productos/por-codigo", {"codigo": codigo})

    def eliminar_producto(self, producto_id):
        return self._post(f"/productos/{int(producto_id)}/eliminar")["ok"]

    def actualizar_stock(self, producto_id, cantidad, tipo="ajuste", referencia_id=None, observaciones=""):
        return self._post(f"/productos/{int(producto_id)}/stock", {"cantidad": cantidad, "tipo": tipo, "referencia_id": referencia_id, "observaciones": observaciones})["ok"]

    def obtener_ventas_por_fechas(self, desde_iso, hasta_iso):
        return self._get("/reportes/ventas", {"desde": desde_iso, "hasta": hasta_iso})

    def obtener_detalle_ventas(self, desde_iso, hasta_iso):
        return self._get("/reportes/ventas/detalle", {"desde": desde_iso, "hasta": hasta_iso})

    def agregar_gasto(self, caja_id, monto, concepto):
        return self._post(f"/cajas/{int(caja_id)}/gastos", {"monto": monto, "concepto": concepto})["id"]

    def obtener_gastos_caja(self, caja_id):
        return self._get(f"/cajas/{int(caja_id)}/gastos")

    def contar_datos(self):
        return self._admin_request("GET", "/admin/datos/conteos")

    def es_primer_uso(self):
        return self._admin_request("GET", "/admin/datos/primer-uso")["activo"]

    def marcar_primer_uso(self, activo):
        return self._admin_request("POST", "/admin/datos/primer-uso", json={"activo": bool(activo)})


    def validar_backup_servidor(self, archivo):
        """Envía un backup para inspección sin modificar la base del servidor.

        Requiere sesión de administrador; no transmite rutas ni credenciales por URL.
        Acepta bytes o ruta local de un archivo .db.
        """
        from pathlib import Path
        contenido = Path(archivo).read_bytes() if isinstance(archivo, (str, Path)) else bytes(archivo)
        if not contenido or len(contenido) > 100 * 1024 * 1024:
            raise ValueError("El backup debe tener entre 1 byte y 100 MiB")
        headers = {**self._admin_headers(), "Content-Type": "application/octet-stream"}
        respuesta = httpx.post(
            self.base_url + "/admin/backups/validar",
            content=contenido,
            headers=headers,
            timeout=120,
        )
        respuesta.raise_for_status()
        return respuesta.json()


    def exportar_backup_servidor(self, destino):
        """Descarga una copia consistente del POS Server, nunca de SQLite local."""
        from pathlib import Path
        import os
        import tempfile
        ruta = Path(destino).expanduser().resolve()
        ruta.parent.mkdir(parents=True, exist_ok=True)
        with httpx.stream(
            "GET", self.base_url + "/admin/backups/exportar",
            headers=self._admin_headers(), timeout=180,
        ) as respuesta:
            respuesta.raise_for_status()
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=str(ruta.parent), prefix=".backup-pos-", delete=False
            ) as temporal:
                temporal_path = Path(temporal.name)
                try:
                    for bloque in respuesta.iter_bytes(chunk_size=1024 * 1024):
                        temporal.write(bloque)
                except BaseException:
                    temporal_path.unlink(missing_ok=True)
                    raise
        try:
            from services.backup_service import validar_backup
            info = validar_backup(temporal_path)
            os.replace(temporal_path, ruta)
            info["destino"] = str(ruta)
            return info
        finally:
            temporal_path.unlink(missing_ok=True)


    def ajustar_stock_absoluto(self, producto_id, nuevo_stock, stock_esperado, observaciones=""):
        resultado = self._admin_request(
            "POST", f"/productos/{int(producto_id)}/stock-absoluto",
            json={"nuevo_stock": int(nuevo_stock), "stock_esperado": int(stock_esperado),
                  "observaciones": observaciones},
        )
        return bool(resultado["ok"])

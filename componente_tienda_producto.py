"""Configuración de publicación de un artículo en IntraShop."""
import shutil
from pathlib import Path

import flet as ft
from ui.paleta import N
from ui.helpers import cerrar_dialogo, snack
from utils.file_dialogs import pick_file


def ProductoTiendaModal(db_manager, producto, page, on_guardado=None):
    from intrashop_api import MEDIA_DIR, _ensure_schema

    _ensure_schema()
    producto_id = int(producto["id"])
    conn = db_manager.get_connection()
    try:
        row = conn.execute(
            "SELECT disponible_tienda, imagen_tienda FROM productos WHERE id=?",
            (producto_id,),
        ).fetchone()
    finally:
        conn.close()

    disponible = ft.Checkbox(
        label="Mostrar este producto en IntraShop",
        value=bool(row["disponible_tienda"]) if row else False,
    )
    imagen_actual = ft.Text(
        "Foto cargada" if row and row["imagen_tienda"] else "Se usará la imagen ilustrativa por defecto",
        size=12, color=N.GREY_400,
    )
    ruta_seleccionada = {"path": ""}
    url_imagen = ft.TextField(label="URL pública HTTPS (opcional)", hint_text="https://ejemplo.com/producto.jpg", value=row["imagen_tienda"] if row and str(row["imagen_tienda"]).startswith("https://") else "")

    async def seleccionar_imagen(e=None):
        ruta = await pick_file(
            page, title="Seleccionar foto del producto",
            extensions=["jpg", "jpeg", "png", "webp"],
        )
        if not ruta:
            return
        ext = Path(ruta).suffix.lower()
        if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
            snack(page, "Formato no permitido. Usá JPG, PNG o WebP.", ok=False)
            return
        if Path(ruta).stat().st_size > 5 * 1024 * 1024:
            snack(page, "La imagen no puede superar 5 MB.", ok=False)
            return
        ruta_seleccionada["path"] = ruta
        imagen_actual.value = f"Foto seleccionada: {Path(ruta).name}"
        page.update()

    def guardar(e=None):
        destino = ""
        try:
            _ensure_schema()
            if ruta_seleccionada["path"]:
                MEDIA_DIR.mkdir(parents=True, exist_ok=True)
                origen = Path(ruta_seleccionada["path"])
                destino_path = MEDIA_DIR / f"{producto_id}-{origen.name}"
                shutil.copy2(origen, destino_path)
                destino = str(destino_path.resolve())

            if url_imagen.value and not destino:
                from urllib.parse import urlparse
                parsed = urlparse(url_imagen.value.strip())
                if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
                    snack(page, "La imagen debe tener una URL pública HTTPS válida.", ok=False)
                    return
                destino = url_imagen.value.strip()

            conn = db_manager.get_connection()
            try:
                if destino:
                    conn.execute(
                        "UPDATE productos SET disponible_tienda=?, imagen_tienda=? WHERE id=?",
                        (int(bool(disponible.value)), destino, producto_id),
                    )
                else:
                    conn.execute(
                        "UPDATE productos SET disponible_tienda=? WHERE id=?",
                        (int(bool(disponible.value)), producto_id),
                    )
                conn.commit()
            finally:
                conn.close()

            try:
                dialog.open = False
                page.update()
            except Exception:
                cerrar_dialogo(page)
            if on_guardado:
                on_guardado()
            snack(page, "Configuración de IntraShop guardada.", ok=True)
        except Exception as ex:
            snack(page, f"No se pudo guardar: {ex}", ok=False)

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Row([
            ft.Icon(ft.Icons.STORE, color=N.PURPLE_300),
            ft.Text("PUBLICAR EN INTRASHOP", size=18, weight=ft.FontWeight.BOLD),
        ]),
        content=ft.Container(
            width=460,
            content=ft.Column([
                ft.Text(producto.get("descripcion", "Producto"), size=15,
                        weight=ft.FontWeight.BOLD),
                ft.Text(f"Código: {producto.get('codigo', '')} · Precio: ${float(producto.get('precio_lista') or 0):,.2f}",
                        size=12, color=N.GREY_400),
                ft.Divider(),
                disponible,
                ft.Text("Foto del catálogo", size=13, weight=ft.FontWeight.BOLD),
                imagen_actual,
                url_imagen,
                ft.Text("Las imágenes por URL requieren Internet en la pantalla de la tienda. Para uso 100% LAN, cargá una foto local.", size=11, color=N.GREY_500),
                ft.OutlinedButton(
                    "Elegir foto", icon=ft.Icons.UPLOAD_FILE,
                    on_click=seleccionar_imagen,
                ),
                ft.Text(
                    "Si no cargás una foto, la tienda mostrará una imagen ilustrativa. "
                    "Los productos sin stock no aparecen en el catálogo.",
                    size=11, color=N.GREY_500,
                ),
            ], tight=True, spacing=12, scroll=ft.ScrollMode.AUTO),
        ),
        actions=[
            ft.TextButton("Cancelar", on_click=lambda e: cerrar_dialogo(page)),
            ft.FilledButton("Guardar", icon=ft.Icons.SAVE, on_click=guardar),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    return dialog

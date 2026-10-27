"""Escáner de QR y códigos de barras con la cámara del celular.

Usa el control nativo ``flet_camera.Camera`` (Android, iOS y web) y decodifica
los cuadros con ``zxing-cpp``. También permite subir una foto como alternativa
cuando el navegador no habilita la cámara (por ejemplo, HTTP en la LAN).
"""
from __future__ import annotations

import asyncio
import io
import logging
import time
from pathlib import Path

import flet as ft
from ui.paleta import N

from ui.helpers import cerrar_dialogo, snack


def camara_disponible(page: ft.Page) -> bool:
    """Indica si la plataforma soporta el control Camera de Flet."""
    if page.web:
        return True
    return page.platform in (ft.PagePlatform.ANDROID, ft.PagePlatform.IOS)


def _decodificar(data: bytes) -> str | None:
    """Devuelve el texto del primer QR/código encontrado en la imagen."""
    if not data:
        return None
    try:
        import zxingcpp
        from PIL import Image

        imagen = Image.open(io.BytesIO(bytes(data)))
        resultado = zxingcpp.read_barcode(imagen)
        if resultado is None:
            return None
        texto = (resultado.text or "").strip()
        return texto or None
    except Exception as ex:  # noqa: BLE001
        logging.getLogger(__name__).debug("No se pudo decodificar imagen: %s", ex)
        return None


def _url_insegura(page: ft.Page) -> bool:
    url = (page.url or "").lower()
    if not url.startswith("http://"):
        return False
    host = url.split("://", 1)[1].split("/", 1)[0].split(":", 1)[0]
    return host not in ("localhost", "127.0.0.1", "::1")


def abrir_escaner_qr(page: ft.Page, on_codigo) -> None:
    """Abre el modal de escaneo y entrega el código detectado a ``on_codigo``."""
    try:
        import flet_camera as fc
    except Exception as ex:  # noqa: BLE001
        logging.getLogger(__name__).warning("flet-camera no disponible: %s", ex)
        snack(page, "El escáner con cámara no está instalado.", ok=False)
        return

    estado = {
        "cerrada": False,
        "inicializada": False,
        "streaming": False,
        "procesando": False,
        "ultimo_intento": 0.0,
        "capturando": False,
    }

    camara = fc.Camera(
        preview_enabled=True,
        expand=True,
        content=ft.Container(
            content=ft.Container(
                width=190,
                height=190,
                border=ft.Border.all(2, ft.Colors.WHITE_70),
                border_radius=12,
            ),
            alignment=ft.Alignment.CENTER,
        ),
    )
    estado_txt = ft.Text("Preparando cámara…", size=12, color=N.GREY_300)
    detalle_txt = ft.Text(
        "Apuntá al QR o código de barras y mantenelo dentro del recuadro.",
        size=11, color=N.GREY_500,
    )
    aviso_http = ft.Text(
        "Para usar la cámara en el celular abrí esta página con HTTPS. "
        "Si estás en HTTP, usá «Subir foto».",
        size=10, color=N.AMBER_300, visible=_url_insegura(page),
    )
    capturar_btn = ft.FilledTonalButton(
        "CAPTURAR", icon=ft.Icons.CAMERA_ALT, disabled=True,
    )
    foto_btn = ft.OutlinedButton(
        "SUBIR FOTO", icon=ft.Icons.PHOTO_LIBRARY,
    )
    cerrar_btn = ft.TextButton("CERRAR", icon=ft.Icons.CLOSE)

    def _actualizar_estado(texto: str) -> None:
        estado_txt.value = texto
        try:
            page.update()
        except Exception:
            pass

    async def _detener() -> None:
        if estado["streaming"]:
            try:
                await camara.stop_image_stream()
            except Exception:
                pass
            estado["streaming"] = False
        if estado["inicializada"]:
            try:
                await camara.pause_preview()
            except Exception:
                pass
        estado["inicializada"] = False

    async def _usar_codigo(codigo: str) -> None:
        if estado["cerrada"]:
            return
        estado["cerrada"] = True
        _actualizar_estado(f"Código detectado: {codigo}")
        await _detener()
        cerrar_dialogo(page)
        on_codigo(codigo)

    async def _pedir_permiso() -> bool:
        if page.web:
            return True
        try:
            from flet_permission_handler import (
                Permission,
                PermissionHandler,
                PermissionStatus,
            )

            handler = PermissionHandler()
            resultado = await handler.request(Permission.CAMERA)
            if resultado in (
                PermissionStatus.GRANTED,
                PermissionStatus.LIMITED,
                PermissionStatus.PROVISIONAL,
            ):
                return True
            _actualizar_estado(
                "Permiso de cámara denegado. Habilitalo en los ajustes del "
                "teléfono o usá «Subir foto»."
            )
            return False
        except Exception as ex:  # noqa: BLE001
            logging.getLogger(__name__).warning("Permiso de cámara: %s", ex)
            return True

    async def _iniciar() -> None:
        if estado["cerrada"]:
            return
        _actualizar_estado("Solicitando permiso de cámara…")
        if not await _pedir_permiso():
            return
        if estado["cerrada"]:
            return

        _actualizar_estado("Buscando cámara…")
        try:
            camaras = await camara.get_available_cameras()
        except Exception as ex:  # noqa: BLE001
            logging.getLogger(__name__).warning("Cámaras disponibles: %s", ex)
            _actualizar_estado(
                "No se pudo acceder a la cámara. Revisá los permisos del "
                "navegador o usá «Subir foto»."
            )
            return

        if estado["cerrada"]:
            return
        if not camaras:
            _actualizar_estado(
                "No se encontró ninguna cámara. Usá «Subir foto» como alternativa."
            )
            return

        elegida = next(
            (c for c in camaras
             if c.lens_direction == fc.CameraLensDirection.BACK),
            camaras[0],
        )
        _actualizar_estado("Iniciando cámara…")
        try:
            await camara.initialize(
                description=elegida,
                resolution_preset=fc.ResolutionPreset.MEDIUM,
                enable_audio=False,
                fps=10,
                image_format_group=fc.ImageFormatGroup.JPEG,
            )
        except Exception as ex:  # noqa: BLE001
            logging.getLogger(__name__).warning("Inicializar cámara: %s", ex)
            _actualizar_estado(
                "No se pudo iniciar la cámara. En HTTP el navegador puede "
                "bloquearla; probá con HTTPS o usá «Subir foto»."
            )
            return

        estado["inicializada"] = True
        if estado["cerrada"]:
            await _detener()
            return

        capturar_btn.disabled = False
        _actualizar_estado("Cámara lista. Apuntá al QR o código de barras.")
        try:
            streaming = await camara.supports_image_streaming()
        except Exception:
            streaming = False
        if streaming and not estado["cerrada"]:
            try:
                await camara.start_image_stream()
                estado["streaming"] = True
                if estado["cerrada"]:
                    await _detener()
                    return
                _actualizar_estado(
                    "Escaneando… mantené el QR dentro del recuadro."
                )
            except Exception as ex:  # noqa: BLE001
                logging.getLogger(__name__).warning("Stream de cámara: %s", ex)
                _actualizar_estado(
                    "Cámara lista. Tocá «Capturar» para leer el código."
                )
        elif not estado["cerrada"]:
            _actualizar_estado(
                "Cámara lista. Tocá «Capturar» para leer el código."
            )

    async def _al_stream(e) -> None:
        if estado["cerrada"] or estado["procesando"] or not e.bytes:
            return
        ahora = time.monotonic()
        if ahora - estado["ultimo_intento"] < 0.4:
            return
        estado["ultimo_intento"] = ahora
        estado["procesando"] = True
        try:
            codigo = await asyncio.to_thread(_decodificar, e.bytes)
        finally:
            estado["procesando"] = False
        if codigo:
            await _usar_codigo(codigo)

    async def _capturar(_e=None) -> None:
        if estado["cerrada"] or estado["capturando"]:
            return
        if not estado["inicializada"]:
            _actualizar_estado("La cámara todavía no está lista.")
            return
        estado["capturando"] = True
        capturar_btn.disabled = True
        _actualizar_estado("Capturando imagen…")
        try:
            data = await camara.take_picture()
            codigo = await asyncio.to_thread(_decodificar, data)
            if codigo:
                await _usar_codigo(codigo)
            else:
                _actualizar_estado(
                    "No se detectó ningún código. Acercá la cámara y probá de nuevo."
                )
        except Exception as ex:  # noqa: BLE001
            logging.getLogger(__name__).warning("Capturar cámara: %s", ex)
            _actualizar_estado("No se pudo capturar la imagen. Probá de nuevo.")
        finally:
            estado["capturando"] = False
            capturar_btn.disabled = estado["cerrada"]
            try:
                page.update()
            except Exception:
                pass

    async def _subir_foto(_e=None) -> None:
        if estado["cerrada"]:
            return
        try:
            picker = ft.FilePicker()
            archivos = await picker.pick_files(
                dialog_title="Elegí una foto del QR",
                file_type=ft.FilePickerFileType.IMAGE,
                allow_multiple=False,
                with_data=True,
            )
        except Exception as ex:  # noqa: BLE001
            logging.getLogger(__name__).warning("Seleccionar foto: %s", ex)
            _actualizar_estado("No se pudo abrir el selector de fotos.")
            return
        if not archivos or estado["cerrada"]:
            return
        archivo = archivos[0]
        data = archivo.bytes
        if not data and archivo.path:
            try:
                data = await asyncio.to_thread(Path(archivo.path).read_bytes)
            except OSError:
                data = None
        if not data:
            _actualizar_estado("No se pudo leer la imagen seleccionada.")
            return
        _actualizar_estado("Leyendo el código de la foto…")
        codigo = await asyncio.to_thread(_decodificar, data)
        if codigo:
            await _usar_codigo(codigo)
        else:
            _actualizar_estado(
                "No se detectó ningún código en la foto. Probá con otra imagen."
            )

    async def _cerrar(_e=None) -> None:
        estado["cerrada"] = True
        await _detener()
        cerrar_dialogo(page)

    def _al_descartar(_e=None) -> None:
        estado["cerrada"] = True
        try:
            page.run_task(_detener)
        except Exception:
            pass

    def _estado_camara(e) -> None:
        if getattr(e, "has_error", False):
            _actualizar_estado(
                f"Error de cámara: {e.error_description or 'desconocido'}"
            )

    camara.on_stream_image = _al_stream
    camara.on_state_change = _estado_camara
    capturar_btn.on_click = _capturar
    foto_btn.on_click = _subir_foto
    cerrar_btn.on_click = _cerrar

    dialogo = ft.AlertDialog(
        modal=True,
        title=ft.Row([
            ft.Icon(ft.Icons.QR_CODE_SCANNER, color=N.CYAN_300),
            ft.Text("Escanear con cámara", size=16, weight=ft.FontWeight.BOLD),
        ], spacing=10),
        content=ft.Container(
            width=380,
            content=ft.Column([
                ft.Container(
                    height=300,
                    bgcolor=N.BLACK,
                    border_radius=8,
                    clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                    content=camara,
                ),
                estado_txt,
                detalle_txt,
                aviso_http,
            ], spacing=8, tight=True),
        ),
        actions=[foto_btn, capturar_btn, cerrar_btn],
        on_dismiss=_al_descartar,
    )

    try:
        page.show_dialog(dialogo)
    except Exception:
        page.overlay.append(dialogo)
        dialogo.open = True
        page.update()
    page.run_task(_iniciar)

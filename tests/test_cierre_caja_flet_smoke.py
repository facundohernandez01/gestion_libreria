"""Smoke real de Flet 1.0.4: construir y cerrar el modal sin abrir desktop."""
import flet as ft

from componente_cerrar_caja import CerrarCajaModal


class DummyPage:
    width = 1200
    height = 900

    def __init__(self):
        self.updated = 0
        self.dialogs = []

    def update(self):
        self.updated += 1

    def run_thread(self, fn, *args):
        # Para el smoke, el trabajo termina sin esperar un event loop.
        return fn(*args)

    def show_dialog(self, control):
        self.dialogs.append(control)


class DummyDb:
    def __init__(self):
        self.closed = False
        self.movimientos = 0

    def obtener_resumen_caja(self, caja_id):
        return {
            "caja_id": caja_id, "fecha_apertura": "2026-11-25 08:00",
            "importe_apertura": 100.0, "ventas_efectivo": 20.0,
            "ventas_otros_medios": 30.0, "total_ventas": 50.0,
            "total_gastos": 5.0, "efectivo_esperado": 115.0,
            "cantidad_ventas": 2, "cobros_pendientes": 0,
            "gastos": [{"concepto": "Transporte", "monto": 5.0}],
            "ventas_por_medio": [
                {"metodo_pago": "efectivo", "total": 20.0},
                {"metodo_pago": "mercadopago_qr", "total": 30.0},
            ],
        }

    def cerrar_caja_arqueo(self, caja_id, importe_contado, observaciones="", snapshot=None):
        assert caja_id == 2
        assert importe_contado == 115.0
        assert snapshot["efectivo_esperado"] == 115.0
        self.closed = True
        return {"ok": True, "diferencia_arqueo": 0.0}


def _walk(control):
    yield control
    for name in ("content", "controls", "actions"):
        obj = getattr(control, name, None)
        if isinstance(obj, (list, tuple)):
            for child in obj:
                yield from _walk(child)
        elif isinstance(obj, ft.Control):
            yield from _walk(obj)


def test_modal_flet_104_se_crea_calcula_y_cierra():
    db, page, calls = DummyDb(), DummyPage(), []
    modal = CerrarCajaModal(db, 2, lambda: calls.append("cerrada"), page)
    assert isinstance(modal, ft.AlertDialog)
    assert modal.open
    campos = [x for x in _walk(modal) if isinstance(x, ft.TextField)]
    contados = [x for x in campos if x.label == "Efectivo contado en el cajón"]
    assert len(contados) == 1
    contado = contados[0]
    contado.value = "115,00"
    contado.on_change(None)
    boton = modal.actions[-1]
    assert boton.disabled is False
    boton.on_click(None)
    assert db.closed
    assert calls == ["cerrada"]
    assert modal.open is False

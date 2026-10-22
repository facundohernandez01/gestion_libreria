"""Compatibilidad hacia atrás: delega en services.mercadopago_service.

NO contiene secretos. Los tokens salen de .env (core.settings) o tabla config.
Se mantiene para no romper `from mp_qr import crear_orden, verificar_estado`.
Código nuevo: importar desde services.mercadopago_service.
"""
from services.mercadopago_service import mp_service

ultima_referencia = None


def _sync_ref():
    global ultima_referencia
    ultima_referencia = mp_service._ultima_referencia


def crear_orden(external_pos_id, external_store_id, monto, cb=None):
    ok = mp_service.crear_orden(monto, cb=cb, pos_ext=external_pos_id, store_ext=external_store_id)
    _sync_ref()
    return ok


def verificar_estado(external_pos_id, timeout=300, intervalo=5, cb=None, cancelar=None):
    return mp_service.verificar_estado(cb=cb, cancelar=cancelar, pos_ext=external_pos_id,
                                       timeout=timeout, intervalo=intervalo)


def consultar_ultimo_pago_por_referencia(cb=None):
    return mp_service.consultar_ultimo_pago(cb=cb)


# Propiedades legacy leídas bajo demanda (no import-time DB con token quemado)
def __getattr__(name):
    if name in ("ACCESS_TOKEN", "USER_ID"):
        token, uid, _, _ = mp_service.credenciales()
        return token if name == "ACCESS_TOKEN" else uid
    raise AttributeError(name)

"""Pruebas HTTP simuladas: nunca se contacta a Mercado Pago."""
from types import SimpleNamespace

import pytest

from services import mercadopago_service as mp


def _response(status, data=None):
    return SimpleNamespace(
        status_code=status,
        json=lambda: data,
        text="respuesta simulada",
    )


@pytest.fixture
def service(monkeypatch):
    svc = mp.MercadoPagoService()
    monkeypatch.setattr(
        svc, "credenciales",
        lambda: ("TEST_TOKEN_INUTIL", "12345", "STORE_TEST", "POS_TEST"),
    )
    return svc


def test_cierre_referencia_correcta(monkeypatch, service):
    llamadas = []
    def get(url, **kwargs):
        llamadas.append(("get", url, kwargs))
        return _response(200, {"external_reference": "checkout-1"})
    def delete(url, **kwargs):
        llamadas.append(("delete", url, kwargs))
        return _response(204)
    monkeypatch.setattr(mp.requests, "get", get)
    monkeypatch.setattr(mp.requests, "delete", delete)
    assert service.cerrar_orden_referencia("checkout-1", pos_ext="POS_TEST")["estado"] == "closed"
    assert [x[0] for x in llamadas] == ["get", "delete"]
    assert all("/collectors/12345/pos/POS_TEST/orders" in x[1] for x in llamadas)
    assert all("/stores/" not in x[1] for x in llamadas)
    assert all("TEST_TOKEN" not in x[1] for x in llamadas)


@pytest.mark.parametrize("respuesta,esperado", [
    (_response(404), "not_active"),
    (_response(500), "uncertain"),
    (_response(200, {"external_reference": "otra-orden"}), "different_order"),
    (_response(200, {"external_reference": None}), "uncertain"),
    (_response(200, []), "uncertain"),
])
def test_no_borra_orden_ajena_o_desconocida(monkeypatch, service, respuesta, esperado):
    monkeypatch.setattr(mp.requests, "get", lambda *args, **kwargs: respuesta)
    def delete(*args, **kwargs):
        raise AssertionError("Nunca se debe borrar esta orden")
    monkeypatch.setattr(mp.requests, "delete", delete)
    assert service.cerrar_orden_referencia("checkout-1", "POS_TEST")["estado"] == esperado


def test_delete_404_no_confirma_cierre(monkeypatch, service):
    monkeypatch.setattr(
        mp.requests, "get",
        lambda *args, **kwargs: _response(200, {"external_reference": "checkout-1"}),
    )
    monkeypatch.setattr(
        mp.requests, "delete", lambda *args, **kwargs: _response(404),
    )
    assert service.cerrar_orden_referencia("checkout-1", "POS_TEST")["estado"] == "uncertain"


def test_error_red_no_confirma_cierre(monkeypatch, service):
    def failing_get(*args, **kwargs):
        raise mp.requests.ConnectionError("sin red")
    monkeypatch.setattr(mp.requests, "get", failing_get)
    monkeypatch.setattr(
        mp.requests, "delete",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("DELETE inesperado")),
    )
    assert service.cerrar_orden_referencia("checkout-1", "POS_TEST")["estado"] == "uncertain"


@pytest.mark.parametrize("payments,expected", [
    ([{"external_reference": "otro", "status": "approved", "transaction_amount": 100}], "uncertain"),
    ([{"external_reference": "checkout-1", "status": "approved", "transaction_amount": 99}], "uncertain"),
    ([{"external_reference": "checkout-1", "status": "pending", "transaction_amount": 100}], "uncertain"),
    ([], "uncertain"),
    ([{"external_reference": "checkout-1", "status": "approved", "transaction_amount": 100}], "approved"),
])
def test_pago_aprobado_solo_con_referencia_y_monto(monkeypatch, service, payments, expected):
    monkeypatch.setattr(
        mp.requests, "get",
        lambda *args, **kwargs: _response(200, {"results": payments}),
    )
    assert service.verificar_pago_referencia("checkout-1", 100)["estado"] == expected

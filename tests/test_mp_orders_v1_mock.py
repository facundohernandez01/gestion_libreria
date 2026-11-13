"""Contrato aislado de Orders API v1 usando respuestas falsas y sin credenciales."""
from types import SimpleNamespace

import pytest
import requests

from services.mp_orders_v1_client import MercadoPagoOrdersV1


def response(code, data):
    return SimpleNamespace(status_code=code, json=lambda: data)


class FakeHTTP:
    def __init__(self, posts=(), gets=()):
        self.posts = list(posts)
        self.gets = list(gets)
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        value = self.posts.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        value = self.gets.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


ITEMS = [{"descripcion": "Gaseosa", "cantidad": 2, "precio_unitario": 50}]
REFERENCE = "checkout_1"
ORDER_ID = "ORD01ABCDE"


def order(status, detail):
    return {
        "id": ORDER_ID, "external_reference": REFERENCE,
        "total_amount": "100.00", "status": status, "status_detail": detail,
        "transactions": {"payments": [{
            "id": "PAY01", "amount": "100.00",
            "status": "processed" if status == "processed" else status,
            "status_detail": "accredited" if status == "processed" else detail,
        }]},
    }


def client(http):
    return MercadoPagoOrdersV1(token_provider=lambda: "TOKEN_FALSO", http=http)


def test_crear_orden_con_referencia_importe_e_idempotencia():
    fake = FakeHTTP(posts=[
        response(201, order("created", "created")),
        response(201, order("created", "created")),
    ])
    api = client(fake)
    assert api.crear(REFERENCE, "POS_1", ITEMS, 100)["order_id"] == ORDER_ID
    assert api.crear(REFERENCE, "POS_1", ITEMS, 100)["estado"] == "created"
    first, second = [entry[2] for entry in fake.calls]
    assert first["headers"]["X-Idempotency-Key"] == second["headers"]["X-Idempotency-Key"]
    assert first["headers"]["Authorization"] == "Bearer TOKEN_FALSO"
    assert first["json"]["external_reference"] == REFERENCE
    assert first["json"]["config"]["qr"]["external_pos_id"] == "POS_1"
    assert first["json"]["transactions"]["payments"][0]["amount"] == "100.00"
    assert "TOKEN_FALSO" not in fake.calls[0][1]


def test_no_crear_orden_si_importe_no_coincide():
    fake = FakeHTTP()
    with pytest.raises(ValueError):
        client(fake).crear(REFERENCE, "POS_1", ITEMS, 99)
    assert fake.calls == []


def test_respuesta_de_creacion_con_referencia_distinta_es_incierta():
    fake = FakeHTTP(posts=[response(201, {**order("created", "created"), "external_reference": "OTRA"})])
    assert client(fake).crear(REFERENCE, "POS_1", ITEMS, 100)["estado"] == "uncertain"


@pytest.mark.parametrize("status,detail,result", [
    ("processed", "processed", "approved"),
    ("canceled", "canceled", "cancelled"),
    ("created", "created", "pending"),
    ("expired", "expired", "expired"),
])
def test_consultar_orden_y_estado(status, detail, result):
    fake = FakeHTTP(gets=[response(200, order(status, detail))])
    assert client(fake).consultar(ORDER_ID, REFERENCE, 100)["estado"] == result


def test_consulta_no_aprueba_otra_referencia_o_importe():
    for data in (
        {**order("processed", "processed"), "external_reference": "OTRO"},
        {**order("processed", "processed"), "total_amount": "10.00"},
    ):
        fake = FakeHTTP(gets=[response(200, data)])
        assert client(fake).consultar(ORDER_ID, REFERENCE, 100)["estado"] == "uncertain"


def test_cancelacion_409_se_concilia_como_pago_aprobado():
    fake = FakeHTTP(
        posts=[response(409, {"error": "already_processed"})],
        gets=[response(200, order("processed", "processed"))],
    )
    assert client(fake).cancelar(ORDER_ID, REFERENCE, 100)["estado"] == "approved"
    assert fake.calls[0][2]["headers"]["X-Idempotency-Key"]
    assert fake.calls[0][1].endswith("/cancel")
    assert fake.calls[1][0] == "GET"


def test_cancelacion_confirmada_autoriza_estado_cancelled():
    fake = FakeHTTP(
        posts=[response(200, order("canceled", "canceled"))],
        gets=[response(200, order("canceled", "canceled"))],
    )
    assert client(fake).cancelar(ORDER_ID, REFERENCE, 100)["estado"] == "cancelled"


def test_timeout_de_cancelacion_solo_libera_si_get_confirma_canceled():
    fake = FakeHTTP(
        posts=[requests.Timeout("timeout")],
        gets=[response(200, order("canceled", "canceled"))],
    )
    assert client(fake).cancelar(ORDER_ID, REFERENCE, 100)["estado"] == "cancelled"
    fake = FakeHTTP(
        posts=[requests.Timeout("timeout")],
        gets=[requests.Timeout("timeout")],
    )
    assert client(fake).cancelar(ORDER_ID, REFERENCE, 100)["estado"] == "uncertain"

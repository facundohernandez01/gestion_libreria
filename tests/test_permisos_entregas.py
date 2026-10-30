from core.permisos import permisos_entregas, tiene, normalizar


def test_entregas_role_least_privilege():
    p = permisos_entregas()
    assert tiene(p, "ENTREGAS_INTRASHOP")
    assert not tiene(p, "VENTAS")
    assert not tiene(p, "CAJA")
    assert not tiene(p, "CONFIGURACION")


def test_old_roles_do_not_gain_fulfillment_permission():
    assert not normalizar('{"VENTAS": true}')["ENTREGAS_INTRASHOP"]

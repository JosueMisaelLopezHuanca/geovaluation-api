from app.domain.avaluos.rules import (
    calcular_impuesto,
    calcular_valor_construccion,
    calcular_valor_terreno,
    factor_pendiente_desde_dn,
    factor_riesgo_desde_dn,
)


def test_factor_pendiente_desde_dn():
    assert factor_pendiente_desde_dn(1) == 1.0
    assert factor_pendiente_desde_dn(2) == 0.9
    assert factor_pendiente_desde_dn(3) == 0.8


def test_factor_riesgo_desde_dn_has_floor():
    assert factor_riesgo_desde_dn(1) == 0.9
    assert factor_riesgo_desde_dn(5) == 0.7


def test_calculo_terreno_e_impuesto():
    valor_terreno, valor_unitario = calcular_valor_terreno(
        superficie_terreno=280,
        valor_base_m2=472.1429,
        factor_servicios=1.0,
        factor_pendiente=0.8,
        factor_riesgo=1.0,
    )

    assert valor_terreno == 105760.01
    assert valor_unitario == 377.7143
    assert calcular_impuesto(valor_terreno, 0.0035) == 370.16


def test_calculo_construccion():
    valor_construccion, valor_unitario = calcular_valor_construccion(
        superficie_construida=120,
        valor_tipologia_m2=1444,
        factor_depreciacion=0.85,
    )

    assert valor_construccion == 147288.0
    assert valor_unitario == 1227.4

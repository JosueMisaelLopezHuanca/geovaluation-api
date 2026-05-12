from app.modules.appraisal_engine.rules import (
    calculate_building_block_value,
    calculate_land_value,
    calculate_tax,
    choose_surface,
    compute_service_score,
)


def test_compute_service_score_ignores_non_official_services():
    score, services = compute_service_score(
        [
            "AGUA POTABLE",
            "ALCANTARILLADO",
            "GAS DOMICILIARIO",
            "INTERNET",
            "TELEFONO",
        ]
    )

    assert score == 0.6
    assert services == ["AGUA POTABLE", "ALCANTARILLADO", "TELEFONO"]


def test_choose_surface_prefers_manual_override():
    surface, source = choose_surface(122.67, 140.0, 250.0)

    assert surface == 250.0
    assert source == "superficie_manual"


def test_land_value_has_no_risk_factor():
    valor_terreno, valor_unitario = calculate_land_value(
        superficie_calculo=250.0,
        valor_unitario=1271.0,
        puntaje_servicios=0.8,
        factor_pendiente=1.0,
    )

    assert valor_unitario == 1016.8
    assert valor_terreno == 254200.0


def test_building_block_and_tax():
    assert calculate_building_block_value(45, 3471, 0.975) == 152290.12
    assert calculate_tax(662789.12, 0.0035) == 2319.76

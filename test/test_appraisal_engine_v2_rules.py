from app.modules.appraisal_engine.rules import (
    calculate_building_block_value,
    calculate_land_value,
    calculate_progressive_tax,
    calculate_tax,
    choose_surface,
    compute_slope_class_factor,
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


def test_compute_service_score_applies_official_minimum_without_confirmed_services():
    score, services = compute_service_score(["INTERNET"])

    assert score == 0.2
    assert services == []


def test_choose_surface_prefers_manual_override():
    surface, source = choose_surface(122.67, 140.0, 250.0)

    assert surface == 250.0
    assert source == "superficie_manual"


def test_slope_class_factor_maps_gis_dn_categories():
    assert compute_slope_class_factor(None) == 1.0
    assert compute_slope_class_factor(1) == 1.0
    assert compute_slope_class_factor(2) == 0.9
    assert compute_slope_class_factor(3) == 0.8


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


def test_impbi_progressive_scale_uses_fixed_quota_and_excess_rate():
    assert calculate_progressive_tax(1399668, 0, 0.00115369, 0) == 1614.78
    assert calculate_progressive_tax(1500000, 1615, 0.00173054, 1399668) == 1788.63

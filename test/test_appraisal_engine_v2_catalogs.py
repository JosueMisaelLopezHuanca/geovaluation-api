from test.conftest import create_client


def test_public_catalogs_endpoint_returns_basic_options():
    client = create_client()
    response = client.get("/api/v2/catalogos/publicos")

    assert response.status_code == 200
    body = response.json()
    assert body["tipo_via"][0]["value"] == "ASFALTO"
    road_values = {option["value"] for option in body["tipo_via"]}
    assert {"CEMENTO", "LOSETA", "PIEDRA", "RIPIO"} <= road_values
    assert "AVENIDA PRINCIPAL" not in road_values
    assert any(option["value"] == "RESIDENCIAL" for option in body["uso_suelo"])
    assert any(option["value"] == "BUENO" for option in body["estado_conservacion"])
    assert not any(option["value"] == "MUY BUENO" for option in body["estado_conservacion"])


def test_methodology_exposes_verified_fiscal_source_and_service_minimum():
    client = create_client()
    response = client.get("/api/v2/metodologia")

    assert response.status_code == 200
    body = response.json()
    assert body["normativa_fuente"]["gestion_tributaria"] == 2023
    assert body["normativa_fuente"]["estado"] == "REFERENCIA_OFICIAL_VERIFICADA"
    assert body["servicios_minimo"] == 0.2
    assert body["motores"]["FISCAL"]["formula_construccion"] == "superficie_construida x tipologia x antiguedad"
    assert "factor_ubicacion_ph" in body["motores"]["FISCAL"]["formula_propiedad_horizontal"]
    assert body["impbi"]["vigencia_confirmada_gestion_calculo"] is False
    assert "no oficial" in body["motores"]["COMERCIAL"]["descripcion"]

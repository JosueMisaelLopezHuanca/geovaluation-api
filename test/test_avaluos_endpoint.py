from test.conftest import create_client


def _admin_headers(client):
    response = client.post(
        "/api/v2/auth/login",
        json={"user": "admin", "password": "change-this-local-password"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_avaluos_health_reports_ok():
    client = create_client()
    response = client.get("/api/v1/avaluos/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def _fake_obtener_contexto_avaluo(db, id_predio):
    return {
        "id_predio": id_predio,
        "superficie_terreno": 280.0,
        "pendiente_grados": 16.0,
        "id_zona_valor": "33333333-3333-3333-3333-333333333333",
        "id_material_via": "44444444-4444-4444-4444-444444444444",
        "material_via_nombre": "LOSETA",
        "material_via_orden": 23,
        "zona_valor_nombre": "Zona tributaria 2-30 a 2-34",
        "zona_valor_macro_zona": 2,
        "zona_valor_subzona_inicio": 30,
        "zona_valor_subzona_fin": 34,
        "riesgo_codigo": 255,
        "riesgo_grado": "MUY ALTO",
        "pendiente_codigo": 2,
        "pendiente_area_m2": 280.0,
        "pendiente_cobertura_pct": 100.0,
        "riesgo_area_m2": 280.0,
        "riesgo_cobertura_pct": 100.0,
        "servicios": ["AGUA POTABLE", "ENERGIA ELECTRICA"],
        "construcciones_registradas": 1,
        "superficie_construida_total": 120.0,
        "geojson": "{\"type\":\"Polygon\",\"coordinates\":[]}",
        "columnas_origen": {
            "riesgo_geom_col": "geometry",
            "riesgo_code_col": "GRIDCODE",
            "riesgo_grade_col": "GRADO",
            "pendiente_geom_col": "geometry",
            "pendiente_code_col": "DN",
        },
    }


def test_avaluos_contexto_returns_real_source_mapping(monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.endpoints.avaluos.obtener_contexto_avaluo",
        _fake_obtener_contexto_avaluo,
    )

    client = create_client()
    response = client.get(
        "/api/v1/avaluos/contexto/22222222-2222-2222-2222-222222222222"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["riesgo_codigo"] == 255
    assert body["riesgo_grado"] == "MUY ALTO"
    assert body["pendiente_codigo"] == 2
    assert body["material_via_nombre"] == "LOSETA"
    assert body["zona_valor_macro_zona"] == 2
    assert body["servicios"] == ["AGUA POTABLE", "ENERGIA ELECTRICA"]
    assert body["columnas_origen"]["riesgo_code_col"] == "GRIDCODE"


async def _fake_obtener_estadisticas_contexto(db):
    return {
        "total_predios": 118949,
        "con_pendiente": 118931,
        "con_riesgo": 116501,
        "pendiente_distribucion": [
            {"codigo": 1, "cantidad": 50000},
            {"codigo": 2, "cantidad": 30000},
            {"codigo": 3, "cantidad": 38931},
        ],
        "riesgo_distribucion": [
            {"codigo": 102, "grado": "MODERADO", "cantidad": 1000},
            {"codigo": 153, "grado": "ALTO", "cantidad": 2000},
        ],
    }


def test_avaluos_contexto_estadisticas_returns_summary(monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.endpoints.avaluos.obtener_estadisticas_contexto",
        _fake_obtener_estadisticas_contexto,
    )

    client = create_client()
    response = client.get("/api/v1/avaluos/contexto-estadisticas")

    assert response.status_code == 200
    body = response.json()
    assert body["total_predios"] == 118949
    assert body["con_pendiente"] == 118931
    assert body["pendiente_distribucion"][0]["codigo"] == 1


async def _fake_obtener_estadisticas_cobertura(db):
    return {
        "total_predios": 118949,
        "con_contexto_pendiente": 118931,
        "con_material_via": 118949,
        "con_zona_valor": 90595,
        "con_servicios": 117000,
        "con_construccion": 12,
        "listos_avaluo_terreno": 90588,
        "listos_avaluo_integral": 8,
    }


def test_avaluos_cobertura_estadisticas_returns_summary(monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.endpoints.avaluos.obtener_estadisticas_cobertura",
        _fake_obtener_estadisticas_cobertura,
    )

    client = create_client()
    response = client.get("/api/v1/avaluos/cobertura-estadisticas")

    assert response.status_code == 200
    body = response.json()
    assert body["con_zona_valor"] == 90595
    assert body["listos_avaluo_integral"] == 8


async def _fake_listar_avaluos(db, limit):
    return [
        {
            "id_avaluo": "11111111-1111-1111-1111-111111111111",
            "id_predio": "22222222-2222-2222-2222-222222222222",
            "codigo_catastral": "006114800010000",
            "valor_total": 1268674.0,
            "impuesto_estimado": 4440.359,
            "fecha_calculo": "2026-04-23T18:00:00Z",
            "nombre_usuario": "admin",
            "estado": "PENDIENTE",
            "gestion_anio": 2026,
        }
    ]


def test_avaluos_list_returns_recent_items(monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.endpoints.avaluos.listar_avaluos",
        _fake_listar_avaluos,
    )

    client = create_client()
    response = client.get("/api/v1/avaluos/?limit=10", headers=_admin_headers(client))

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["codigo_catastral"] == "006114800010000"


async def _fake_obtener_avaluo_por_id(db, id_avaluo):
    return await _fake_calcular_y_guardar_avaluo(
        db,
        type(
            "Payload",
            (),
            {"id_predio": "22222222-2222-2222-2222-222222222222"},
        )(),
    )


def test_avaluos_detail_returns_saved_item(monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.endpoints.avaluos.obtener_avaluo_por_id",
        _fake_obtener_avaluo_por_id,
    )

    client = create_client()
    response = client.get(
        "/api/v1/avaluos/11111111-1111-1111-1111-111111111111",
        headers=_admin_headers(client),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id_avaluo"] == "11111111-1111-1111-1111-111111111111"
    assert body["valor_total"] == 1268674.0


async def _fake_calcular_y_guardar_avaluo(db, avaluo):
    return {
        "id_avaluo": "11111111-1111-1111-1111-111111111111",
        "id_predio": str(avaluo.id_predio),
        "valor_terreno": 105760.0,
        "valor_construccion": 1162914.0,
        "valor_total": 1268674.0,
        "base_imponible": 1268674.0,
        "impuesto_estimado": 4440.359,
        "fecha_calculo": "2026-04-23T18:00:00Z",
        "superficie_terreno": 280.0,
        "pendiente_grados": 16.0,
        "factor_pendiente": 0.8,
        "factor_riesgo": 1.0,
        "factor_servicios": 1.0,
        "valor_unitario_aplicado": 377.7143,
        "valor_unitario_construccion": 1227.4,
        "factor_depreciacion": 0.8,
        "construcciones_procesadas": 2,
        "riesgo_dn": 255,
        "pendiente_dn": 2,
        "geojson": "{\"type\":\"Polygon\",\"coordinates\":[]}",
        "parametros_utilizados": {
            "valor_base_m2": 472.1429,
            "columnas_origen": {"riesgo_code_col": "GRIDCODE", "pendiente_code_col": "DN"},
        },
    }


def test_avaluos_post_returns_breakdown(monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.endpoints.avaluos.calcular_y_guardar_avaluo",
        _fake_calcular_y_guardar_avaluo,
    )

    client = create_client()
    response = client.post(
        "/api/v1/avaluos/",
        headers=_admin_headers(client),
        json={
            "id_predio": "22222222-2222-2222-2222-222222222222",
            "valor_base_m2": 472.1429,
            "alicuota_impuesto": 0.0035,
            "gestion_anio": 2026,
            "nombre_usuario": "admin",
            "factor_servicios": 1.0,
            "ficha_tecnica": {
                "material_via_aplicado": "ASFALTO",
                "servicios_aplicados": ["AGUA POTABLE"],
                "uso_predio": "VIVIENDA",
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["valor_terreno"] == 105760.0
    assert body["valor_construccion"] == 1162914.0
    assert body["impuesto_estimado"] == 4440.359
    assert body["factor_pendiente"] == 0.8
    assert body["construcciones_procesadas"] == 2


def test_avaluos_post_accepts_ficha_tecnica(monkeypatch):
    captured = {}

    async def _fake(db, avaluo):
        captured["ficha_tecnica"] = (
            avaluo.ficha_tecnica.model_dump() if avaluo.ficha_tecnica else None
        )
        return await _fake_calcular_y_guardar_avaluo(db, avaluo)

    monkeypatch.setattr(
        "app.api.v1.endpoints.avaluos.calcular_y_guardar_avaluo",
        _fake,
    )

    client = create_client()
    response = client.post(
        "/api/v1/avaluos/",
        headers=_admin_headers(client),
        json={
            "id_predio": "22222222-2222-2222-2222-222222222222",
            "valor_base_m2": 472.1429,
            "alicuota_impuesto": 0.0035,
            "gestion_anio": 2026,
            "nombre_usuario": "admin",
            "factor_servicios": 1.0,
            "usar_tablas_maestras": True,
            "ficha_tecnica": {
                "material_via_aplicado": "ASFALTO",
                "zona_valor_aplicada": "ZONA 1",
                "servicios_aplicados": ["AGUA POTABLE", "ENERGIA ELECTRICA"],
                "uso_predio": "VIVIENDA",
                "estado_construccion": "BUENO",
                "calidad_constructiva": "MEDIA",
                "superficie_construida_declarada": 120.5,
                "anio_construccion_referencia": 2010,
                "observaciones_tecnicas": "Verificado en campo",
            },
        },
    )

    assert response.status_code == 200
    assert captured["ficha_tecnica"]["material_via_aplicado"] == "ASFALTO"
    assert captured["ficha_tecnica"]["servicios_aplicados"] == [
        "AGUA POTABLE",
        "ENERGIA ELECTRICA",
    ]


def test_avaluos_automatico_post_wraps_predio_id(monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.endpoints.avaluos.calcular_y_guardar_avaluo",
        _fake_calcular_y_guardar_avaluo,
    )

    client = create_client()
    response = client.post(
        "/api/v1/avaluos/automatico/22222222-2222-2222-2222-222222222222",
        headers=_admin_headers(client),
        json={
            "gestion_anio": 2026,
            "nombre_usuario": "admin",
            "valor_base_m2": 472.1429,
            "alicuota_impuesto": 0.0035,
            "factor_servicios": 1.0,
            "usar_tablas_maestras": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id_predio"] == "22222222-2222-2222-2222-222222222222"

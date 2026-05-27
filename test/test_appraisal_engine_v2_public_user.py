import pytest
from fastapi import HTTPException

from app.modules.appraisal_engine import schemas, service


def _minimal_context(*, services=None):
    return {
        "id_predio": "11111111-1111-1111-1111-111111111111",
        "superficie_gis": 100.0,
        "superficie_legal": None,
        "zona_tributaria_codigo": "1-10",
        "material_via_codigo": "ASFALTO",
        "servicios_oficiales": services or [],
    }


async def _fake_normative(db, gestion_anio):
    return {
        "normative_version_id": "normativa-test",
        "gestion_anio": gestion_anio,
        "nombre": "Normativa prueba",
        "version_codigo": "v1",
    }


def test_special_location_flags_keep_avenue_separate_from_road_material():
    assert service._resolve_special_location_flags(None) == (False, False)
    assert service._resolve_special_location_flags("ESQUINA") == (True, False)
    assert service._resolve_special_location_flags("AVENIDA") == (False, True)
    assert service._resolve_special_location_flags("ESQUINA_AVENIDA") == (True, True)


def test_public_payload_rejects_values_outside_valuation_ranges():
    with pytest.raises(ValueError):
        schemas.ManualInputPayload(pendiente_manual=91)
    with pytest.raises(ValueError):
        schemas.BuildingBlockInput(
            superficie=60,
            calidad_constructiva="MEDIA",
            anio_construccion=2020,
            depreciacion_manual=1.2,
        )
    with pytest.raises(ValueError):
        schemas.BuildingBlockInput(
            superficie=60,
            calidad_constructiva="MEDIA",
            anio_construccion=2020,
            numero_pisos=121,
        )


@pytest.mark.anyio
async def test_fiscal_building_block_uses_only_typology_and_official_age(monkeypatch):
    async def fake_tipologia(db, normative_version_id, calidad, categoria="PREDIO"):
        return {
            "tipologia_constructiva_id": "tipologia-test",
            "valor_m2": 100.0,
        }

    async def fail_matrix(db, normative_version_id, **kwargs):
        raise AssertionError("El modo fiscal no debe consultar matriz comercial.")

    async def fake_depreciation(db, normative_version_id, edad):
        return 0.8

    monkeypatch.setattr(service.repository, "resolve_tipologia_constructiva", fake_tipologia)
    monkeypatch.setattr(service.repository, "resolve_construction_matrix", fail_matrix)
    monkeypatch.setattr(service.repository, "resolve_depreciacion_factor", fake_depreciation)

    block = schemas.BuildingBlockInput(
        superficie=60,
        calidad_constructiva="MEDIA",
        anio_construccion=2020,
        estado_conservacion="MALO",
        remodelaciones="SI",
        depreciacion_manual=0.5,
        usar_depreciacion_manual=True,
    )

    result, formula = await service._appraise_building_block(
        None,
        block=block,
        normative_version_id="normativa-test",
        gestion_anio=2026,
        avaluo_tipo="FISCAL",
    )

    assert result["valor_bloque"] == 4800.0
    assert result["factor_antiguedad"] == 0.8
    assert result["factor_estado"] == 1.0
    assert result["factor_remodelacion"] == 1.0
    assert result["ajustes_comerciales_aplicados"] is False
    assert formula.simbolica == "superficie x valor_tipologia_m2 x factor_antiguedad"


@pytest.mark.anyio
async def test_commercial_building_block_rejects_missing_reference_matrix(monkeypatch):
    async def fake_tipologia(db, normative_version_id, calidad, categoria="PREDIO"):
        return {
            "tipologia_constructiva_id": "tipologia-test",
            "valor_m2": 100.0,
        }

    async def fake_matrix(db, normative_version_id, **kwargs):
        return None

    monkeypatch.setattr(service.repository, "resolve_tipologia_constructiva", fake_tipologia)
    monkeypatch.setattr(service.repository, "resolve_construction_matrix", fake_matrix)

    block = schemas.BuildingBlockInput(
        superficie=60,
        calidad_constructiva="MEDIA",
        anio_construccion=2020,
        estado_conservacion="MALO",
    )

    with pytest.raises(HTTPException) as exc_info:
        await service._appraise_building_block(
            None,
            block=block,
            normative_version_id="normativa-test",
            gestion_anio=2026,
            avaluo_tipo="COMERCIAL",
        )

    assert exc_info.value.status_code == 409
    assert "matriz constructiva referencial" in exc_info.value.detail


@pytest.mark.anyio
async def test_resolve_usuario_id_creates_public_user_when_missing(monkeypatch):
    async def fake_get_usuario_id(db, nombre_usuario):
        return None

    async def fake_ensure_public_user(db, nombre_usuario):
        return "public-user-id"

    monkeypatch.setattr(service.repository, "get_usuario_id", fake_get_usuario_id)
    monkeypatch.setattr(service.repository, "ensure_public_user", fake_ensure_public_user)

    resolved_user_id = await service._resolve_usuario_id(None, service.PUBLIC_APPRAISAL_USER)

    assert resolved_user_id == "public-user-id"


@pytest.mark.anyio
async def test_resolve_usuario_id_raises_for_unknown_non_public_user(monkeypatch):
    async def fake_get_usuario_id(db, nombre_usuario):
        return None

    monkeypatch.setattr(service.repository, "get_usuario_id", fake_get_usuario_id)

    with pytest.raises(HTTPException) as exc_info:
        await service._resolve_usuario_id(None, "tecnico_inexistente")

    assert exc_info.value.status_code == 404
    assert "tecnico_inexistente" in exc_info.value.detail


@pytest.mark.anyio
async def test_preview_does_not_provision_public_user(monkeypatch):
    class ContextReached(Exception):
        pass

    async def fake_normative(db, gestion_anio):
        return {"normative_version_id": "normativa-test"}

    async def fail_if_user_is_resolved(db, nombre_usuario):
        raise AssertionError("El preview publico no debe crear ni consultar usuarios.")

    async def stop_after_read_only_boundary(db, predio_id):
        raise ContextReached

    monkeypatch.setattr(service.repository, "get_normative_version", fake_normative)
    monkeypatch.setattr(service, "_resolve_usuario_id", fail_if_user_is_resolved)
    monkeypatch.setattr(service, "_resolve_predio_context", stop_after_read_only_boundary)

    payload = schemas.AppraisalPreviewRequest(
        predio_id="11111111-1111-1111-1111-111111111111",
        gestion_anio=2026,
        usuario="consulta_publica",
    )

    with pytest.raises(ContextReached):
        await service.preview_appraisal(None, payload)


@pytest.mark.anyio
async def test_preview_applies_normative_minimum_without_official_services(monkeypatch):
    async def fake_context(db, predio_id):
        return _minimal_context(), None, None

    async def fake_land_value(db, normative_version_id, zona_tributaria_codigo, material_via_codigo):
        return 100.0

    async def fake_impbi(db, normative_version_id, base_imponible):
        return {
            "tramo_codigo": "TRAMO_1",
            "limite_inferior": 0,
            "cuota_fija": 0,
            "alicuota_excedente": 0.00115369,
            "fuente_gestion_anio": 2023,
            "fuente_documental": "RA GAMLP/ATM No. 14/2023",
            "vigente_confirmada": False,
        }

    monkeypatch.setattr(service.repository, "get_normative_version", _fake_normative)
    monkeypatch.setattr(service, "_resolve_predio_context", fake_context)
    monkeypatch.setattr(service.repository, "get_official_land_value", fake_land_value)
    monkeypatch.setattr(service.repository, "get_impbi_bracket", fake_impbi)

    payload = schemas.AppraisalPreviewRequest(
        predio_id="11111111-1111-1111-1111-111111111111",
        gestion_anio=2026,
        usuario="consulta_publica",
    )

    result = await service.preview_appraisal(None, payload)

    assert result.valor_terreno == 2000.0
    assert result.factores_aplicados["factor_servicios"] == 0.2
    assert result.factores_aplicados["factor_servicios_minimo_aplicado"] is True


@pytest.mark.anyio
async def test_fiscal_horizontal_property_applies_location_factor_without_separate_land(monkeypatch):
    async def fake_tipologia(db, normative_version_id, calidad, categoria="PREDIO"):
        assert categoria == "PROPIEDAD_HORIZONTAL"
        return {
            "tipologia_constructiva_id": "tipologia-ph",
            "categoria": categoria,
            "valor_m2": 3471.0,
        }

    async def fake_depreciation(db, normative_version_id, edad):
        return 0.9

    async def fake_ph_factor(db, normative_version_id, zona_tributaria_codigo):
        assert zona_tributaria_codigo == "1-10"
        return 1.625

    monkeypatch.setattr(service.repository, "resolve_tipologia_constructiva", fake_tipologia)
    monkeypatch.setattr(service.repository, "resolve_depreciacion_factor", fake_depreciation)
    monkeypatch.setattr(service.repository, "get_ph_location_factor", fake_ph_factor)

    result, formula = await service._appraise_building_block(
        None,
        block=schemas.BuildingBlockInput(
            superficie=100,
            calidad_constructiva="MEDIA",
            anio_construccion=2010,
        ),
        normative_version_id="normativa-test",
        gestion_anio=2026,
        avaluo_tipo="FISCAL",
        regimen_inmueble="PROPIEDAD_HORIZONTAL",
        zona_tributaria_codigo="1-10",
    )

    assert result["valor_bloque"] == 507633.75
    assert result["factor_ubicacion_ph"] == 1.625
    assert "factor_ubicacion_ph" in formula.simbolica


@pytest.mark.anyio
async def test_preview_rejects_future_construction_year(monkeypatch):
    async def fake_context(db, predio_id):
        return _minimal_context(services=["AGUA POTABLE"]), None, None

    monkeypatch.setattr(service.repository, "get_normative_version", _fake_normative)
    monkeypatch.setattr(service, "_resolve_predio_context", fake_context)

    payload = schemas.AppraisalPreviewRequest(
        predio_id="11111111-1111-1111-1111-111111111111",
        gestion_anio=2026,
        usuario="consulta_publica",
        bloques=[
            schemas.BuildingBlockInput(
                superficie=60,
                calidad_constructiva="MEDIA",
                anio_construccion=2027,
            )
        ],
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.preview_appraisal(None, payload)

    assert exc_info.value.status_code == 422
    assert "no puede ser posterior" in exc_info.value.detail


@pytest.mark.anyio
async def test_preview_rejects_land_value_combination_without_official_table(monkeypatch):
    async def fake_context(db, predio_id):
        return _minimal_context(services=["AGUA POTABLE"]), None, None

    async def fake_land_value(db, normative_version_id, zona_tributaria_codigo, material_via_codigo):
        return None

    monkeypatch.setattr(service.repository, "get_normative_version", _fake_normative)
    monkeypatch.setattr(service, "_resolve_predio_context", fake_context)
    monkeypatch.setattr(service.repository, "get_official_land_value", fake_land_value)

    payload = schemas.AppraisalPreviewRequest(
        predio_id="11111111-1111-1111-1111-111111111111",
        gestion_anio=2026,
        usuario="consulta_publica",
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.preview_appraisal(None, payload)

    assert exc_info.value.status_code == 422
    assert "No existe valor unitario oficial" in exc_info.value.detail


@pytest.mark.anyio
async def test_beta_submission_rejects_contact_without_separate_consent():
    payload = schemas.PublicBetaSubmissionRequest(
        calculo=schemas.AppraisalPreviewRequest(
            predio_id="11111111-1111-1111-1111-111111111111",
            gestion_anio=2026,
        ),
        correo_contacto="vecino@example.com",
        acepta_registro_consulta=True,
        acepta_contacto=False,
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.submit_public_beta_consultation(None, payload)

    assert exc_info.value.status_code == 422
    assert "autorizar el contacto" in exc_info.value.detail

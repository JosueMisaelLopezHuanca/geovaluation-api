import importlib

from test.conftest import create_client


appraisal_router_module = importlib.import_module("app.modules.appraisal_engine.router")


REQUEST_PAYLOAD = {
    "predio_id": "11111111-1111-1111-1111-111111111111",
    "gestion_anio": 2026,
    "avaluo_tipo": "FISCAL",
    "usuario": "consulta_publica",
    "bloques": [],
}

FAKE_RESPONSE = {
    "appraisal_id": "11111111-1111-1111-1111-111111111111",
    "predio_id": "11111111-1111-1111-1111-111111111111",
    "preview": True,
    "avaluo_tipo": "FISCAL",
    "valor_terreno": 100.0,
    "valor_construccion": 0.0,
    "base_imponible": 100.0,
    "impuesto_estimado": 0.35,
    "normativa": {
        "gestion_anio": 2026,
        "nombre": "Normativa prueba",
        "version_codigo": "V1",
    },
    "factores_aplicados": {},
    "contexto_espacial": {},
    "tablas_utilizadas": [],
    "formula_aplicada": {},
    "auditoria": {},
    "bloques": [],
    "export_urls": {},
}


def _login_headers(client):
    response = client.post(
        "/api/v2/auth/login",
        json={"user": "admin", "password": "change-this-local-password"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_public_can_calculate_only_without_persisting(monkeypatch):
    captured = {}

    async def fake_calculate(db, payload):
        captured["persistir_override"] = payload.persistir_override
        return FAKE_RESPONSE

    monkeypatch.setattr(appraisal_router_module.service, "calculate_appraisal", fake_calculate)

    client = create_client()
    response = client.post(
        "/api/v2/avaluos/calcular",
        json={**REQUEST_PAYLOAD, "persistir_override": False},
    )

    assert response.status_code == 200
    assert captured["persistir_override"] is False


def test_persisted_calculation_rejects_missing_admin_session():
    client = create_client()
    response = client.post(
        "/api/v2/avaluos/calcular",
        json={**REQUEST_PAYLOAD, "persistir_override": True},
    )

    assert response.status_code == 401


def test_persisted_calculation_accepts_admin_session(monkeypatch):
    captured = {}

    async def fake_calculate(db, payload):
        captured["persistir_override"] = payload.persistir_override
        return {**FAKE_RESPONSE, "preview": False}

    monkeypatch.setattr(appraisal_router_module.service, "calculate_appraisal", fake_calculate)

    client = create_client()
    response = client.post(
        "/api/v2/avaluos/calcular",
        headers=_login_headers(client),
        json={**REQUEST_PAYLOAD, "usuario": "admin", "persistir_override": True},
    )

    assert response.status_code == 200
    assert captured["persistir_override"] is True


def test_admin_history_and_audit_require_session():
    client = create_client()

    history_response = client.get("/api/v2/avaluos?limit=1")
    audit_response = client.get(
        "/api/v2/predios/11111111-1111-1111-1111-111111111111/auditoria?limit=1"
    )
    surface_response = client.get("/api/v2/superficies/diferencias?limit=1")
    surface_layer_response = client.get(
        "/api/v2/gis/capas/diferencias_superficie/bbox?xmin=0&ymin=0&xmax=1&ymax=1"
    )
    beta_summary_response = client.get("/api/v2/beta/consultas/resumen")
    beta_list_response = client.get("/api/v2/beta/consultas?limit=1")
    beta_export_response = client.get("/api/v2/beta/consultas/export/csv")
    beta_delete_contact_response = client.delete(
        "/api/v2/beta/consultas/22222222-2222-2222-2222-222222222222/contacto"
    )

    assert history_response.status_code == 401
    assert audit_response.status_code == 401
    assert surface_response.status_code == 401
    assert surface_layer_response.status_code == 401
    assert beta_summary_response.status_code == 401
    assert beta_list_response.status_code == 401
    assert beta_export_response.status_code == 401
    assert beta_delete_contact_response.status_code == 401


def test_public_beta_submission_is_available_without_account(monkeypatch):
    async def fake_submission(db, payload):
        assert payload.acepta_registro_consulta is True
        return {
            "beta_submission_id": "22222222-2222-2222-2222-222222222222",
            "created_at": "2026-05-26T12:00:00-04:00",
            "contacto_registrado": False,
            "message": "Consulta registrada para la prueba beta sin datos de contacto.",
        }

    monkeypatch.setattr(
        appraisal_router_module.service,
        "submit_public_beta_consultation",
        fake_submission,
    )

    client = create_client()
    response = client.post(
        "/api/v2/beta/consultas",
        json={
            "calculo": REQUEST_PAYLOAD,
            "utilidad_resultado": "UTIL",
            "acepta_registro_consulta": True,
            "acepta_contacto": False,
        },
    )

    assert response.status_code == 200
    assert response.json()["contacto_registrado"] is False


def test_admin_can_list_beta_consultations(monkeypatch):
    async def fake_list(db, limit):
        assert limit == 5
        return {
            "total": 1,
            "items": [
                {
                    "beta_submission_id": "22222222-2222-2222-2222-222222222222",
                    "predio_id": "11111111-1111-1111-1111-111111111111",
                    "codigo_catastral": "028000100020000",
                    "gestion_anio": 2026,
                    "avaluo_tipo": "FISCAL",
                    "regimen_inmueble": "VIVIENDA_FAMILIAR",
                    "base_imponible": 100.0,
                    "impuesto_estimado": 0.35,
                    "utilidad_resultado": "UTIL",
                    "comentario": "Resultado claro.",
                    "contacto_autorizado": False,
                    "created_at": "2026-05-26T12:00:00-04:00",
                }
            ],
        }

    monkeypatch.setattr(
        appraisal_router_module.service,
        "list_public_beta_consultations",
        fake_list,
    )

    client = create_client()
    response = client.get(
        "/api/v2/beta/consultas?limit=5",
        headers=_login_headers(client),
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["utilidad_resultado"] == "UTIL"


def test_admin_can_export_beta_consultations(monkeypatch):
    async def fake_export(db):
        return b"codigo_catastral,utilidad\r\n028000100020000,UTIL\r\n", "text/csv; charset=utf-8", "consultas_beta_publicas.csv"

    monkeypatch.setattr(
        appraisal_router_module.service,
        "export_public_beta_consultations_csv",
        fake_export,
    )

    client = create_client()
    response = client.get(
        "/api/v2/beta/consultas/export/csv",
        headers=_login_headers(client),
    )

    assert response.status_code == 200
    assert response.headers["content-disposition"] == 'attachment; filename="consultas_beta_publicas.csv"'
    assert "028000100020000" in response.text


def test_admin_can_delete_authorized_beta_contact(monkeypatch):
    async def fake_delete(db, beta_submission_id):
        assert beta_submission_id == "22222222-2222-2222-2222-222222222222"
        return {"message": "Datos de contacto eliminados; la consulta estadistica se conserva."}

    monkeypatch.setattr(
        appraisal_router_module.service,
        "delete_public_beta_contact",
        fake_delete,
    )

    client = create_client()
    response = client.delete(
        "/api/v2/beta/consultas/22222222-2222-2222-2222-222222222222/contacto",
        headers=_login_headers(client),
    )

    assert response.status_code == 200
    assert "contacto eliminados" in response.json()["message"]

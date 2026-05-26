from test.conftest import create_client
from app.domain.predios.service import infer_bbox_srid


async def _fake_predios_bbox(db, xmin, ymin, xmax, ymax, limit):
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": []},
                "properties": {"id": "predio-1", "codigo": "ABC123"},
            }
        ],
    }


def test_predios_bbox_returns_feature_collection(monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.endpoints.predios.get_predios_bbox",
        _fake_predios_bbox,
    )

    client = create_client()
    response = client.get(
        "/api/v1/predios/bbox",
        params={
            "xmin": 1,
            "ymin": 2,
            "xmax": 3,
            "ymax": 4,
            "limit": 10,
        },
    )

    assert response.status_code == 200
    assert response.json()["type"] == "FeatureCollection"
    assert len(response.json()["features"]) == 1


def test_predios_bbox_validates_required_params():
    client = create_client()
    response = client.get("/api/v1/predios/bbox")

    assert response.status_code == 422


def test_infer_bbox_srid_detects_geographic_bounds():
    assert infer_bbox_srid(-68.2, -16.55, -68.1, -16.45) == 4326


def test_infer_bbox_srid_detects_projected_bounds():
    assert infer_bbox_srid(594465.67, 8176682.28, 594659.02, 8176834.51) == 32719


async def _fake_predios_search(db, query, limit, otb_name=None):
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": []},
                "properties": {
                    "id": "predio-2",
                    "codigo": "036005400040000",
                    "otb_nombre": otb_name,
                },
            }
        ],
    }


def test_predios_search_allows_otb_without_query(monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.endpoints.predios.search_predios_by_query",
        _fake_predios_search,
    )

    client = create_client()
    response = client.get(
        "/api/v1/predios/search",
        params={
            "otb": "JUPAPINA",
            "limit": 5,
        },
    )

    assert response.status_code == 200
    assert response.json()["type"] == "FeatureCollection"
    assert response.json()["features"][0]["properties"]["otb_nombre"] == "JUPAPINA"

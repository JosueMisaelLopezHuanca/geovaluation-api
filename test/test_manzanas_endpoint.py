from test.conftest import create_client


async def _fake_manzanas_bbox(db, xmin, ymin, xmax, ymax):
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": []},
                "properties": {"id": "manzana-1", "codigo": "MZ001"},
            }
        ],
    }


def test_manzanas_bbox_returns_feature_collection(monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.endpoints.manzanas.get_manzanas_bbox",
        _fake_manzanas_bbox,
    )

    client = create_client()
    response = client.get(
        "/api/v1/manzanas/bbox",
        params={"xmin": 1, "ymin": 2, "xmax": 3, "ymax": 4},
    )

    assert response.status_code == 200
    assert response.json()["type"] == "FeatureCollection"
    assert len(response.json()["features"]) == 1

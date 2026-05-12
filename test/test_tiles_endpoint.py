from test.conftest import create_client


async def _fake_tile(db, z, x, y):
    return b"fake-mvt"


def test_tiles_endpoint_returns_pbf(monkeypatch):
    monkeypatch.setattr("app.api.v1.endpoints.tiles.get_tile", _fake_tile)

    client = create_client()
    response = client.get("/api/v1/tiles/1/2/3.pbf")

    assert response.status_code == 200
    assert response.content == b"fake-mvt"
    assert response.headers["content-type"] == "application/x-protobuf"

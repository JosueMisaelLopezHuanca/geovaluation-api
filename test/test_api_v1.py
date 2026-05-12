from app.main import app


def test_routes_are_registered():
    paths = {route.path for route in app.routes if hasattr(route, "path")}

    assert "/api/v1/predios/bbox" in paths
    assert "/api/v1/manzanas/bbox" in paths
    assert "/api/v1/tiles/{z}/{x}/{y}.pbf" in paths
    assert "/api/v1/avaluos/health" in paths
    assert "/api/v1/avaluos/contexto/{id_predio}" in paths

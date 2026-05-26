from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.predios.repository import (
    fetch_predio_at_point,
    fetch_otb_feature_by_name,
    fetch_predios_bbox,
    list_otbs,
    search_predios,
)


def infer_bbox_srid(xmin: float, ymin: float, xmax: float, ymax: float) -> int:
    if (
        -180 <= xmin <= 180
        and -180 <= xmax <= 180
        and -90 <= ymin <= 90
        and -90 <= ymax <= 90
    ):
        return 4326
    return 32719


async def get_predios_bbox(
    db: AsyncSession, xmin: float, ymin: float, xmax: float, ymax: float, limit: int
):
    srid = infer_bbox_srid(xmin, ymin, xmax, ymax)
    data = await fetch_predios_bbox(
        db,
        xmin,
        ymin,
        xmax,
        ymax,
        limit,
        input_srid=srid,
        output_srid=srid,
    )
    return data or {"type": "FeatureCollection", "features": []}


async def get_predio_at_point(db: AsyncSession, lng: float, lat: float):
    if not (-180 <= lng <= 180 and -90 <= lat <= 90):
        return {"type": "FeatureCollection", "features": []}

    data = await fetch_predio_at_point(db, lng, lat)
    return data or {"type": "FeatureCollection", "features": []}


async def search_predios_by_query(
    db: AsyncSession,
    query: str | None,
    limit: int,
    otb_name: str | None = None,
):
    normalized_query = (query or "").strip()
    normalized_otb_name = (otb_name or "").strip()

    if len(normalized_query) < 2 and not normalized_otb_name:
        return {"type": "FeatureCollection", "features": []}

    data = await search_predios(db, normalized_query, limit, normalized_otb_name or None)
    return data or {"type": "FeatureCollection", "features": []}


async def get_otb_options(db: AsyncSession, limit: int = 600, query: str | None = None):
    return await list_otbs(db, limit, query)


async def get_otb_feature(db: AsyncSession, name: str):
    normalized_name = name.strip()
    if not normalized_name:
        return {"type": "FeatureCollection", "features": []}

    data = await fetch_otb_feature_by_name(db, normalized_name)
    return data or {"type": "FeatureCollection", "features": []}

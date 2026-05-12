from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.predios.repository import fetch_predios_bbox


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

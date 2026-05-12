from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.manzanas.repository import fetch_manzanas_bbox


async def get_manzanas_bbox(
    db: AsyncSession, xmin: float, ymin: float, xmax: float, ymax: float
):
    data = await fetch_manzanas_bbox(db, xmin, ymin, xmax, ymax)
    return data or {"type": "FeatureCollection", "features": []}

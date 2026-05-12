from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.domain.manzanas.service import get_manzanas_bbox

router = APIRouter()


@router.get("/bbox")
async def bbox(
    xmin: float = Query(...),
    ymin: float = Query(...),
    xmax: float = Query(...),
    ymax: float = Query(...),
    db: AsyncSession = Depends(get_db),
):
    return await get_manzanas_bbox(db, xmin, ymin, xmax, ymax)

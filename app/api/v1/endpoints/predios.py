from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.domain.predios.service import get_predios_bbox

router = APIRouter()


@router.get("/bbox")
async def bbox(
    xmin: float = Query(...),
    ymin: float = Query(...),
    xmax: float = Query(...),
    ymax: float = Query(...),
    limit: int = Query(5000, ge=1, le=20000),
    db: AsyncSession = Depends(get_db),
):
    return await get_predios_bbox(db, xmin, ymin, xmax, ymax, limit)

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from .service import get_predios_bbox

router = APIRouter()

@router.get("/bbox")
async def bbox(
    xmin: float = Query(...),
    ymin: float = Query(...),
    xmax: float = Query(...),
    ymax: float = Query(...),
    limit: int = 5000,
    db: AsyncSession = Depends(get_db)
):
    return await get_predios_bbox(db, xmin, ymin, xmax, ymax, limit)
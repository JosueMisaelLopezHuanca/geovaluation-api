from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from .service import get_manzanas_bbox

router = APIRouter()

@router.get("/bbox")
async def bbox(
    xmin: float,
    ymin: float,
    xmax: float,
    ymax: float,
    db: AsyncSession = Depends(get_db)
):
    return await get_manzanas_bbox(db, xmin, ymin, xmax, ymax)
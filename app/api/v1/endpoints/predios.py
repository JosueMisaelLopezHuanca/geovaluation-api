from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.domain.predios.service import (
    get_predio_at_point,
    get_otb_feature,
    get_otb_options,
    get_predios_bbox,
    search_predios_by_query,
)

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


@router.get("/point")
async def point(
    lng: float = Query(..., ge=-180, le=180),
    lat: float = Query(..., ge=-90, le=90),
    db: AsyncSession = Depends(get_db),
):
    return await get_predio_at_point(db, lng, lat)


@router.get("/search")
async def search(
    q: str | None = Query(None),
    otb: str | None = Query(None, min_length=1),
    limit: int = Query(8, ge=1, le=25),
    db: AsyncSession = Depends(get_db),
):
    return await search_predios_by_query(db, q, limit, otb)


@router.get("/otbs/options")
async def otb_options(
    q: str | None = Query(None, min_length=1),
    limit: int = Query(600, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    return await get_otb_options(db, limit, q)


@router.get("/otbs/feature")
async def otb_feature(
    name: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
):
    return await get_otb_feature(db, name)

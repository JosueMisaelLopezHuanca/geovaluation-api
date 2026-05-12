from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.manzana_service import (
    obtener_manzanas,
    obtener_manzanas_geojson
)

router = APIRouter(prefix="/manzanas", tags=["Manzanas"])

@router.get("/")
async def listar_manzanas(db: AsyncSession = Depends(get_db)):
    return await obtener_manzanas(db)

@router.get("/geojson")
async def manzanas_geojson(db: AsyncSession = Depends(get_db)):
    return await obtener_manzanas_geojson(db)
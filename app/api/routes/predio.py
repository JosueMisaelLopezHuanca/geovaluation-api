from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.predio_service import (
    obtener_predios,
    obtener_predios_geojson
)

router = APIRouter(prefix="/predios", tags=["Predios"])

@router.get("/")
async def listar_predios(db: AsyncSession = Depends(get_db)):
    return await obtener_predios(db)

@router.get("/geojson")
async def predios_geojson(db: AsyncSession = Depends(get_db)):
    return await obtener_predios_geojson(db)
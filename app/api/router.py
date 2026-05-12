from fastapi import APIRouter

from app.api.v1.endpoints.avaluos import router as avaluos_router
from app.api.v1.endpoints.manzanas import router as manzanas_router
from app.api.v1.endpoints.predios import router as predios_router
from app.api.v1.endpoints.tiles import router as tiles_router

api_router = APIRouter()
api_router.include_router(predios_router, prefix="/predios", tags=["Predios"])
api_router.include_router(manzanas_router, prefix="/manzanas", tags=["Manzanas"])
api_router.include_router(tiles_router, prefix="/tiles", tags=["Tiles"])
api_router.include_router(avaluos_router, prefix="/avaluos", tags=["Avaluos"])

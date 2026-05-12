from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.models.avaluos import schemas, service

router = APIRouter(prefix="/api/v1/avaluos", tags=["Avalúos"])

@router.post("/", response_model=schemas.AvaluoResponse)
async def generar_avaluo(avaluo: schemas.AvaluoCreate, db: AsyncSession = Depends(get_db)):
    try:
        return await service.calcular_y_guardar_avaluo(db, avaluo)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error en el cálculo misa: {str(e)}")
    
 
    
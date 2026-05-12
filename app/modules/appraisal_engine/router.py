from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.modules.appraisal_engine import schemas, service

router = APIRouter(prefix="/api/v2", tags=["AppraisalEngineV2"])


@router.get("/health")
async def health():
    return {"status": "ok", "module": "appraisal-engine-v2"}


@router.get("/metodologia")
async def get_methodology():
    return service.get_methodology()


@router.post("/avaluos/calcular", response_model=schemas.AppraisalResponseV2)
async def calculate_appraisal(
    payload: schemas.AppraisalRequestV2,
    db: AsyncSession = Depends(get_db),
):
    return await service.calculate_appraisal(db, payload)


@router.get("/avaluos", response_model=list[schemas.AppraisalListItem])
async def list_appraisals(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_appraisals(db, limit)


@router.get("/avaluos/{appraisal_id}", response_model=schemas.AppraisalResponseV2)
async def get_appraisal(appraisal_id: str, db: AsyncSession = Depends(get_db)):
    return await service.get_appraisal(db, appraisal_id)


@router.get("/avaluos/{appraisal_id}/traza", response_model=schemas.AppraisalTraceResponse)
async def get_appraisal_trace(appraisal_id: str, db: AsyncSession = Depends(get_db)):
    return await service.get_appraisal_trace(db, appraisal_id)


@router.get("/tablas-maestras/{table_name}", response_model=list[schemas.MasterTableRow])
async def get_master_table(
    table_name: str,
    gestion: int = Query(..., ge=2025),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_master_table(db, table_name, gestion)


@router.get("/predios/{predio_id}/contexto-gis", response_model=schemas.PredioGisContextResponse)
async def get_predio_context(predio_id: str, db: AsyncSession = Depends(get_db)):
    return await service.get_predio_gis_context(db, predio_id)


@router.post("/construcciones", response_model=schemas.ConstructionValuationResponse)
async def value_construction_blocks(
    payload: schemas.ConstructionValuationRequest,
    db: AsyncSession = Depends(get_db),
):
    return await service.value_construction_blocks(db, payload)

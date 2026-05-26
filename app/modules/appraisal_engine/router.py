from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.modules.auth.router import AuthSession, get_current_session
from app.modules.appraisal_engine import schemas, service

router = APIRouter(prefix="/api/v2", tags=["AppraisalEngineV2"])


@router.get("/health")
async def health():
    return {"status": "ok", "module": "appraisal-engine-v2"}


@router.get("/metodologia")
async def get_methodology():
    return service.get_methodology()


@router.get("/catalogos/publicos", response_model=schemas.PublicCatalogsResponse)
async def get_public_catalogs():
    return service.get_public_catalogs()


@router.get("/cobertura-estadisticas")
async def get_coverage_stats(db: AsyncSession = Depends(get_db)):
    return await service.get_coverage_stats(db)


@router.get("/gis/capas/{capa}/bbox")
async def get_gis_layer_bbox(
    capa: str,
    xmin: float = Query(...),
    ymin: float = Query(...),
    xmax: float = Query(...),
    ymax: float = Query(...),
    limit: int = Query(3000, ge=1, le=20000),
    db: AsyncSession = Depends(get_db),
    authorization: str | None = Header(default=None),
):
    if capa.lower() == "diferencias_superficie":
        await get_current_session(authorization)
    return await service.get_gis_layer_bbox(
        db,
        capa=capa,
        xmin=xmin,
        ymin=ymin,
        xmax=xmax,
        ymax=ymax,
        limit=limit,
    )


@router.post("/avaluos/calcular", response_model=schemas.AppraisalResponseV2)
async def calculate_appraisal(
    payload: schemas.AppraisalRequestV2,
    db: AsyncSession = Depends(get_db),
    authorization: str | None = Header(default=None),
):
    if payload.persistir_override:
        await get_current_session(authorization)
    return await service.calculate_appraisal(db, payload)


@router.post("/avaluos/preview", response_model=schemas.AppraisalResponseV2)
async def preview_appraisal(
    payload: schemas.AppraisalPreviewRequest,
    db: AsyncSession = Depends(get_db),
):
    return await service.preview_appraisal(db, payload)


@router.post("/beta/consultas", response_model=schemas.PublicBetaSubmissionResponse)
async def submit_public_beta_consultation(
    payload: schemas.PublicBetaSubmissionRequest,
    db: AsyncSession = Depends(get_db),
):
    return await service.submit_public_beta_consultation(db, payload)


@router.get("/beta/consultas/resumen", response_model=schemas.PublicBetaSummaryResponse)
async def get_public_beta_summary(
    db: AsyncSession = Depends(get_db),
    _session: AuthSession = Depends(get_current_session),
):
    return await service.get_public_beta_summary(db)


@router.get("/beta/consultas", response_model=schemas.PublicBetaAdminListResponse)
async def list_public_beta_consultations(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _session: AuthSession = Depends(get_current_session),
):
    return await service.list_public_beta_consultations(db, limit=limit)


@router.get("/beta/consultas/export/csv")
async def export_public_beta_consultations_csv(
    db: AsyncSession = Depends(get_db),
    _session: AuthSession = Depends(get_current_session),
):
    content, media_type, filename = await service.export_public_beta_consultations_csv(db)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/beta/consultas/{beta_submission_id}/contacto")
async def delete_public_beta_contact(
    beta_submission_id: str,
    db: AsyncSession = Depends(get_db),
    _session: AuthSession = Depends(get_current_session),
):
    return await service.delete_public_beta_contact(db, beta_submission_id)


@router.get("/avaluos", response_model=list[schemas.AppraisalListItem])
async def list_appraisals(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _session: AuthSession = Depends(get_current_session),
):
    return await service.list_appraisals(db, limit)


@router.get("/avaluos/{appraisal_id}", response_model=schemas.AppraisalResponseV2)
async def get_appraisal(
    appraisal_id: str,
    db: AsyncSession = Depends(get_db),
    _session: AuthSession = Depends(get_current_session),
):
    return await service.get_appraisal(db, appraisal_id)


@router.get("/avaluos/{appraisal_id}/traza", response_model=schemas.AppraisalTraceResponse)
async def get_appraisal_trace(
    appraisal_id: str,
    db: AsyncSession = Depends(get_db),
    _session: AuthSession = Depends(get_current_session),
):
    return await service.get_appraisal_trace(db, appraisal_id)


@router.get("/avaluos/{appraisal_id}/export/{export_format}")
async def export_appraisal(
    appraisal_id: str,
    export_format: str,
    db: AsyncSession = Depends(get_db),
    _session: AuthSession = Depends(get_current_session),
):
    content, media_type, filename = await service.export_appraisal(db, appraisal_id, export_format)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/superficies/diferencias", response_model=schemas.SurfaceDifferenceListResponse)
async def list_surface_differences(
    status: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(100, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _session: AuthSession = Depends(get_current_session),
):
    return await service.list_surface_differences(
        db,
        status=status,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.post("/superficies/diferencias/refresh")
async def refresh_surface_differences(
    db: AsyncSession = Depends(get_db),
    _session: AuthSession = Depends(get_current_session),
):
    return await service.refresh_surface_differences(db)


@router.get("/superficies/diferencias/export/{export_format}")
async def export_surface_differences(
    export_format: str,
    status: str | None = Query(default=None),
    search: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _session: AuthSession = Depends(get_current_session),
):
    content, media_type, filename = await service.export_surface_differences(
        db,
        export_format=export_format,
        status=status,
        search=search,
    )
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/tablas-maestras/{table_name}", response_model=list[schemas.MasterTableRow])
async def get_master_table(
    table_name: str,
    gestion: int = Query(..., ge=2025),
    db: AsyncSession = Depends(get_db),
    _session: AuthSession = Depends(get_current_session),
):
    return await service.get_master_table(db, table_name, gestion)


@router.get("/predios/{predio_id}/contexto-gis", response_model=schemas.PredioGisContextResponse)
async def get_predio_context(predio_id: str, db: AsyncSession = Depends(get_db)):
    return await service.get_predio_gis_context(db, predio_id)


@router.get("/predios/{predio_id}/auditoria", response_model=list[schemas.AuditEntryResponse])
async def get_predio_audit(
    predio_id: str,
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _session: AuthSession = Depends(get_current_session),
):
    return await service.get_audit_entries(db, predio_id, limit)


@router.post("/construcciones", response_model=schemas.ConstructionValuationResponse)
async def value_construction_blocks(
    payload: schemas.ConstructionValuationRequest,
    db: AsyncSession = Depends(get_db),
):
    return await service.value_construction_blocks(db, payload)

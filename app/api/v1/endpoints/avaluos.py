from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.modules.auth.router import AuthSession, get_current_session
from app.domain.avaluos.schemas import (
    AvaluoAutomaticoCreate,
    AvaluoContextResponse,
    AvaluoCreate,
    AvaluoListItem,
    AvaluoResponse,
)
from app.domain.avaluos.service import (
    calcular_y_guardar_avaluo,
    listar_avaluos,
    obtener_avaluo_por_id,
    obtener_contexto_avaluo,
    obtener_metodologia_avaluo,
)
from app.domain.avaluos.service import (
    obtener_capa_bbox,
    obtener_estadisticas_cobertura,
    obtener_estadisticas_contexto,
)

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok", "modulo": "avaluos"}


@router.get("/contexto/{id_predio}", response_model=AvaluoContextResponse)
async def obtener_contexto(id_predio: str, db: AsyncSession = Depends(get_db)):
    return await obtener_contexto_avaluo(db, id_predio)


@router.get("/contexto-estadisticas")
async def obtener_contexto_estadisticas(db: AsyncSession = Depends(get_db)):
    return await obtener_estadisticas_contexto(db)


@router.get("/cobertura-estadisticas")
async def obtener_cobertura_estadisticas(db: AsyncSession = Depends(get_db)):
    return await obtener_estadisticas_cobertura(db)


@router.get("/metodologia")
async def obtener_metodologia():
    return await obtener_metodologia_avaluo()


@router.get("/capas/{capa}/bbox")
async def obtener_capa_contexto_bbox(
    capa: str,
    xmin: float = Query(...),
    ymin: float = Query(...),
    xmax: float = Query(...),
    ymax: float = Query(...),
    limit: int = Query(3000, ge=1, le=10000),
    db: AsyncSession = Depends(get_db),
):
    return await obtener_capa_bbox(
        db,
        capa=capa,
        xmin=xmin,
        ymin=ymin,
        xmax=xmax,
        ymax=ymax,
        limit=limit,
    )


@router.post("/", response_model=AvaluoResponse)
async def generar_avaluo(
    avaluo: AvaluoCreate,
    db: AsyncSession = Depends(get_db),
    _session: AuthSession = Depends(get_current_session),
):
    return await calcular_y_guardar_avaluo(db, avaluo)


@router.get("/", response_model=list[AvaluoListItem])
async def listar_avaluos_guardados(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _session: AuthSession = Depends(get_current_session),
):
    return await listar_avaluos(db, limit=limit)


@router.get("/{id_avaluo}", response_model=AvaluoResponse)
async def obtener_avaluo_detalle(
    id_avaluo: str,
    db: AsyncSession = Depends(get_db),
    _session: AuthSession = Depends(get_current_session),
):
    return await obtener_avaluo_por_id(db, id_avaluo=id_avaluo)


@router.post("/automatico/{id_predio}", response_model=AvaluoResponse)
async def generar_avaluo_automatico(
    id_predio: str,
    payload: AvaluoAutomaticoCreate,
    db: AsyncSession = Depends(get_db),
    _session: AuthSession = Depends(get_current_session),
):
    avaluo = AvaluoCreate(id_predio=id_predio, **payload.model_dump())
    return await calcular_y_guardar_avaluo(db, avaluo)

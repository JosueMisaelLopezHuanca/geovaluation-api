from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class BuildingBlockInput(BaseModel):
    superficie: float = Field(gt=0)
    calidad_constructiva: str = Field(min_length=3)
    anio_construccion: int = Field(ge=1900, le=2100)


class ConstructionValuationRequest(BaseModel):
    gestion_anio: int = Field(ge=2025, le=2100)
    bloques: list[BuildingBlockInput] = Field(default_factory=list, min_length=1)


class ConstructionValuationResponse(BaseModel):
    gestion_anio: int
    valor_construccion: float
    bloques: list[dict] = Field(default_factory=list)


class AppraisalRequestV2(BaseModel):
    predio_id: UUID
    gestion_anio: int = Field(ge=2025, le=2100)
    superficie_manual: float | None = Field(default=None, gt=0)
    superficie_override_reason: str | None = None
    bloques: list[BuildingBlockInput] = Field(default_factory=list)
    estado_conservacion: str | None = None
    observaciones: str | None = None
    usuario: str = Field(default="admin", min_length=4)


class MasterTableRow(BaseModel):
    codigo: str
    valor: float | None = None
    descripcion: str | None = None
    metadata: dict = Field(default_factory=dict)


class PredioGisContextResponse(BaseModel):
    predio_id: UUID
    superficie_gis: float
    superficie_legal: float | None = None
    superficie_manual: float | None = None
    superficie_calculo: float
    superficie_fuente: str
    zona_homogenea_codigo: str | None = None
    zona_homogenea_grupo: str | None = None
    zona_tributaria_codigo: str | None = None
    material_via_codigo: str | None = None
    pendiente_codigo: int | None = None
    pendiente_grados: float | None = None
    riesgo_codigo: int | None = None
    riesgo_grado: str | None = None
    servicios_oficiales: list[str] = Field(default_factory=list)
    overlays_utilizados: list[str] = Field(default_factory=list)


class AppraisalTraceResponse(BaseModel):
    appraisal_id: UUID
    predio_id: UUID
    gestion_anio: int
    normative_version: str
    input_payload: dict
    factores_aplicados: dict
    contexto_espacial: dict
    tablas_utilizadas: list[str]
    formulas_aplicadas: dict
    overrides_manuales: dict
    geometries_used: dict
    generated_by: UUID
    generated_at: datetime


class AppraisalResponseV2(BaseModel):
    appraisal_id: UUID
    predio_id: UUID
    created_at: datetime | None = None
    valor_terreno: float
    valor_construccion: float
    base_imponible: float
    impuesto_estimado: float
    factores_aplicados: dict
    contexto_espacial: dict
    tablas_utilizadas: list[str]
    formula_aplicada: dict
    auditoria: dict
    bloques: list[dict] = Field(default_factory=list)


class AppraisalListItem(BaseModel):
    appraisal_id: UUID
    predio_id: UUID
    codigo_catastral: str | None = None
    gestion_anio: int
    base_imponible: float
    impuesto_estimado: float
    valor_terreno: float
    valor_construccion: float
    created_at: datetime

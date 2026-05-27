from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class BuildingBlockInput(BaseModel):
    superficie: float = Field(gt=0)
    calidad_constructiva: str = Field(min_length=3)
    anio_construccion: int = Field(ge=1500, le=2100)
    estado_conservacion: str | None = None
    numero_pisos: int | None = Field(default=None, ge=1, le=120)
    uso_construccion: str | None = None
    material_estructural: str | None = None
    tipo_cubierta: str | None = None
    remodelaciones: str | None = None
    depreciacion_manual: float | None = Field(default=None, gt=0, le=1)
    usar_depreciacion_manual: bool = False


class ManualInputPayload(BaseModel):
    motivo: str | None = None
    es_temporal: bool = False
    superficie_manual: float | None = Field(default=None, gt=0)
    frente: float | None = Field(default=None, gt=0)
    fondo: float | None = Field(default=None, gt=0)
    forma_lote: str | None = None
    uso_suelo: str | None = None
    tipo_via: str | None = None
    acceso_vehicular: bool | None = None
    pendiente_manual: float | None = Field(default=None, ge=0, le=90)
    zona_homogenea_manual: str | None = None
    zona_tributaria_manual: str | None = None
    coordenadas_manual: str | None = None
    distrito_manual: str | None = None
    macrodistrito_manual: str | None = None
    agua: bool | None = None
    alcantarillado: bool | None = None
    electricidad: bool | None = None
    telefono: bool | None = None
    gas: bool | None = None
    internet: bool | None = None
    alumbrado_publico: bool | None = None
    riesgo_territorial_manual: str | None = None
    tipo_riesgo: str | None = None
    afectacion_riesgo: str | None = None
    valor_unitario_manual: float | None = Field(default=None, gt=0)
    usar_valor_unitario_manual: bool = False
    coeficiente_manual: float | None = Field(default=None, gt=0)
    usar_coeficiente_manual: bool = False
    depreciacion_manual: float | None = Field(default=None, gt=0, le=1)
    usar_depreciacion_manual: bool = False
    ajuste_comercial: float | None = Field(default=None, gt=0)
    clasificacion_especial: Literal["ESQUINA", "AVENIDA", "ESQUINA_AVENIDA"] | None = None
    observacion_tecnica: str | None = None


class DataSourceDetail(BaseModel):
    value: str | float | int | bool | None = None
    source: str
    is_temporary: bool = False
    note: str | None = None


class NormativeMetadata(BaseModel):
    gestion_anio: int
    nombre: str
    version_codigo: str
    fuente_gestion_anio: int | None = None
    vigente_para_gestion: int | None = None
    alcance: str | None = None
    resolucion_municipal: str | None = None
    detalle_normativo: str | None = None


class FormulaComponent(BaseModel):
    nombre: str
    valor: float | int | str | None = None
    fuente: str | None = None
    tabla: str | None = None
    descripcion: str | None = None


class FormulaDetail(BaseModel):
    simbolica: str
    expandida: str
    resultado: float
    componentes: list[FormulaComponent] = Field(default_factory=list)


class DifferenceReport(BaseModel):
    diferencia: float
    porcentaje_diferencia: float | None = None
    clasificacion: str
    color: str


class ConstructionValuationRequest(BaseModel):
    gestion_anio: int = Field(ge=2025, le=2100)
    avaluo_tipo: Literal["FISCAL", "COMERCIAL"] = "FISCAL"
    regimen_inmueble: Literal["VIVIENDA_FAMILIAR", "PROPIEDAD_HORIZONTAL"] = "VIVIENDA_FAMILIAR"
    zona_tributaria_codigo: str | None = None
    bloques: list[BuildingBlockInput] = Field(default_factory=list, min_length=1)
    manual: ManualInputPayload | None = None


class ConstructionValuationResponse(BaseModel):
    gestion_anio: int
    valor_construccion: float
    bloques: list[dict] = Field(default_factory=list)
    factores_aplicados: dict = Field(default_factory=dict)


class AppraisalRequestV2(BaseModel):
    predio_id: UUID
    gestion_anio: int = Field(ge=2025, le=2100)
    avaluo_tipo: Literal["FISCAL", "COMERCIAL"] = "FISCAL"
    regimen_inmueble: Literal["VIVIENDA_FAMILIAR", "PROPIEDAD_HORIZONTAL"] = "VIVIENDA_FAMILIAR"
    superficie_manual: float | None = Field(default=None, gt=0)
    superficie_override_reason: str | None = None
    bloques: list[BuildingBlockInput] = Field(default_factory=list)
    estado_conservacion: str | None = None
    observaciones: str | None = None
    usuario: str = Field(default="consulta_publica", min_length=4)
    manual: ManualInputPayload | None = None
    persistir_override: bool = True


class AppraisalPreviewRequest(BaseModel):
    predio_id: UUID
    gestion_anio: int = Field(ge=2025, le=2100)
    avaluo_tipo: Literal["FISCAL", "COMERCIAL"] = "FISCAL"
    regimen_inmueble: Literal["VIVIENDA_FAMILIAR", "PROPIEDAD_HORIZONTAL"] = "VIVIENDA_FAMILIAR"
    bloques: list[BuildingBlockInput] = Field(default_factory=list)
    usuario: str = Field(default="consulta_publica", min_length=4)
    manual: ManualInputPayload | None = None


class MasterTableRow(BaseModel):
    codigo: str
    valor: float | None = None
    descripcion: str | None = None
    metadata: dict = Field(default_factory=dict)


class CatalogOption(BaseModel):
    value: str
    label: str
    description: str | None = None


class PublicCatalogsResponse(BaseModel):
    forma_lote: list[CatalogOption] = Field(default_factory=list)
    uso_suelo: list[CatalogOption] = Field(default_factory=list)
    tipo_via: list[CatalogOption] = Field(default_factory=list)
    riesgo_territorial: list[CatalogOption] = Field(default_factory=list)
    calidad_constructiva: list[CatalogOption] = Field(default_factory=list)
    estado_conservacion: list[CatalogOption] = Field(default_factory=list)
    uso_construccion: list[CatalogOption] = Field(default_factory=list)
    material_estructural: list[CatalogOption] = Field(default_factory=list)
    tipo_cubierta: list[CatalogOption] = Field(default_factory=list)


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
    pendiente_final: float | int | None = None
    pendiente_fuente: str | None = None
    riesgo_codigo: int | None = None
    riesgo_grado: str | None = None
    riesgo_final: str | None = None
    riesgo_fuente: str | None = None
    servicios_oficiales: list[str] = Field(default_factory=list)
    servicios_completos: dict = Field(default_factory=dict)
    frente: float | None = None
    fondo: float | None = None
    forma_lote: str | None = None
    uso_suelo: str | None = None
    tipo_via: str | None = None
    acceso_vehicular: bool | None = None
    coordenadas: str | None = None
    distrito: str | None = None
    macrodistrito: str | None = None
    tipo_riesgo: str | None = None
    afectacion_riesgo: str | None = None
    diferencia_superficie: DifferenceReport
    fuentes: dict[str, DataSourceDetail] = Field(default_factory=dict)
    overlays_utilizados: list[str] = Field(default_factory=list)


class AppraisalTraceResponse(BaseModel):
    appraisal_id: UUID
    predio_id: UUID
    gestion_anio: int
    normative_version: str
    input_payload: dict
    factores_aplicados: dict
    contexto_espacial: dict
    tablas_utilizadas: list[dict]
    formulas_aplicadas: dict
    overrides_manuales: dict
    geometries_used: dict
    generated_by: UUID
    generated_at: datetime


class AppraisalResponseV2(BaseModel):
    appraisal_id: UUID
    predio_id: UUID
    created_at: datetime | None = None
    preview: bool = False
    avaluo_tipo: Literal["FISCAL", "COMERCIAL"]
    regimen_inmueble: Literal["VIVIENDA_FAMILIAR", "PROPIEDAD_HORIZONTAL"] = "VIVIENDA_FAMILIAR"
    valor_terreno: float
    valor_construccion: float
    base_imponible: float
    impuesto_estimado: float
    normativa: NormativeMetadata
    factores_aplicados: dict
    contexto_espacial: dict
    tablas_utilizadas: list[dict]
    formula_aplicada: dict
    auditoria: dict
    bloques: list[dict] = Field(default_factory=list)
    export_urls: dict[str, str] = Field(default_factory=dict)


class AppraisalListItem(BaseModel):
    appraisal_id: UUID
    predio_id: UUID
    codigo_catastral: str | None = None
    gestion_anio: int
    avaluo_tipo: str | None = None
    base_imponible: float
    impuesto_estimado: float
    valor_terreno: float
    valor_construccion: float
    created_at: datetime


class PublicBetaSubmissionRequest(BaseModel):
    calculo: AppraisalPreviewRequest
    utilidad_resultado: Literal["UTIL", "PARCIAL", "NO_REFLEJA", "NO_SE"] | None = None
    comentario: str | None = Field(default=None, max_length=1000)
    nombre_contacto: str | None = Field(default=None, max_length=120)
    correo_contacto: str | None = Field(
        default=None,
        max_length=254,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )
    telefono_contacto: str | None = Field(
        default=None,
        max_length=30,
        pattern=r"^[0-9+()\-\s]{6,30}$",
    )
    acepta_registro_consulta: bool = False
    acepta_contacto: bool = False
    consentimiento_version: Literal["beta-v1"] = "beta-v1"


class PublicBetaSubmissionResponse(BaseModel):
    beta_submission_id: UUID
    created_at: datetime
    contacto_registrado: bool
    message: str


class PublicBetaSummaryResponse(BaseModel):
    total_consultas: int
    total_con_contacto: int
    ultima_consulta: datetime | None = None
    utilidad: dict[str, int] = Field(default_factory=dict)


class PublicBetaAdminItem(BaseModel):
    beta_submission_id: UUID
    predio_id: UUID
    codigo_catastral: str | None = None
    gestion_anio: int
    avaluo_tipo: str
    regimen_inmueble: str
    base_imponible: float
    impuesto_estimado: float
    utilidad_resultado: str | None = None
    comentario: str | None = None
    contacto_autorizado: bool = False
    nombre_contacto: str | None = None
    correo_contacto: str | None = None
    telefono_contacto: str | None = None
    created_at: datetime


class PublicBetaAdminListResponse(BaseModel):
    total: int
    items: list[PublicBetaAdminItem] = Field(default_factory=list)


class AuditEntryResponse(BaseModel):
    auditoria_id: UUID
    appraisal_id: UUID | None = None
    predio_id: UUID
    usuario_id: UUID
    campo: str
    valor_anterior: str | None = None
    valor_nuevo: str | None = None
    fuente_anterior: str | None = None
    fuente_nueva: str
    motivo: str | None = None
    es_temporal: bool = False
    created_at: datetime


class SurfaceDifferenceItem(BaseModel):
    predio_id: UUID
    codigo_catastral: str | None = None
    superficie_gis: float
    superficie_legal: float | None = None
    diferencia: float
    porcentaje_diferencia: float | None = None
    clasificacion: str
    color: str


class SurfaceDifferenceListResponse(BaseModel):
    total: int
    items: list[SurfaceDifferenceItem] = Field(default_factory=list)
    resumen: dict = Field(default_factory=dict)

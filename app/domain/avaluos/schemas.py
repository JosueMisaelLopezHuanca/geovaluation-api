from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AvaluoFichaTecnica(BaseModel):
    material_via_aplicado: str | None = None
    zona_valor_aplicada: str | None = None
    servicios_aplicados: list[str] = Field(default_factory=list)
    uso_predio: str | None = None
    estado_construccion: str | None = None
    calidad_constructiva: str | None = None
    superficie_construida_declarada: float | None = Field(default=None, ge=0)
    anio_construccion_referencia: int | None = Field(default=None, ge=1500)
    observaciones_tecnicas: str | None = None


class AvaluoCreate(BaseModel):
    id_predio: UUID
    superficie_terreno_override: float | None = Field(default=None, gt=0)
    valor_base_m2: float = Field(default=100.0, gt=0)
    alicuota_impuesto: float = Field(default=0.0035, gt=0)
    gestion_anio: int = Field(default=2026, ge=2000)
    nombre_usuario: str = Field(default="admin", min_length=4)
    factor_servicios: float = Field(default=1.0, gt=0)
    usar_tablas_maestras: bool = True
    ficha_tecnica: AvaluoFichaTecnica | None = None


class AvaluoAutomaticoCreate(BaseModel):
    superficie_terreno_override: float | None = Field(default=None, gt=0)
    valor_base_m2: float = Field(default=100.0, gt=0)
    alicuota_impuesto: float = Field(default=0.0035, gt=0)
    gestion_anio: int = Field(default=2026, ge=2000)
    nombre_usuario: str = Field(default="admin", min_length=4)
    factor_servicios: float = Field(default=1.0, gt=0)
    usar_tablas_maestras: bool = True
    ficha_tecnica: AvaluoFichaTecnica | None = None


class AvaluoResponse(BaseModel):
    id_avaluo: UUID
    id_predio: UUID
    valor_terreno: float
    valor_construccion: float
    valor_total: float
    base_imponible: float
    impuesto_estimado: float
    fecha_calculo: datetime
    superficie_terreno: float
    pendiente_grados: float | None
    factor_pendiente: float
    factor_riesgo: float
    factor_servicios: float
    valor_unitario_aplicado: float
    valor_unitario_construccion: float
    factor_depreciacion: float
    construcciones_procesadas: int
    riesgo_dn: int | None
    pendiente_dn: int | None
    geojson: str | None
    parametros_utilizados: dict

    model_config = ConfigDict(from_attributes=True)


class AvaluoListItem(BaseModel):
    id_avaluo: UUID
    id_predio: UUID
    codigo_catastral: str | None = None
    valor_total: float
    impuesto_estimado: float
    fecha_calculo: datetime
    nombre_usuario: str | None = None
    estado: str
    gestion_anio: int | None = None


class AvaluoContextResponse(BaseModel):
    id_predio: UUID
    superficie_terreno: float
    superficie_terreno_fuente: str = "predio.superficie_mensura"
    superficie_terreno_permite_edicion: bool = True
    pendiente_grados: float | None
    id_zona_valor: UUID | None
    id_material_via: UUID | None
    material_via_nombre: str | None = None
    material_via_orden: int | None = None
    zona_valor_nombre: str | None = None
    zona_valor_macro_zona: int | None = None
    zona_valor_subzona_inicio: int | None = None
    zona_valor_subzona_fin: int | None = None
    zona_homogenea_codigo: str | None = None
    zona_homogenea_grupo: str | None = None
    riesgo_codigo: int | None
    riesgo_grado: str | None
    pendiente_codigo: int | None
    pendiente_area_m2: float | None = None
    pendiente_cobertura_pct: float | None = None
    riesgo_area_m2: float | None = None
    riesgo_cobertura_pct: float | None = None
    servicios: list[str] = Field(default_factory=list)
    construcciones_registradas: int = 0
    superficie_construida_total: float = 0.0
    geojson: str | None
    columnas_origen: dict

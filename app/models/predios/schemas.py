from pydantic import BaseModel, ConfigDict
from typing import Optional, Any
from uuid import UUID

class PredioResponse(BaseModel):
    id_predio: UUID
    codigo_catastral: str
    superficie_mensura: float
    direccion: Optional[str] = None
    activo: bool
    model_config = ConfigDict(from_attributes=True)

#  NUEVO: Esquema para recibir datos
class PredioCreate(BaseModel):
    id_manzana: UUID
    id_estado_predio: UUID
    codigo_catastral: str
    superficie_mensura: float
    direccion: Optional[str] = None
    geom: Any  # Aquí recibiremos el GeoJSON dict
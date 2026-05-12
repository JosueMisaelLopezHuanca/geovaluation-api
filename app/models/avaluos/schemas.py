from pydantic import BaseModel, ConfigDict
from uuid import UUID
from datetime import datetime
from typing import Optional

class AvaluoCreate(BaseModel):
    id_predio: UUID
    valor_base_m2: float = 100.0  # Un valor por defecto para pruebas

class AvaluoResponse(BaseModel):
    id_avaluo: UUID
    id_predio: UUID
    valor_terreno: float
    valor_total: float
    fecha_calculo: datetime
    # --- Añadimos esto ---
    riesgo_dn: int 
    pendiente_dn: int
    superficie: float
    # ---------------------
    # ... dentro de AvaluoResponse ...
    geojson: str # Recibiremos el polígono como un string JSON

    model_config = ConfigDict(from_attributes=True)
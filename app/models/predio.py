from sqlalchemy import Column, String, ForeignKey, Numeric
from geoalchemy2 import Geometry
from sqlalchemy.dialects.postgresql import UUID
import uuid

from app.core.database import Base

class Predio(Base):
    __tablename__ = "predio"

    id_predio = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    id_manzana = Column(UUID(as_uuid=True), ForeignKey("manzana.id_manzana"))

    codigo_catastral = Column(String)
    superficie_mensura = Column(Numeric)

    geom = Column(Geometry("MULTIPOLYGON", srid=32719))
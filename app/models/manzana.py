from sqlalchemy import Column, String, ForeignKey
from geoalchemy2 import Geometry
from sqlalchemy.dialects.postgresql import UUID
import uuid

from app.core.database import Base

class Manzana(Base):
    __tablename__ = "manzana"

    id_manzana = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    id_zona = Column(UUID(as_uuid=True), ForeignKey("zona.id_zona"))

    codigo_manzana = Column(String)
    codigo_interno = Column(String)

    geom = Column(Geometry("MULTIPOLYGON", srid=32719))
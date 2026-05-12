from sqlalchemy import Column, String, Numeric, Boolean, text
from sqlalchemy.dialects.postgresql import UUID
from geoalchemy2 import Geometry
from app.core.database import Base

class Predio(Base):
    __tablename__ = "predio"

    # Usamos gen_random_uuid() de PostgreSQL
    id_predio = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    
    # Por ahora mapeamos las llaves foráneas como simples UUID. 
    # Más adelante, cuando creemos el módulo Territorial, haremos las relaciones (relationships).
    id_manzana = Column(UUID(as_uuid=True), nullable=False)
    id_estado_predio = Column(UUID(as_uuid=True), nullable=False)
    
    codigo_catastral = Column(String(50), nullable=False, unique=True)
    superficie_mensura = Column(Numeric(12, 2), nullable=False)
    direccion = Column(String)
    
    # La columna geométrica (¡La magia espacial!)
    geom = Column(Geometry(geometry_type='MULTIPOLYGON', srid=32719))
    
    activo = Column(Boolean, default=True)
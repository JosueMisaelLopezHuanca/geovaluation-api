from sqlalchemy import Column, Numeric, DateTime, ForeignKey, text, JSON, String #  Añadimos String
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.core.database import Base

class AvaluoPredio(Base):
    __tablename__ = "avaluo_predio"

    id_avaluo = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    id_gestion = Column(UUID(as_uuid=True), nullable=False)
    id_predio = Column(UUID(as_uuid=True), nullable=False)
    valor_terreno = Column(Numeric(14, 2))
    valor_construccion = Column(Numeric(14, 2), default=0.0)
    valor_total = Column(Numeric(14, 2), nullable=False)
    base_imponible = Column(Numeric(14, 2), nullable=False)
    fecha_calculo = Column(DateTime(timezone=True), server_default=func.current_timestamp())
    # Usamos JSONB como define tu diseño para mejor rendimiento
    parametros_utilizados = Column(JSONB, nullable=False)
    usuario_creador_id = Column(UUID(as_uuid=True), nullable=False)
    usuario_validador_id = Column(UUID(as_uuid=True), nullable=True)
    estado = Column(String(20), nullable=False, default='PENDIENTE')
    
    fecha_calculo = Column(DateTime(timezone=True), server_default=func.now())
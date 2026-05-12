from sqlalchemy import DateTime, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AvaluoPredio(Base):
    __tablename__ = "avaluo_predio"

    id_avaluo: Mapped[str] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    id_gestion: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False)
    id_predio: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False)
    valor_terreno: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    valor_construccion: Mapped[float | None] = mapped_column(
        Numeric(14, 2), nullable=True
    )
    valor_total: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    base_imponible: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    fecha_calculo: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    parametros_utilizados: Mapped[dict] = mapped_column(JSONB, nullable=False)
    usuario_creador_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False)
    usuario_validador_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDIENTE")

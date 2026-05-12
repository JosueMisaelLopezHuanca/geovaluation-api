"""
Engine SÍNCRONO para scripts de importación y mantenimiento.
El app principal usa async (asyncpg), pero geopandas y los
scripts CLI necesitan una conexión síncrona (psycopg2).
"""

from sqlalchemy import create_engine, text
from app.core.config import settings

# Convertir la URL async a sync: asyncpg → psycopg2
SYNC_DATABASE_URL = settings.DATABASE_URL.replace(
    "postgresql+asyncpg://",
    "postgresql://"
)

sync_engine = create_engine(SYNC_DATABASE_URL, echo=False)


def test_connection():
    """Verifica conexión y retorna versión de PostGIS."""
    with sync_engine.connect() as conn:
        version = conn.execute(text("SELECT PostGIS_Version()")).scalar()
        return version

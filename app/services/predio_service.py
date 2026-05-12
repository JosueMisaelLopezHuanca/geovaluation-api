from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

async def obtener_predios(db: AsyncSession):
    result = await db.execute(text("""
        SELECT id_predio, codigo_catastral, superficie_mensura
        FROM predio
        LIMIT 100
    """))
    return [dict(r._mapping) for r in result.fetchall()]


async def obtener_predios_geojson(db: AsyncSession):
    result = await db.execute(text("""
        SELECT jsonb_build_object(
            'type', 'FeatureCollection',
            'features', jsonb_agg(
                jsonb_build_object(
                    'type', 'Feature',
                    'geometry', ST_AsGeoJSON(geom)::jsonb,
                    'properties', jsonb_build_object(
                        'id', id_predio,
                        'codigo', codigo_catastral,
                        'superficie', superficie_mensura
                    )
                )
            )
        )
        FROM predio
    """))
    return result.scalar()
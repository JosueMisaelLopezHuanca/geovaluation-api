from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

async def obtener_manzanas(db: AsyncSession):
    result = await db.execute(text("""
        SELECT id_manzana, codigo_manzana, codigo_interno
        FROM manzana
        LIMIT 100
    """))
    return [dict(r._mapping) for r in result.fetchall()]


async def obtener_manzanas_geojson(db: AsyncSession):
    result = await db.execute(text("""
        SELECT jsonb_build_object(
            'type', 'FeatureCollection',
            'features', jsonb_agg(
                jsonb_build_object(
                    'type', 'Feature',
                    'geometry', ST_AsGeoJSON(geom)::jsonb,
                    'properties', jsonb_build_object(
                        'id', id_manzana,
                        'codigo', codigo_manzana
                    )
                )
            )
        )
        FROM manzana
    """))
    return result.scalar()
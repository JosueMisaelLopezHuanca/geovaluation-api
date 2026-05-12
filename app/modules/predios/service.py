from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

async def get_predios_bbox(db: AsyncSession, xmin, ymin, xmax, ymax, limit):
    sql = text("""
        SELECT jsonb_build_object(
            'type','FeatureCollection',
            'features', jsonb_agg(f)
        )
        FROM (
            SELECT jsonb_build_object(
                'type','Feature',
                'geometry', ST_AsGeoJSON(
                    ST_Simplify(geom, 0.5)
                )::jsonb,
                'properties', jsonb_build_object(
                    'id', id_predio,
                    'codigo', codigo_catastral
                )
            ) AS f
            FROM predio
            WHERE geom && ST_MakeEnvelope(:xmin, :ymin, :xmax, :ymax, 32719)
            LIMIT :limit
        ) sub;
    """)

    result = await db.execute(sql, {
        "xmin": xmin,
        "ymin": ymin,
        "xmax": xmax,
        "ymax": ymax,
        "limit": limit
    })

    return result.scalar()
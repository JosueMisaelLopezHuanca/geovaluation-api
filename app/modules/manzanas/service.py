from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

async def get_manzanas_bbox(db: AsyncSession, xmin, ymin, xmax, ymax):
    sql = text("""
        SELECT jsonb_build_object(
            'type','FeatureCollection',
            'features', jsonb_agg(f)
        )
        FROM (
            SELECT jsonb_build_object(
                'type','Feature',
                'geometry', ST_AsGeoJSON(
                    ST_Simplify(geom, 1)
                )::jsonb,
                'properties', jsonb_build_object(
                    'id', id_manzana,
                    'codigo', codigo_manzana
                )
            ) AS f
            FROM manzana
            WHERE geom && ST_MakeEnvelope(:xmin, :ymin, :xmax, :ymax, 32719)
        ) sub;
    """)

    result = await db.execute(sql, {
        "xmin": xmin,
        "ymin": ymin,
        "xmax": xmax,
        "ymax": ymax
    })

    return result.scalar()
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def fetch_predios_bbox(
    db: AsyncSession,
    xmin: float,
    ymin: float,
    xmax: float,
    ymax: float,
    limit: int,
    input_srid: int,
    output_srid: int,
):
    sql = text(
        """
        SELECT jsonb_build_object(
            'type', 'FeatureCollection',
            'features', COALESCE(jsonb_agg(f), '[]'::jsonb)
        )
        FROM (
            SELECT jsonb_build_object(
                'type', 'Feature',
                'geometry', ST_AsGeoJSON(
                    CASE
                        WHEN :output_srid = 32719 THEN ST_Simplify(geom, 0.5)
                        ELSE ST_Transform(ST_Simplify(geom, 0.5), :output_srid)
                    END
                )::jsonb,
                'properties', jsonb_build_object(
                    'id', id_predio,
                    'codigo', codigo_catastral
                )
            ) AS f
            FROM predio
            WHERE geom && CASE
                WHEN :input_srid = 32719 THEN ST_MakeEnvelope(:xmin, :ymin, :xmax, :ymax, 32719)
                ELSE ST_Transform(ST_MakeEnvelope(:xmin, :ymin, :xmax, :ymax, :input_srid), 32719)
            END
            LIMIT :limit
        ) sub;
        """
    )

    result = await db.execute(
        sql,
        {
            "xmin": xmin,
            "ymin": ymin,
            "xmax": xmax,
            "ymax": ymax,
            "limit": limit,
            "input_srid": input_srid,
            "output_srid": output_srid,
        },
    )
    return result.scalar()

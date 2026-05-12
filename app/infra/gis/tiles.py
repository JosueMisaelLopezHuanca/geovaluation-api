from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def get_tile(db: AsyncSession, z: int, x: int, y: int):
    sql = text(
        """
        WITH
        bounds AS (
            SELECT ST_TileEnvelope(:z, :x, :y) AS geom
        ),
        bounds_32719 AS (
            SELECT ST_Transform(ST_TileEnvelope(:z, :x, :y), 32719) AS geom
        ),
        predios AS (
            SELECT
                ST_AsMVTGeom(
                    ST_Transform(p.geom, 3857),
                    bounds.geom,
                    4096,
                    256,
                    true
                ) AS geom,
                p.codigo_catastral,
                'predio' AS tipo
            FROM predio p, bounds, bounds_32719
            WHERE p.geom && bounds_32719.geom
        ),
        manzanas AS (
            SELECT
                ST_AsMVTGeom(
                    ST_Transform(m.geom, 3857),
                    bounds.geom,
                    4096,
                    256,
                    true
                ) AS geom,
                m.codigo_interno AS codigo_catastral,
                'manzana' AS tipo
            FROM manzana m, bounds, bounds_32719
            WHERE m.geom && bounds_32719.geom
        ),
        union_geom AS (
            SELECT * FROM predios
            UNION ALL
            SELECT * FROM manzanas
        )
        SELECT ST_AsMVT(union_geom, 'avalix', 4096, 'geom')
        FROM union_geom;
        """
    )

    result = await db.execute(sql, {"z": z, "x": x, "y": y})
    tile = result.scalar()
    return tile if tile else b""

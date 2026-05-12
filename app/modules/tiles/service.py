from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


async def get_tile(db: AsyncSession, z: int, x: int, y: int):
    sql = text("""
    WITH
    -- Caja original en 3857 (Web Mercator) que pide Leaflet
    bounds AS (
        SELECT ST_TileEnvelope(:z, :x, :y) AS geom
    ),
    -- Caja transformada a 32719 para usar tus índices espaciales rápido
    bounds_32719 AS (
        SELECT ST_Transform(ST_TileEnvelope(:z, :x, :y), 32719) AS geom
    ),

    -- =========================
    -- PREDIOS
    -- =========================
    predios AS (
        SELECT
            ST_AsMVTGeom(
                ST_Transform(p.geom, 3857), -- 🔥 Se transforma a 3857 para dibujar
                bounds.geom,                -- 🔥 Usa la caja original 3857
                4096,
                256,
                true
            ) AS geom,
            p.codigo_catastral,
            'predio' AS tipo
        FROM predio p, bounds, bounds_32719
        WHERE p.geom && bounds_32719.geom   -- 🔥 Filtra usando 32719 (¡Rapidísimo!)
    ),

    -- =========================
    -- MANZANAS
    -- =========================
    manzanas AS (
        SELECT
            ST_AsMVTGeom(
                ST_Transform(m.geom, 3857), -- 🔥 Se transforma a 3857 para dibujar
                bounds.geom,                -- 🔥 Usa la caja original 3857
                4096,
                256,
                true
            ) AS geom,
            m.codigo_interno AS codigo_catastral,
            'manzana' AS tipo
        FROM manzana m, bounds, bounds_32719
        WHERE m.geom && bounds_32719.geom   -- 🔥 Filtra usando 32719
    ),

    -- =========================
    -- UNIÓN
    -- =========================
    union_geom AS (
        SELECT * FROM predios
        UNION ALL
        SELECT * FROM manzanas
    )

    SELECT ST_AsMVT(union_geom, 'avalix', 4096, 'geom')
    FROM union_geom;
    """)

    result = await db.execute(sql, {
        "z": z,
        "x": x,
        "y": y
    })

    tile = result.scalar()

    return tile if tile else b""
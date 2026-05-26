from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def table_exists(db: AsyncSession, table_name: str) -> bool:
    result = await db.execute(
        text("SELECT to_regclass(:table_name) IS NOT NULL"),
        {"table_name": table_name},
    )
    return bool(result.scalar())


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


async def fetch_predio_at_point(db: AsyncSession, lng: float, lat: float):
    has_otb_context = await table_exists(db, "predio_otb_contexto")
    otb_name_sql = "ctx.otb_nombre" if has_otb_context else "NULL"
    otb_join_sql = (
        "LEFT JOIN predio_otb_contexto ctx ON ctx.predio_id = p.id_predio"
        if has_otb_context
        else ""
    )
    sql = text(
        f"""
        WITH click_point AS (
            SELECT ST_Transform(ST_SetSRID(ST_MakePoint(:lng, :lat), 4326), 32719) AS geom
        )
        SELECT jsonb_build_object(
            'type', 'FeatureCollection',
            'features', COALESCE(jsonb_agg(f), '[]'::jsonb)
        )
        FROM (
            SELECT jsonb_build_object(
                'type', 'Feature',
                'geometry', ST_AsGeoJSON(ST_Simplify(p.geom, 0.5))::jsonb,
                'properties', jsonb_build_object(
                    'id', p.id_predio,
                    'codigo', p.codigo_catastral,
                    'otb_nombre', {otb_name_sql},
                    'match_origen', 'map_click',
                    'superficie_gis', p.superficie_mensura,
                    'superficie_legal', p.superficie_titulo,
                    'centroide_lat', ST_Y(ST_Transform(ST_PointOnSurface(p.geom), 4326)),
                    'centroide_lng', ST_X(ST_Transform(ST_PointOnSurface(p.geom), 4326))
                )
            ) AS f
            FROM predio p
            CROSS JOIN click_point cp
            {otb_join_sql}
            WHERE p.geom && cp.geom
              AND ST_Intersects(p.geom, cp.geom)
            ORDER BY ST_Area(p.geom) ASC, p.codigo_catastral
            LIMIT 1
        ) sub;
        """
    )
    result = await db.execute(sql, {"lng": lng, "lat": lat})
    return result.scalar() or {"type": "FeatureCollection", "features": []}


async def list_otbs(db: AsyncSession, limit: int, query: str | None = None):
    if not await table_exists(db, "staging_otbs"):
        return {"items": []}

    trimmed_query = (query or "").strip()
    sql = text(
        """
        SELECT COALESCE(
            jsonb_agg(
                jsonb_build_object(
                    'nombre', nombre
                )
                ORDER BY nombre
            ),
            '[]'::jsonb
        )
        FROM (
            SELECT DISTINCT NULLIF(TRIM("NOM_OTB"), '') AS nombre
            FROM staging_otbs
            WHERE NULLIF(TRIM("NOM_OTB"), '') IS NOT NULL
              AND (:query = '' OR "NOM_OTB" ILIKE :like_query)
            ORDER BY NULLIF(TRIM("NOM_OTB"), '')
            LIMIT :limit
        ) options
        """
    )
    result = await db.execute(
        sql,
        {
            "query": trimmed_query,
            "like_query": f"%{trimmed_query}%",
            "limit": limit,
        },
    )
    return {"items": result.scalar() or []}


async def fetch_otb_feature_by_name(db: AsyncSession, name: str):
    if not await table_exists(db, "staging_otbs"):
        return {"type": "FeatureCollection", "features": []}

    sql = text(
        """
        SELECT jsonb_build_object(
            'type', 'FeatureCollection',
            'features', COALESCE(jsonb_agg(f), '[]'::jsonb)
        )
        FROM (
            SELECT jsonb_build_object(
                'type', 'Feature',
                'geometry', ST_AsGeoJSON(ST_SimplifyPreserveTopology(geometry, 1.5))::jsonb,
                'properties', jsonb_build_object(
                    'codigo', NULLIF(TRIM("NOM_OTB"), ''),
                    'nombre', NULLIF(TRIM("NOM_OTB"), ''),
                    'capa', 'otbs'
                )
            ) AS f
            FROM staging_otbs
            WHERE NULLIF(TRIM("NOM_OTB"), '') = :name
            LIMIT 1
        ) sub
        """
    )
    result = await db.execute(sql, {"name": name.strip()})
    return result.scalar() or {"type": "FeatureCollection", "features": []}


async def search_predios(db: AsyncSession, query: str, limit: int, otb_name: str | None = None):
    has_otb_context = await table_exists(db, "predio_otb_contexto")
    if has_otb_context:
        return await search_predios_with_otb_context(db, query, limit, otb_name)

    has_otbs = await table_exists(db, "staging_otbs")
    if has_otbs:
        return await search_predios_with_otbs(db, query, limit, otb_name)

    return await search_predios_basic(db, query, limit)


async def search_predios_basic(db: AsyncSession, query: str, limit: int):
    if not query.strip():
        return {"type": "FeatureCollection", "features": []}

    like_query = f"%{query.strip()}%"
    sql = text(
        """
        SELECT jsonb_build_object(
            'type', 'FeatureCollection',
            'features', COALESCE(jsonb_agg(f), '[]'::jsonb)
        )
        FROM (
            SELECT jsonb_build_object(
                'type', 'Feature',
                'geometry', ST_AsGeoJSON(ST_Simplify(geom, 0.5))::jsonb,
                'properties', jsonb_build_object(
                    'id', id_predio,
                    'codigo', codigo_catastral,
                    'otb_nombre', NULL,
                    'match_origen', 'predio',
                    'superficie_gis', superficie_mensura,
                    'superficie_legal', superficie_titulo,
                    'centroide_lat', ST_Y(ST_Transform(ST_PointOnSurface(geom), 4326)),
                    'centroide_lng', ST_X(ST_Transform(ST_PointOnSurface(geom), 4326))
                )
            ) AS f
            FROM predio
            WHERE codigo_catastral ILIKE :query
               OR CAST(id_predio AS VARCHAR) ILIKE :query
            ORDER BY
                CASE
                    WHEN codigo_catastral = :exact_query THEN 0
                    WHEN codigo_catastral ILIKE :prefix_query THEN 1
                    ELSE 2
                END,
                codigo_catastral
            LIMIT :limit
        ) sub;
        """
    )
    result = await db.execute(
        sql,
        {
            "query": like_query,
            "exact_query": query.strip(),
            "prefix_query": f"{query.strip()}%",
            "limit": limit,
        },
    )
    return result.scalar()


async def search_predios_with_otb_context(
    db: AsyncSession,
    query: str,
    limit: int,
    otb_name: str | None = None,
):
    stripped_query = query.strip()
    selected_otb_name = (otb_name or "").strip()

    if not stripped_query and selected_otb_name:
        return await search_predios_by_selected_otb_context(db, selected_otb_name, limit)

    if not stripped_query:
        return {"type": "FeatureCollection", "features": []}

    like_query = f"%{stripped_query}%"
    prefix_query = f"{stripped_query}%"
    sql = text(
        """
        WITH matched_otbs AS (
            SELECT DISTINCT otb_nombre
            FROM predio_otb_contexto
            WHERE otb_nombre ILIKE :query
            ORDER BY otb_nombre
            LIMIT 12
        ),
        direct_matches AS (
            SELECT
                p.id_predio,
                p.codigo_catastral,
                p.geom,
                p.superficie_mensura,
                p.superficie_titulo,
                ctx.otb_nombre,
                CASE
                    WHEN p.codigo_catastral = :exact_query THEN 0
                    WHEN p.codigo_catastral ILIKE :prefix_query THEN 1
                    ELSE 2
                END AS match_rank,
                'predio' AS match_origen
            FROM predio p
            LEFT JOIN predio_otb_contexto ctx ON ctx.predio_id = p.id_predio
            WHERE (
                    p.codigo_catastral ILIKE :query
                    OR CAST(p.id_predio AS VARCHAR) ILIKE :query
                  )
              AND (
                    :selected_otb_name = ''
                    OR ctx.otb_nombre = :selected_otb_name
                  )
            LIMIT :direct_limit
        ),
        otb_matches AS (
            SELECT
                p.id_predio,
                p.codigo_catastral,
                p.geom,
                p.superficie_mensura,
                p.superficie_titulo,
                ctx.otb_nombre,
                CASE
                    WHEN ctx.otb_nombre ILIKE :prefix_query THEN 3
                    ELSE 4
                END AS match_rank,
                'otb' AS match_origen
            FROM matched_otbs mo
            JOIN predio_otb_contexto ctx ON ctx.otb_nombre = mo.otb_nombre
            JOIN predio p ON p.id_predio = ctx.predio_id
            ORDER BY ctx.otb_nombre, p.codigo_catastral
            LIMIT :otb_limit
        ),
        ranked AS (
            SELECT DISTINCT ON (id_predio)
                id_predio,
                codigo_catastral,
                geom,
                superficie_mensura,
                superficie_titulo,
                otb_nombre,
                match_rank,
                match_origen
            FROM (
                SELECT * FROM direct_matches
                UNION ALL
                SELECT * FROM otb_matches
            ) candidates
            ORDER BY id_predio, match_rank, codigo_catastral
        )
        SELECT jsonb_build_object(
            'type', 'FeatureCollection',
            'features', COALESCE(jsonb_agg(f), '[]'::jsonb)
        )
        FROM (
            SELECT jsonb_build_object(
                'type', 'Feature',
                'geometry', ST_AsGeoJSON(ST_Simplify(geom, 0.5))::jsonb,
                'properties', jsonb_build_object(
                    'id', id_predio,
                    'codigo', codigo_catastral,
                    'otb_nombre', otb_nombre,
                    'match_origen', match_origen,
                    'superficie_gis', superficie_mensura,
                    'superficie_legal', superficie_titulo,
                    'centroide_lat', ST_Y(ST_Transform(ST_PointOnSurface(geom), 4326)),
                    'centroide_lng', ST_X(ST_Transform(ST_PointOnSurface(geom), 4326))
                )
            ) AS f
            FROM ranked
            ORDER BY match_rank, codigo_catastral
            LIMIT :limit
        ) sub;
        """
    )
    result = await db.execute(
        sql,
        {
            "query": like_query,
            "exact_query": stripped_query,
            "prefix_query": prefix_query,
            "limit": limit,
            "direct_limit": limit,
            "otb_limit": max(limit * 4, 24),
            "selected_otb_name": selected_otb_name,
        },
    )
    return result.scalar()


async def search_predios_by_selected_otb_context(
    db: AsyncSession,
    selected_otb_name: str,
    limit: int,
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
                'geometry', ST_AsGeoJSON(ST_Simplify(p.geom, 0.5))::jsonb,
                'properties', jsonb_build_object(
                    'id', p.id_predio,
                    'codigo', p.codigo_catastral,
                    'otb_nombre', ctx.otb_nombre,
                    'match_origen', 'otb',
                    'superficie_gis', p.superficie_mensura,
                    'superficie_legal', p.superficie_titulo,
                    'centroide_lat', ST_Y(ST_Transform(ST_PointOnSurface(p.geom), 4326)),
                    'centroide_lng', ST_X(ST_Transform(ST_PointOnSurface(p.geom), 4326))
                )
            ) AS f
            FROM predio_otb_contexto ctx
            JOIN predio p ON p.id_predio = ctx.predio_id
            WHERE ctx.otb_nombre = :selected_otb_name
            ORDER BY p.codigo_catastral
            LIMIT :limit
        ) sub;
        """
    )
    result = await db.execute(
        sql,
        {
            "selected_otb_name": selected_otb_name,
            "limit": limit,
        },
    )
    return result.scalar() or {"type": "FeatureCollection", "features": []}


async def search_predios_with_otbs(
    db: AsyncSession,
    query: str,
    limit: int,
    otb_name: str | None = None,
):
    stripped_query = query.strip()
    selected_otb_name = (otb_name or "").strip()

    if not stripped_query and selected_otb_name:
        return await search_predios_by_selected_otb(db, selected_otb_name, limit)

    if not stripped_query:
        return {"type": "FeatureCollection", "features": []}

    like_query = f"%{stripped_query}%"
    prefix_query = f"{stripped_query}%"
    sql = text(
        """
        WITH selected_otb AS (
            SELECT geometry
            FROM staging_otbs
            WHERE :selected_otb_name <> ''
              AND NULLIF(TRIM("NOM_OTB"), '') = :selected_otb_name
            LIMIT 1
        ),
        matched_otbs AS (
            SELECT
                NULLIF(TRIM("NOM_OTB"), '') AS otb_nombre,
                geometry
            FROM staging_otbs
            WHERE "NOM_OTB" ILIKE :query
            ORDER BY
                CASE
                    WHEN "NOM_OTB" ILIKE :prefix_query THEN 0
                    ELSE 1
                END,
                "NOM_OTB"
            LIMIT 12
        ),
        direct_matches AS (
            SELECT
                p.id_predio,
                p.codigo_catastral,
                p.geom,
                p.superficie_mensura,
                p.superficie_titulo,
                otb.otb_nombre,
                CASE
                    WHEN p.codigo_catastral = :exact_query THEN 0
                    WHEN p.codigo_catastral ILIKE :prefix_query THEN 1
                    ELSE 2
                END AS match_rank,
                'predio' AS match_origen
            FROM predio p
            LEFT JOIN LATERAL (
                SELECT NULLIF(TRIM(o."NOM_OTB"), '') AS otb_nombre
                FROM staging_otbs o
                WHERE o.geometry && ST_PointOnSurface(p.geom)
                  AND ST_Intersects(o.geometry, ST_PointOnSurface(p.geom))
                ORDER BY o."NOM_OTB"
                LIMIT 1
            ) otb ON TRUE
            WHERE (
                    p.codigo_catastral ILIKE :query
                    OR CAST(p.id_predio AS VARCHAR) ILIKE :query
                  )
              AND (
                    :selected_otb_name = ''
                    OR EXISTS (
                        SELECT 1
                        FROM selected_otb so
                        WHERE p.geom && so.geometry
                          AND ST_Intersects(ST_PointOnSurface(p.geom), so.geometry)
                    )
              )
            LIMIT :direct_limit
        ),
        otb_matches AS (
            SELECT
                p.id_predio,
                p.codigo_catastral,
                p.geom,
                p.superficie_mensura,
                p.superficie_titulo,
                mo.otb_nombre,
                CASE
                    WHEN mo.otb_nombre ILIKE :prefix_query THEN 3
                    ELSE 4
                END AS match_rank,
                'otb' AS match_origen
            FROM matched_otbs mo
            JOIN predio p
              ON p.geom && mo.geometry
             AND ST_Intersects(ST_PointOnSurface(p.geom), mo.geometry)
            ORDER BY mo.otb_nombre, p.codigo_catastral
            LIMIT :otb_limit
        ),
        ranked AS (
            SELECT DISTINCT ON (id_predio)
                id_predio,
                codigo_catastral,
                geom,
                superficie_mensura,
                superficie_titulo,
                otb_nombre,
                match_rank,
                match_origen
            FROM (
                SELECT * FROM direct_matches
                UNION ALL
                SELECT * FROM otb_matches
            ) candidates
            ORDER BY id_predio, match_rank, codigo_catastral
        )
        SELECT jsonb_build_object(
            'type', 'FeatureCollection',
            'features', COALESCE(jsonb_agg(f), '[]'::jsonb)
        )
        FROM (
            SELECT jsonb_build_object(
                'type', 'Feature',
                'geometry', ST_AsGeoJSON(ST_Simplify(geom, 0.5))::jsonb,
                'properties', jsonb_build_object(
                    'id', id_predio,
                    'codigo', codigo_catastral,
                    'otb_nombre', otb_nombre,
                    'match_origen', match_origen,
                    'superficie_gis', superficie_mensura,
                    'superficie_legal', superficie_titulo,
                    'centroide_lat', ST_Y(ST_Transform(ST_PointOnSurface(geom), 4326)),
                    'centroide_lng', ST_X(ST_Transform(ST_PointOnSurface(geom), 4326))
                )
            ) AS f
            FROM ranked
            ORDER BY match_rank, codigo_catastral
            LIMIT :limit
        ) sub;
        """
    )
    result = await db.execute(
        sql,
        {
            "query": like_query,
            "exact_query": stripped_query,
            "prefix_query": prefix_query,
            "limit": limit,
            "direct_limit": limit,
            "otb_limit": max(limit * 4, 24),
            "selected_otb_name": selected_otb_name,
        },
    )
    return result.scalar()


async def search_predios_by_selected_otb(db: AsyncSession, selected_otb_name: str, limit: int):
    sql = text(
        """
        WITH selected_otb AS (
            SELECT geometry
            FROM staging_otbs
            WHERE NULLIF(TRIM("NOM_OTB"), '') = :selected_otb_name
            LIMIT 1
        )
        SELECT jsonb_build_object(
            'type', 'FeatureCollection',
            'features', COALESCE(jsonb_agg(f), '[]'::jsonb)
        )
        FROM (
            SELECT jsonb_build_object(
                'type', 'Feature',
                'geometry', ST_AsGeoJSON(ST_Simplify(p.geom, 0.5))::jsonb,
                'properties', jsonb_build_object(
                    'id', p.id_predio,
                    'codigo', p.codigo_catastral,
                    'otb_nombre', :selected_otb_name,
                    'match_origen', 'otb',
                    'superficie_gis', p.superficie_mensura,
                    'superficie_legal', p.superficie_titulo,
                    'centroide_lat', ST_Y(ST_Transform(ST_PointOnSurface(p.geom), 4326)),
                    'centroide_lng', ST_X(ST_Transform(ST_PointOnSurface(p.geom), 4326))
                )
            ) AS f
            FROM predio p
            WHERE EXISTS (
                SELECT 1
                FROM selected_otb so
                WHERE p.geom && so.geometry
                  AND ST_Intersects(ST_PointOnSurface(p.geom), so.geometry)
            )
            ORDER BY p.codigo_catastral
            LIMIT :limit
        ) sub;
        """
    )
    result = await db.execute(
        sql,
        {
            "selected_otb_name": selected_otb_name,
            "limit": limit,
        },
    )
    return result.scalar() or {"type": "FeatureCollection", "features": []}

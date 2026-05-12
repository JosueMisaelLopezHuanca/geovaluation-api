from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.avaluos.models import AvaluoPredio


async def get_gestion_id(db: AsyncSession, anio: int):
    result = await db.execute(
        text("SELECT id_gestion FROM gestion WHERE anio = :anio LIMIT 1"),
        {"anio": anio},
    )
    return result.scalar()


async def get_usuario_id(db: AsyncSession, nombre_usuario: str):
    result = await db.execute(
        text(
            "SELECT id_usuario FROM usuario WHERE nombre_usuario = :nombre_usuario LIMIT 1"
        ),
        {"nombre_usuario": nombre_usuario},
    )
    return result.scalar()


async def fetch_avaluos(db: AsyncSession, *, limit: int):
    result = await db.execute(
        text(
            """
            SELECT
                ap.id_avaluo,
                ap.id_predio,
                p.codigo_catastral,
                ap.valor_total,
                ap.base_imponible,
                ap.fecha_calculo,
                ap.estado,
                u.nombre_usuario,
                g.anio AS gestion_anio,
                COALESCE(
                    (ap.parametros_utilizados ->> 'alicuota_impuesto')::numeric,
                    0
                ) AS alicuota_impuesto
            FROM avaluo_predio ap
            LEFT JOIN predio p
                ON p.id_predio = ap.id_predio
            LEFT JOIN usuario u
                ON u.id_usuario = ap.usuario_creador_id
            LEFT JOIN gestion g
                ON g.id_gestion = ap.id_gestion
            ORDER BY ap.fecha_calculo DESC
            LIMIT :limit
            """
        ),
        {"limit": limit},
    )
    return [dict(row._mapping) for row in result.fetchall()]


async def fetch_avaluo_by_id(db: AsyncSession, *, id_avaluo: str):
    result = await db.execute(
        text(
            """
            SELECT
                ap.id_avaluo,
                ap.id_predio,
                ap.valor_terreno,
                ap.valor_construccion,
                ap.valor_total,
                ap.base_imponible,
                ap.fecha_calculo,
                ap.parametros_utilizados,
                ap.estado,
                p.codigo_catastral
            FROM avaluo_predio ap
            LEFT JOIN predio p
                ON p.id_predio = ap.id_predio
            WHERE ap.id_avaluo = :id_avaluo
            LIMIT 1
            """
        ),
        {"id_avaluo": id_avaluo},
    )
    row = result.fetchone()
    return dict(row._mapping) if row else None


async def get_geometry_column(db: AsyncSession, table_name: str) -> str:
    result = await db.execute(
        text(
            """
            SELECT f_geometry_column
            FROM geometry_columns
            WHERE f_table_name = :tabla
            LIMIT 1
            """
        ),
        {"tabla": table_name},
    )
    return result.scalar() or "geometry"


async def get_table_columns(db: AsyncSession, table_name: str) -> set[str]:
    result = await db.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = :tabla
            """
        ),
        {"tabla": table_name},
    )
    return {row[0] for row in result.fetchall()}


async def table_exists(db: AsyncSession, table_name: str) -> bool:
    result = await db.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = :tabla
            )
            """
        ),
        {"tabla": table_name},
    )
    return bool(result.scalar())


def quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


async def fetch_predio_context(
    db: AsyncSession,
    id_predio: str,
    riesgo_geom_col: str,
    pendiente_geom_col: str,
    riesgo_code_col: str,
    riesgo_grade_col: str | None,
    pendiente_code_col: str,
):
    zonas_homogeneas_exists = await table_exists(db, "staging_zonas_homogeneas")
    riesgo_geom_sql = quote_identifier(riesgo_geom_col)
    pendiente_geom_sql = quote_identifier(pendiente_geom_col)
    riesgo_code_sql = quote_identifier(riesgo_code_col)
    riesgo_grade_sql = quote_identifier(riesgo_grade_col) if riesgo_grade_col else None
    pendiente_code_sql = quote_identifier(pendiente_code_col)

    context_table_exists = await table_exists(db, "predio_contexto_espacial")
    if context_table_exists:
        sql = text(
            """
            SELECT
                p.id_predio,
                p.superficie_mensura AS superficie_terreno,
                p.pendiente_grados,
                p.id_zona_valor,
                p.id_material_via,
                mv.nombre AS material_via_nombre,
                mv.orden AS material_via_orden,
                zv.nombre AS zona_valor_nombre,
                zv.macro_zona AS zona_valor_macro_zona,
                zv.subzona_inicio AS zona_valor_subzona_inicio,
                zv.subzona_fin AS zona_valor_subzona_fin,
                zh.zonavalor AS zona_homogenea_codigo,
                zh.grupovalor AS zona_homogenea_grupo,
                ST_AsGeoJSON(ST_Transform(p.geom, 4326)) AS geojson,
                TRUE AS contexto_precalculado,
                ctx.riesgo_codigo,
                ctx.riesgo_grado,
                ctx.pendiente_codigo,
                ctx.pendiente_area_m2,
                ctx.pendiente_cobertura_pct,
                ctx.riesgo_area_m2,
                ctx.riesgo_cobertura_pct,
                COALESCE(svc.servicios, ARRAY[]::VARCHAR[]) AS servicios,
                cons.construcciones_registradas,
                cons.superficie_construida_total
            FROM predio p
            LEFT JOIN material_via mv
                ON mv.id_material_via = p.id_material_via
            LEFT JOIN zona_valor zv
                ON zv.id_zona_valor = p.id_zona_valor
            LEFT JOIN LATERAL (
                SELECT
                    NULLIF(TRIM(zonavalor), '') AS zonavalor,
                    NULLIF(TRIM(grupovalor), '') AS grupovalor
                FROM staging_zonas_homogeneas
                WHERE :zh_exists
                  AND geometry && ST_PointOnSurface(p.geom)
                  AND ST_Intersects(geometry, ST_PointOnSurface(p.geom))
                ORDER BY idzonavalo
                LIMIT 1
            ) zh ON TRUE
            LEFT JOIN predio_contexto_espacial ctx
                ON ctx.id_predio = p.id_predio
            LEFT JOIN LATERAL (
                SELECT ARRAY_AGG(s.nombre ORDER BY s.nombre) AS servicios
                FROM predio_servicio ps
                JOIN servicio s ON s.id_servicio = ps.id_servicio
                WHERE ps.id_predio = p.id_predio
            ) svc ON TRUE
            LEFT JOIN LATERAL (
                SELECT
                    COUNT(*) AS construcciones_registradas,
                    COALESCE(SUM(c.superficie_construida), 0) AS superficie_construida_total
                FROM construccion c
                WHERE c.id_predio = p.id_predio
            ) cons ON TRUE
            WHERE p.id_predio = :id_predio
            LIMIT 1
            """
        )
        result = await db.execute(
            sql, {"id_predio": str(id_predio), "zh_exists": zonas_homogeneas_exists}
        )
        row = result.fetchone()
        return dict(row._mapping) if row else None

    sql = text(
        f"""
        SELECT
            p.id_predio,
            p.superficie_mensura AS superficie_terreno,
            p.pendiente_grados,
            p.id_zona_valor,
            p.id_material_via,
            mv.nombre AS material_via_nombre,
            mv.orden AS material_via_orden,
            zv.nombre AS zona_valor_nombre,
            zv.macro_zona AS zona_valor_macro_zona,
            zv.subzona_inicio AS zona_valor_subzona_inicio,
            zv.subzona_fin AS zona_valor_subzona_fin,
            zh.zonavalor AS zona_homogenea_codigo,
            zh.grupovalor AS zona_homogenea_grupo,
            ST_AsGeoJSON(ST_Transform(p.geom, 4326)) AS geojson,
            FALSE AS contexto_precalculado,
            r.riesgo_codigo,
            r.riesgo_grado,
            pen.pendiente_codigo,
            NULL::numeric AS pendiente_area_m2,
            NULL::numeric AS pendiente_cobertura_pct,
            NULL::numeric AS riesgo_area_m2,
            NULL::numeric AS riesgo_cobertura_pct,
            COALESCE(svc.servicios, ARRAY[]::VARCHAR[]) AS servicios,
            cons.construcciones_registradas,
            cons.superficie_construida_total
        FROM predio p
        LEFT JOIN material_via mv
            ON mv.id_material_via = p.id_material_via
        LEFT JOIN zona_valor zv
            ON zv.id_zona_valor = p.id_zona_valor
        LEFT JOIN LATERAL (
            SELECT
                NULLIF(TRIM(zonavalor), '') AS zonavalor,
                NULLIF(TRIM(grupovalor), '') AS grupovalor
            FROM staging_zonas_homogeneas
            WHERE :zh_exists
              AND geometry && ST_PointOnSurface(p.geom)
              AND ST_Intersects(geometry, ST_PointOnSurface(p.geom))
            ORDER BY idzonavalo
            LIMIT 1
        ) zh ON TRUE
        LEFT JOIN LATERAL (
            SELECT
                src.{riesgo_code_sql} AS riesgo_codigo,
                {f'src.{riesgo_grade_sql} AS riesgo_grado,' if riesgo_grade_sql else 'NULL AS riesgo_grado,'}
                ST_Area(ST_Intersection(p.geom, src.{riesgo_geom_sql})) AS area_interseccion
            FROM staging_riesgos src
            WHERE ST_Intersects(p.geom, src.{riesgo_geom_sql})
            ORDER BY area_interseccion DESC, src.{riesgo_code_sql} DESC
            LIMIT 1
        ) r ON TRUE
        LEFT JOIN LATERAL (
            SELECT
                src.{pendiente_code_sql} AS pendiente_codigo,
                ST_Area(ST_Intersection(p.geom, src.{pendiente_geom_sql})) AS area_interseccion
            FROM staging_pendientes src
            WHERE ST_Intersects(p.geom, src.{pendiente_geom_sql})
            ORDER BY area_interseccion DESC, src.{pendiente_code_sql} DESC
            LIMIT 1
        ) pen ON TRUE
        LEFT JOIN LATERAL (
            SELECT ARRAY_AGG(s.nombre ORDER BY s.nombre) AS servicios
            FROM predio_servicio ps
            JOIN servicio s ON s.id_servicio = ps.id_servicio
            WHERE ps.id_predio = p.id_predio
        ) svc ON TRUE
        LEFT JOIN LATERAL (
            SELECT
                COUNT(*) AS construcciones_registradas,
                COALESCE(SUM(c.superficie_construida), 0) AS superficie_construida_total
            FROM construccion c
            WHERE c.id_predio = p.id_predio
        ) cons ON TRUE
        WHERE p.id_predio = :id_predio
        LIMIT 1
        """
    )
    result = await db.execute(
        sql, {"id_predio": str(id_predio), "zh_exists": zonas_homogeneas_exists}
    )
    row = result.fetchone()
    return dict(row._mapping) if row else None


async def get_latest_esquema_id(db: AsyncSession):
    result = await db.execute(
        text(
            """
            SELECT id_esquema
            FROM esquema_valuacion
            ORDER BY fecha_inicio DESC
            LIMIT 1
            """
        )
    )
    return result.scalar()


async def get_valor_suelo(
    db: AsyncSession,
    *,
    id_esquema,
    id_zona_valor,
    id_material_via,
):
    if not id_esquema or not id_zona_valor or not id_material_via:
        return None

    result = await db.execute(
        text(
            """
            SELECT valor_por_metro_cuadrado
            FROM valor_suelo
            WHERE id_esquema = :id_esquema
              AND id_zona_valor = :id_zona_valor
              AND id_material_via = :id_material_via
            ORDER BY vigencia_desde DESC
            LIMIT 1
            """
        ),
        {
            "id_esquema": id_esquema,
            "id_zona_valor": id_zona_valor,
            "id_material_via": id_material_via,
        },
    )
    value = result.scalar()
    return float(value) if value is not None else None


async def get_factor_servicios(db: AsyncSession, *, id_predio):
    result = await db.execute(
        text(
            """
            SELECT COALESCE(SUM(s.factor_incremento), 0)
            FROM predio_servicio ps
            JOIN servicio s ON s.id_servicio = ps.id_servicio
            WHERE ps.id_predio = :id_predio
            """
        ),
        {"id_predio": id_predio},
    )
    total = result.scalar()
    total = float(total or 0)
    return max(0.2, total)


async def fetch_construcciones_context(
    db: AsyncSession, *, id_predio, id_esquema, gestion_anio: int
):
    result = await db.execute(
        text(
            """
            SELECT
                c.id_construccion,
                c.superficie_construida,
                c.anio_construccion,
                c.numero_bloques,
                c.es_propiedad_horizontal,
                t.codigo AS tipologia_codigo,
                t.valor_por_metro_cuadrado AS valor_tipologia_m2,
                fd.factor_ajuste AS factor_depreciacion
            FROM construccion c
            JOIN tipologia t
                ON t.id_tipologia = c.id_tipologia
            LEFT JOIN factor_depreciacion fd
                ON fd.id_esquema = :id_esquema
               AND fd.id_municipio = t.id_municipio
               AND (
                    :gestion_anio - c.anio_construccion
               ) >= fd.antiguedad_minima
               AND (
                    :gestion_anio - c.anio_construccion
               ) <= fd.antiguedad_maxima
            WHERE c.id_predio = :id_predio
            ORDER BY c.fecha_creacion ASC
            """
        ),
        {
            "id_predio": id_predio,
            "id_esquema": id_esquema,
            "gestion_anio": gestion_anio,
        },
    )
    return [dict(row._mapping) for row in result.fetchall()]


async def fetch_contexto_espacial_stats(db: AsyncSession):
    if not await table_exists(db, "predio_contexto_espacial"):
        return {
            "total_predios": 0,
            "con_pendiente": 0,
            "con_riesgo": 0,
            "pendiente_distribucion": [],
            "riesgo_distribucion": [],
        }

    resumen = await db.execute(
        text(
            """
            SELECT
                COUNT(*) AS total_predios,
                COUNT(*) FILTER (WHERE pendiente_codigo IS NOT NULL) AS con_pendiente,
                COUNT(*) FILTER (WHERE riesgo_codigo IS NOT NULL) AS con_riesgo
            FROM predio_contexto_espacial
            """
        )
    )
    row = resumen.fetchone()

    pendiente_rows = await db.execute(
        text(
            """
            SELECT pendiente_codigo, COUNT(*) AS cantidad
            FROM predio_contexto_espacial
            WHERE pendiente_codigo IS NOT NULL
            GROUP BY pendiente_codigo
            ORDER BY pendiente_codigo
            """
        )
    )

    riesgo_rows = await db.execute(
        text(
            """
            SELECT riesgo_codigo, riesgo_grado, COUNT(*) AS cantidad
            FROM predio_contexto_espacial
            WHERE riesgo_codigo IS NOT NULL
            GROUP BY riesgo_codigo, riesgo_grado
            ORDER BY riesgo_codigo
            """
        )
    )

    return {
        "total_predios": int(row.total_predios or 0),
        "con_pendiente": int(row.con_pendiente or 0),
        "con_riesgo": int(row.con_riesgo or 0),
        "pendiente_distribucion": [
            {"codigo": int(r.pendiente_codigo), "cantidad": int(r.cantidad)}
            for r in pendiente_rows.fetchall()
        ],
        "riesgo_distribucion": [
            {
                "codigo": int(r.riesgo_codigo),
                "grado": r.riesgo_grado,
                "cantidad": int(r.cantidad),
            }
            for r in riesgo_rows.fetchall()
        ],
    }


async def fetch_valuacion_coverage_stats(db: AsyncSession):
    contexto_table_exists = await table_exists(db, "predio_contexto_espacial")
    zonas_homogeneas_exists = await table_exists(db, "staging_zonas_homogeneas")
    contexto_join = (
        "LEFT JOIN predio_contexto_espacial ctx ON ctx.id_predio = p.id_predio"
        if contexto_table_exists
        else ""
    )
    contexto_filter = (
        "ctx.pendiente_codigo IS NOT NULL"
        if contexto_table_exists
        else "FALSE"
    )

    row = (await db.execute(text(
        f"""
            SELECT
                COUNT(*) AS total_predios,
                COUNT(*) FILTER (WHERE {contexto_filter}) AS con_contexto_pendiente,
                COUNT(*) FILTER (WHERE p.id_material_via IS NOT NULL) AS con_material_via,
                COUNT(*) FILTER (WHERE p.id_zona_valor IS NOT NULL) AS con_zona_valor,
                COUNT(*) FILTER (
                    WHERE EXISTS (
                        SELECT 1
                        FROM staging_zonas_homogeneas zh
                        WHERE :zh_exists
                          AND zh.geometry && ST_PointOnSurface(p.geom)
                          AND ST_Intersects(zh.geometry, ST_PointOnSurface(p.geom))
                    )
                ) AS con_zona_homogenea,
                COUNT(*) FILTER (
                    WHERE EXISTS (
                        SELECT 1
                        FROM predio_servicio ps
                        WHERE ps.id_predio = p.id_predio
                    )
                ) AS con_servicios,
                COUNT(*) FILTER (
                    WHERE EXISTS (
                        SELECT 1
                        FROM construccion c
                        WHERE c.id_predio = p.id_predio
                    )
                ) AS con_construccion,
                COUNT(*) FILTER (
                    WHERE p.id_material_via IS NOT NULL
                      AND p.id_zona_valor IS NOT NULL
                      AND {contexto_filter}
                ) AS listos_avaluo_terreno,
                COUNT(*) FILTER (
                    WHERE p.id_material_via IS NOT NULL
                      AND p.id_zona_valor IS NOT NULL
                      AND {contexto_filter}
                      AND EXISTS (
                          SELECT 1
                          FROM construccion c
                          WHERE c.id_predio = p.id_predio
                      )
                ) AS listos_avaluo_integral
            FROM predio p
            {contexto_join}
        """
    ), {"zh_exists": zonas_homogeneas_exists})).fetchone()
    return {
        "total_predios": int(row.total_predios or 0),
        "con_contexto_pendiente": int(row.con_contexto_pendiente or 0),
        "con_material_via": int(row.con_material_via or 0),
        "con_zona_valor": int(row.con_zona_valor or 0),
        "con_zona_homogenea": int(row.con_zona_homogenea or 0),
        "con_servicios": int(row.con_servicios or 0),
        "con_construccion": int(row.con_construccion or 0),
        "listos_avaluo_terreno": int(row.listos_avaluo_terreno or 0),
        "listos_avaluo_integral": int(row.listos_avaluo_integral or 0),
    }


async def fetch_capa_geojson_bbox(
    db: AsyncSession,
    *,
    capa: str,
    xmin: float,
    ymin: float,
    xmax: float,
    ymax: float,
    limit: int,
    input_srid: int,
    output_srid: int,
):
    if capa == "pendientes":
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
                            WHEN :output_srid = 32719 THEN ST_SimplifyPreserveTopology(geometry, 2.0)
                            ELSE ST_Transform(ST_SimplifyPreserveTopology(geometry, 2.0), :output_srid)
                        END
                    )::jsonb,
                    'properties', jsonb_build_object(
                        'codigo', "DN",
                        'capa', 'pendientes'
                    )
                ) AS f
                FROM staging_pendientes
                WHERE geometry && CASE
                    WHEN :input_srid = 32719 THEN ST_MakeEnvelope(:xmin, :ymin, :xmax, :ymax, 32719)
                    ELSE ST_Transform(ST_MakeEnvelope(:xmin, :ymin, :xmax, :ymax, :input_srid), 32719)
                END
                LIMIT :limit
            ) sub
            """
        )
    elif capa == "riesgos":
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
                            WHEN :output_srid = 32719 THEN ST_SimplifyPreserveTopology(geometry, 2.0)
                            ELSE ST_Transform(ST_SimplifyPreserveTopology(geometry, 2.0), :output_srid)
                        END
                    )::jsonb,
                    'properties', jsonb_build_object(
                        'codigo', "GRIDCODE",
                        'grado', "GRADO",
                        'capa', 'riesgos'
                    )
                ) AS f
                FROM staging_riesgos
                WHERE geometry && CASE
                    WHEN :input_srid = 32719 THEN ST_MakeEnvelope(:xmin, :ymin, :xmax, :ymax, 32719)
                    ELSE ST_Transform(ST_MakeEnvelope(:xmin, :ymin, :xmax, :ymax, :input_srid), 32719)
                END
                LIMIT :limit
            ) sub
            """
        )
    elif capa == "zonas_homogeneas":
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
                            WHEN :output_srid = 32719 THEN ST_SimplifyPreserveTopology(geometry, 2.0)
                            ELSE ST_Transform(ST_SimplifyPreserveTopology(geometry, 2.0), :output_srid)
                        END
                    )::jsonb,
                    'properties', jsonb_build_object(
                        'codigo', zonavalor,
                        'grupo', grupovalor,
                        'id_zona_homogenea', idzonavalo,
                        'capa', 'zonas_homogeneas'
                    )
                ) AS f
                FROM staging_zonas_homogeneas
                WHERE geometry && CASE
                    WHEN :input_srid = 32719 THEN ST_MakeEnvelope(:xmin, :ymin, :xmax, :ymax, 32719)
                    ELSE ST_Transform(ST_MakeEnvelope(:xmin, :ymin, :xmax, :ymax, :input_srid), 32719)
                END
                LIMIT :limit
            ) sub
            """
        )
    else:
        raise ValueError(f"Capa no soportada: {capa}")

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
    return result.scalar() or {"type": "FeatureCollection", "features": []}


async def save_avaluo_predio(
    db: AsyncSession,
    *,
    id_gestion,
    id_predio,
    usuario_creador_id,
    valor_terreno: float,
    valor_construccion: float,
    valor_total: float,
    base_imponible: float,
    parametros_utilizados: dict,
):
    nuevo_avaluo = AvaluoPredio(
        id_gestion=id_gestion,
        id_predio=id_predio,
        valor_terreno=valor_terreno,
        valor_construccion=valor_construccion,
        valor_total=valor_total,
        base_imponible=base_imponible,
        usuario_creador_id=usuario_creador_id,
        estado="PENDIENTE",
        parametros_utilizados=parametros_utilizados,
    )
    db.add(nuevo_avaluo)
    await db.commit()
    await db.refresh(nuevo_avaluo)
    return nuevo_avaluo

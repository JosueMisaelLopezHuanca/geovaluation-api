import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def get_normative_version(db: AsyncSession, gestion_anio: int):
    row = (
        await db.execute(
            text(
                """
                SELECT normative_version_id, gestion_anio, version_codigo
                FROM normative_version
                WHERE gestion_anio = :gestion_anio
                  AND estado = 'ACTIVE'
                ORDER BY vigente_desde DESC
                LIMIT 1
                """
            ),
            {"gestion_anio": gestion_anio},
        )
    ).fetchone()
    return dict(row._mapping) if row else None


async def get_usuario_id(db: AsyncSession, nombre_usuario: str):
    row = (
        await db.execute(
            text(
                """
                SELECT id_usuario
                FROM usuario
                WHERE nombre_usuario = :nombre_usuario
                LIMIT 1
                """
            ),
            {"nombre_usuario": nombre_usuario},
        )
    ).fetchone()
    return row[0] if row else None


async def get_gestion_id(db: AsyncSession, gestion_anio: int):
    row = (
        await db.execute(
            text("SELECT id_gestion FROM gestion WHERE anio = :anio LIMIT 1"),
            {"anio": gestion_anio},
        )
    ).fetchone()
    return row[0] if row else None


async def fetch_predio_gis_context(db: AsyncSession, predio_id: str):
    row = (
        await db.execute(
            text(
                """
                SELECT
                    p.id_predio,
                    p.superficie_mensura AS superficie_gis,
                    p.superficie_titulo AS superficie_legal,
                    p.codigo_catastral,
                    mv.nombre AS material_via_codigo,
                    COALESCE(zt.codigo, zv.nombre) AS zona_tributaria_codigo,
                    ctx.pendiente_codigo,
                    p.pendiente_grados,
                    ctx.riesgo_codigo,
                    ctx.riesgo_grado,
                    ctx.pendiente_cobertura_pct,
                    ctx.riesgo_cobertura_pct,
                    zh.zonavalor AS zona_homogenea_codigo,
                    zh.grupovalor AS zona_homogenea_grupo,
                    COALESCE(svc.servicios, ARRAY[]::VARCHAR[]) AS servicios_oficiales
                FROM predio p
                LEFT JOIN material_via mv ON mv.id_material_via = p.id_material_via
                LEFT JOIN zona_valor zv ON zv.id_zona_valor = p.id_zona_valor
                LEFT JOIN zona_tributaria zt ON zt.id_zona_tributaria = zv.id_zona_tributaria
                LEFT JOIN predio_contexto_espacial ctx ON ctx.id_predio = p.id_predio
                LEFT JOIN LATERAL (
                    SELECT
                        NULLIF(TRIM(zonavalor), '') AS zonavalor,
                        NULLIF(TRIM(grupovalor), '') AS grupovalor
                    FROM staging_zonas_homogeneas
                    WHERE geometry && ST_PointOnSurface(p.geom)
                      AND ST_Intersects(geometry, ST_PointOnSurface(p.geom))
                    ORDER BY idzonavalo
                    LIMIT 1
                ) zh ON TRUE
                LEFT JOIN LATERAL (
                    SELECT ARRAY_AGG(s.nombre ORDER BY s.nombre) AS servicios
                    FROM predio_servicio ps
                    JOIN servicio s ON s.id_servicio = ps.id_servicio
                    WHERE ps.id_predio = p.id_predio
                ) svc ON TRUE
                WHERE p.id_predio = :predio_id
                LIMIT 1
                """
            ),
            {"predio_id": predio_id},
        )
    ).fetchone()
    return dict(row._mapping) if row else None


async def get_surface_override(db: AsyncSession, predio_id: str):
    row = (
        await db.execute(
            text(
                """
                SELECT superficie_manual, motivo, created_at
                FROM predio_superficie_override
                WHERE predio_id = :predio_id
                  AND vigente = TRUE
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"predio_id": predio_id},
        )
    ).fetchone()
    return dict(row._mapping) if row else None


async def get_official_land_value(
    db: AsyncSession, normative_version_id: str, zona_tributaria_codigo: str, material_via_codigo: str
):
    row = (
        await db.execute(
            text(
                """
                SELECT valor_m2
                FROM tabla_zonas_valor
                WHERE normative_version_id = :normative_version_id
                  AND zona_tributaria_codigo = :zona_tributaria_codigo
                  AND material_via_codigo = :material_via_codigo
                  AND activo = TRUE
                LIMIT 1
                """
            ),
            {
                "normative_version_id": normative_version_id,
                "zona_tributaria_codigo": zona_tributaria_codigo,
                "material_via_codigo": material_via_codigo,
            },
        )
    ).fetchone()
    return float(row[0]) if row else None


async def get_official_pendiente_factor(db: AsyncSession, normative_version_id: str, pendiente_grados: float | None):
    if pendiente_grados is None:
        return 1.0
    row = (
        await db.execute(
            text(
                """
                SELECT factor
                FROM tabla_factores_pendiente
                WHERE normative_version_id = :normative_version_id
                  AND :pendiente_grados >= rango_min
                  AND :pendiente_grados <= rango_max
                  AND activo = TRUE
                ORDER BY rango_min
                LIMIT 1
                """
            ),
            {
                "normative_version_id": normative_version_id,
                "pendiente_grados": pendiente_grados,
            },
        )
    ).fetchone()
    return float(row[0]) if row else 1.0


async def get_alicuota(db: AsyncSession, normative_version_id: str):
    row = (
        await db.execute(
            text(
                """
                SELECT alicuota
                FROM tabla_alicuota_impuesto
                WHERE normative_version_id = :normative_version_id
                  AND codigo = 'PREDIAL_BASE'
                  AND activo = TRUE
                LIMIT 1
                """
            ),
            {"normative_version_id": normative_version_id},
        )
    ).fetchone()
    return float(row[0]) if row else None


async def resolve_tipologia_constructiva(db: AsyncSession, normative_version_id: str, calidad: str):
    row = (
        await db.execute(
            text(
                """
                SELECT tipologia_constructiva_id, calidad, categoria, valor_m2, tipologia_origen_codigo
                FROM tabla_tipologias_constructivas
                WHERE normative_version_id = :normative_version_id
                  AND calidad = :calidad
                  AND activo = TRUE
                ORDER BY
                    CASE categoria
                        WHEN 'PREDIO' THEN 0
                        ELSE 1
                    END,
                    valor_m2 DESC
                LIMIT 1
                """
            ),
            {
                "normative_version_id": normative_version_id,
                "calidad": calidad.upper(),
            },
        )
    ).fetchone()
    return dict(row._mapping) if row else None


async def resolve_depreciacion_factor(db: AsyncSession, normative_version_id: str, edad: int):
    row = (
        await db.execute(
            text(
                """
                SELECT factor
                FROM tabla_depreciacion_antiguedad
                WHERE normative_version_id = :normative_version_id
                  AND :edad >= edad_min
                  AND :edad <= edad_max
                ORDER BY edad_min
                LIMIT 1
                """
            ),
            {"normative_version_id": normative_version_id, "edad": edad},
        )
    ).fetchone()
    return float(row[0]) if row else 1.0


async def save_surface_override(
    db: AsyncSession,
    *,
    predio_id: str,
    superficie_gis: float | None,
    superficie_legal: float | None,
    superficie_manual: float,
    motivo: str,
    usuario_id: str,
):
    await db.execute(
        text("UPDATE predio_superficie_override SET vigente = FALSE WHERE predio_id = :predio_id"),
        {"predio_id": predio_id},
    )
    await db.execute(
        text(
            """
            INSERT INTO predio_superficie_override (
                predio_id, superficie_gis, superficie_legal, superficie_manual, motivo, usuario_id, vigente
            ) VALUES (
                :predio_id, :superficie_gis, :superficie_legal, :superficie_manual, :motivo, :usuario_id, TRUE
            )
            """
        ),
        {
            "predio_id": predio_id,
            "superficie_gis": superficie_gis,
            "superficie_legal": superficie_legal,
            "superficie_manual": superficie_manual,
            "motivo": motivo,
            "usuario_id": usuario_id,
        },
    )


async def save_appraisal_case_and_result(
    db: AsyncSession,
    *,
    predio_id: str,
    gestion_id: str | None,
    normative_version_id: str,
    usuario_id: str,
    superficie_gis: float,
    superficie_legal: float | None,
    superficie_manual: float | None,
    superficie_calculo: float,
    superficie_override_reason: str | None,
    observaciones: str | None,
    valor_terreno: float,
    valor_construccion: float,
    base_imponible: float,
    impuesto_estimado: float,
    alicuota: float,
    bloques: list[dict],
    trace_payload: dict,
):
    appraisal_row = (
        await db.execute(
            text(
                """
                INSERT INTO appraisal_case (
                    predio_id, gestion_id, normative_version_id, status, initiated_by,
                    calculation_mode, superficie_gis, superficie_legal, superficie_manual,
                    superficie_calculo, superficie_override_reason, observaciones, finalized_at
                ) VALUES (
                    :predio_id, :gestion_id, :normative_version_id, 'CALCULATED', :usuario_id,
                    'INDIVIDUAL', :superficie_gis, :superficie_legal, :superficie_manual,
                    :superficie_calculo, :superficie_override_reason, :observaciones, CURRENT_TIMESTAMP
                )
                RETURNING appraisal_id
                """
            ),
            {
                "predio_id": predio_id,
                "gestion_id": gestion_id,
                "normative_version_id": normative_version_id,
                "usuario_id": usuario_id,
                "superficie_gis": superficie_gis,
                "superficie_legal": superficie_legal,
                "superficie_manual": superficie_manual,
                "superficie_calculo": superficie_calculo,
                "superficie_override_reason": superficie_override_reason,
                "observaciones": observaciones,
            },
        )
    ).fetchone()
    appraisal_id = appraisal_row[0]

    await db.execute(
        text(
            """
            INSERT INTO appraisal_result (
                appraisal_id, valor_terreno, valor_construccion, base_imponible, impuesto_estimado, alicuota, formula_version
            ) VALUES (
                :appraisal_id, :valor_terreno, :valor_construccion, :base_imponible, :impuesto_estimado, :alicuota, 'gamlp-v2'
            )
            """
        ),
        {
            "appraisal_id": appraisal_id,
            "valor_terreno": valor_terreno,
            "valor_construccion": valor_construccion,
            "base_imponible": base_imponible,
            "impuesto_estimado": impuesto_estimado,
            "alicuota": alicuota,
        },
    )

    for index, block in enumerate(bloques, start=1):
        await db.execute(
            text(
                """
                INSERT INTO appraisal_building_block (
                    appraisal_id, orden, superficie, calidad_constructiva, anio_construccion,
                    tipologia_constructiva_id, valor_tipologia_m2, factor_antiguedad, valor_bloque
                ) VALUES (
                    :appraisal_id, :orden, :superficie, :calidad_constructiva, :anio_construccion,
                    :tipologia_constructiva_id, :valor_tipologia_m2, :factor_antiguedad, :valor_bloque
                )
                """
            ),
            {
                "appraisal_id": appraisal_id,
                "orden": index,
                "superficie": block["superficie"],
                "calidad_constructiva": block["calidad_constructiva"],
                "anio_construccion": block["anio_construccion"],
                "tipologia_constructiva_id": block["tipologia_constructiva_id"],
                "valor_tipologia_m2": block["valor_tipologia_m2"],
                "factor_antiguedad": block["factor_antiguedad"],
                "valor_bloque": block["valor_bloque"],
            },
        )

    await db.execute(
        text(
            """
            INSERT INTO appraisal_trace (
                appraisal_id, predio_id, gestion_anio, normative_version, input_payload,
                factores_aplicados, contexto_espacial, tablas_utilizadas, formulas_aplicadas,
                overrides_manuales, geometries_used, generated_by
            ) VALUES (
                :appraisal_id, :predio_id, :gestion_anio, :normative_version,
                CAST(:input_payload AS jsonb),
                CAST(:factores_aplicados AS jsonb),
                CAST(:contexto_espacial AS jsonb),
                CAST(:tablas_utilizadas AS jsonb),
                CAST(:formulas_aplicadas AS jsonb),
                CAST(:overrides_manuales AS jsonb),
                CAST(:geometries_used AS jsonb),
                :generated_by
            )
            """
        ),
            {
                "appraisal_id": appraisal_id,
                "predio_id": predio_id,
                "gestion_anio": trace_payload["gestion_anio"],
                "normative_version": trace_payload["normative_version"],
                "input_payload": json.dumps(trace_payload["input_payload"]),
                "factores_aplicados": json.dumps(trace_payload["factores_aplicados"]),
                "contexto_espacial": json.dumps(trace_payload["contexto_espacial"]),
                "tablas_utilizadas": json.dumps(trace_payload["tablas_utilizadas"]),
                "formulas_aplicadas": json.dumps(trace_payload["formulas_aplicadas"]),
                "overrides_manuales": json.dumps(trace_payload["overrides_manuales"]),
                "geometries_used": json.dumps(trace_payload["geometries_used"]),
                "generated_by": usuario_id,
            },
        )
    await db.commit()
    return appraisal_id


async def fetch_appraisal_result(db: AsyncSession, appraisal_id: str):
    row = (
        await db.execute(
            text(
                """
                SELECT
                    ac.appraisal_id,
                    ac.predio_id,
                    ac.created_at,
                    ar.valor_terreno,
                    ar.valor_construccion,
                    ar.base_imponible,
                    ar.impuesto_estimado,
                    ar.alicuota,
                    ac.superficie_gis,
                    ac.superficie_legal,
                    ac.superficie_manual,
                    ac.superficie_calculo,
                    ac.superficie_override_reason,
                    at.factores_aplicados,
                    at.contexto_espacial,
                    at.tablas_utilizadas,
                    at.formulas_aplicadas,
                    at.overrides_manuales,
                    at.normative_version,
                    at.generated_by
                FROM appraisal_case ac
                JOIN appraisal_result ar ON ar.appraisal_id = ac.appraisal_id
                JOIN appraisal_trace at ON at.appraisal_id = ac.appraisal_id
                WHERE ac.appraisal_id = :appraisal_id
                LIMIT 1
                """
            ),
            {"appraisal_id": appraisal_id},
        )
    ).fetchone()
    return dict(row._mapping) if row else None


async def fetch_appraisal_blocks(db: AsyncSession, appraisal_id: str):
    rows = (
        await db.execute(
            text(
                """
                SELECT orden, superficie, calidad_constructiva, anio_construccion,
                       valor_tipologia_m2, factor_antiguedad, valor_bloque
                FROM appraisal_building_block
                WHERE appraisal_id = :appraisal_id
                ORDER BY orden
                """
            ),
            {"appraisal_id": appraisal_id},
        )
    ).fetchall()
    return [dict(row._mapping) for row in rows]


async def fetch_appraisal_trace(db: AsyncSession, appraisal_id: str):
    row = (
        await db.execute(
            text("SELECT * FROM appraisal_trace WHERE appraisal_id = :appraisal_id LIMIT 1"),
            {"appraisal_id": appraisal_id},
        )
    ).fetchone()
    return dict(row._mapping) if row else None


async def fetch_appraisals(db: AsyncSession, limit: int = 20):
    rows = (
        await db.execute(
            text(
                """
                SELECT
                    ac.appraisal_id,
                    ac.predio_id,
                    p.codigo_catastral,
                    g.anio AS gestion_anio,
                    ar.base_imponible,
                    ar.impuesto_estimado,
                    ar.valor_terreno,
                    ar.valor_construccion,
                    ar.calculated_at AS created_at
                FROM appraisal_case ac
                JOIN appraisal_result ar ON ar.appraisal_id = ac.appraisal_id
                LEFT JOIN predio p ON p.id_predio = ac.predio_id
                LEFT JOIN gestion g ON g.id_gestion = ac.gestion_id
                ORDER BY ar.calculated_at DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        )
    ).fetchall()
    return [dict(row._mapping) for row in rows]


async def fetch_master_table(db: AsyncSession, table_name: str, gestion_anio: int):
    queries = {
        "zonas-valor": """
            SELECT tzv.zona_tributaria_codigo AS codigo,
                   tzv.valor_m2 AS valor,
                   tzv.material_via_codigo AS descripcion
            FROM tabla_zonas_valor tzv
            JOIN normative_version nv ON nv.normative_version_id = tzv.normative_version_id
            WHERE nv.gestion_anio = :gestion_anio
              AND tzv.activo = TRUE
            ORDER BY tzv.zona_tributaria_codigo, tzv.material_via_codigo
        """,
        "factores-pendiente": """
            SELECT CONCAT(rango_min, '-', rango_max) AS codigo,
                   factor AS valor,
                   'rango_grados' AS descripcion
            FROM tabla_factores_pendiente tfp
            JOIN normative_version nv ON nv.normative_version_id = tfp.normative_version_id
            WHERE nv.gestion_anio = :gestion_anio
              AND tfp.activo = TRUE
            ORDER BY rango_min
        """,
        "servicios": """
            SELECT servicio_codigo AS codigo,
                   puntaje AS valor,
                   'servicio_oficial' AS descripcion
            FROM tabla_factores_servicios tfs
            JOIN normative_version nv ON nv.normative_version_id = tfs.normative_version_id
            WHERE nv.gestion_anio = :gestion_anio
              AND tfs.activo = TRUE
            ORDER BY servicio_codigo
        """,
        "tipologias": """
            SELECT calidad AS codigo,
                   valor_m2 AS valor,
                   categoria AS descripcion
            FROM tabla_tipologias_constructivas ttc
            JOIN normative_version nv ON nv.normative_version_id = ttc.normative_version_id
            WHERE nv.gestion_anio = :gestion_anio
              AND ttc.activo = TRUE
            ORDER BY calidad, categoria
        """,
        "depreciacion": """
            SELECT CONCAT(edad_min, '-', edad_max) AS codigo,
                   factor AS valor,
                   'antiguedad' AS descripcion
            FROM tabla_depreciacion_antiguedad tda
            JOIN normative_version nv ON nv.normative_version_id = tda.normative_version_id
            WHERE nv.gestion_anio = :gestion_anio
            ORDER BY edad_min
        """,
    }
    sql = queries[table_name]
    rows = (await db.execute(text(sql), {"gestion_anio": gestion_anio})).fetchall()
    return [dict(row._mapping) for row in rows]

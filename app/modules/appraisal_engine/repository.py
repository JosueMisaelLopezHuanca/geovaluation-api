import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def get_normative_version(db: AsyncSession, gestion_anio: int):
    row = (
        await db.execute(
            text(
                """
                SELECT
                    normative_version_id,
                    gestion_anio,
                    nombre,
                    version_codigo,
                    resolucion_municipal,
                    detalle_normativo
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


async def ensure_public_user(db: AsyncSession, nombre_usuario: str = "consulta_publica"):
    existing_user_id = await get_usuario_id(db, nombre_usuario)
    if existing_user_id:
        return existing_user_id

    await db.execute(
        text(
            """
            INSERT INTO persona (
                nombres,
                apellido_paterno,
                apellido_materno,
                ci,
                expedido_en,
                email,
                estado
            )
            SELECT
                'CONSULTA',
                'PUBLICA',
                'CATASTRO',
                'CATASTRO-PUBLICO',
                'LP',
                'consulta_publica@catastro.local',
                'ACTIVO'
            WHERE NOT EXISTS (
                SELECT 1
                FROM persona
                WHERE ci = 'CATASTRO-PUBLICO'
            )
            """
        )
    )

    await db.execute(
        text(
            """
            INSERT INTO usuario (
                id_persona,
                nombre_usuario,
                contrasena_hash,
                activo
            )
            SELECT
                p.id_persona,
                CAST(:nombre_usuario AS VARCHAR),
                'public-user-sin-login',
                TRUE
            FROM persona p
            WHERE p.ci = 'CATASTRO-PUBLICO'
              AND NOT EXISTS (
                  SELECT 1
                  FROM usuario u
                  WHERE u.nombre_usuario = CAST(:nombre_usuario AS VARCHAR)
              )
            """
        ),
        {"nombre_usuario": nombre_usuario},
    )

    return await get_usuario_id(db, nombre_usuario)


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
                    p.frente,
                    p.fondo,
                    p.forma AS forma_lote,
                    ST_AsText(ST_Centroid(p.geom)) AS coordenadas,
                    mv.nombre AS material_via_codigo,
                    COALESCE(zt.codigo, zv.nombre) AS zona_tributaria_codigo,
                    ctx.pendiente_codigo,
                    p.pendiente_grados,
                    ctx.riesgo_codigo,
                    ctx.riesgo_grado,
                    ctx.pendiente_cobertura_pct,
                    ctx.riesgo_cobertura_pct,
                    sm."DISTRITOMC" AS distrito,
                    sm."MACRODISTR" AS macrodistrito,
                    sm."TIPO" AS tipo_via_automatico,
                    zh.zonavalor AS zona_homogenea_codigo,
                    zh.grupovalor AS zona_homogenea_grupo,
                    COALESCE(svc.servicios, ARRAY[]::VARCHAR[]) AS servicios_oficiales
                FROM predio p
                LEFT JOIN material_via mv ON mv.id_material_via = p.id_material_via
                LEFT JOIN zona_valor zv ON zv.id_zona_valor = p.id_zona_valor
                LEFT JOIN zona_tributaria zt ON zt.id_zona_tributaria = zv.id_zona_tributaria
                LEFT JOIN predio_contexto_espacial ctx ON ctx.id_predio = p.id_predio
                LEFT JOIN manzana m ON m.id_manzana = p.id_manzana
                LEFT JOIN LATERAL (
                    SELECT "DISTRITOMC", "MACRODISTR", "TIPO"
                    FROM staging_manzanas sm
                    WHERE sm.geometry && ST_PointOnSurface(m.geom)
                      AND ST_Intersects(sm.geometry, ST_PointOnSurface(m.geom))
                    LIMIT 1
                ) sm ON TRUE
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


async def get_manual_data(db: AsyncSession, predio_id: str):
    row = (
        await db.execute(
            text(
                """
                SELECT *
                FROM predio_manual_data
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


async def get_official_risk_factor(db: AsyncSession, normative_version_id: str, riesgo_codigo: int | None):
    if riesgo_codigo is None:
        return None
    row = (
        await db.execute(
            text(
                """
                SELECT factor
                FROM tabla_factores_riesgo
                WHERE normative_version_id = :normative_version_id
                  AND riesgo_codigo = :riesgo_codigo
                  AND activo = TRUE
                LIMIT 1
                """
            ),
            {
                "normative_version_id": normative_version_id,
                "riesgo_codigo": riesgo_codigo,
            },
        )
    ).fetchone()
    return float(row[0]) if row else None


async def get_terrain_coefficient(
    db: AsyncSession, normative_version_id: str, coefficient_type: str, coefficient_code: str | None
):
    if not coefficient_code:
        coefficient_code = "DEFAULT"
    row = (
        await db.execute(
            text(
                """
                SELECT factor
                FROM tabla_coeficientes_terreno
                WHERE normative_version_id = :normative_version_id
                  AND coefficient_type = :coefficient_type
                  AND coefficient_code = :coefficient_code
                  AND activo = TRUE
                LIMIT 1
                """
            ),
            {
                "normative_version_id": normative_version_id,
                "coefficient_type": coefficient_type,
                "coefficient_code": coefficient_code,
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


async def get_impbi_bracket(db: AsyncSession, normative_version_id: str, base_imponible: float):
    row = (
        await db.execute(
            text(
                """
                SELECT tramo_codigo, limite_inferior, limite_superior, cuota_fija,
                       alicuota_excedente, fuente_gestion_anio, fuente_documental,
                       vigente_confirmada
                FROM tabla_escala_impbi
                WHERE normative_version_id = :normative_version_id
                  AND activo = TRUE
                  AND (:base_imponible > limite_inferior OR limite_inferior = 0)
                  AND (limite_superior IS NULL OR :base_imponible <= limite_superior)
                ORDER BY limite_inferior DESC
                LIMIT 1
                """
            ),
            {
                "normative_version_id": normative_version_id,
                "base_imponible": base_imponible,
            },
        )
    ).fetchone()
    return dict(row._mapping) if row else None


async def get_ph_location_factor(db: AsyncSession, normative_version_id: str, zona_tributaria_codigo: str | None):
    if not zona_tributaria_codigo:
        return None
    row = (
        await db.execute(
            text(
                """
                SELECT factor
                FROM tabla_factores_ubicacion_ph
                WHERE normative_version_id = :normative_version_id
                  AND zona_tributaria_codigo = :zona_tributaria_codigo
                  AND activo = TRUE
                LIMIT 1
                """
            ),
            {
                "normative_version_id": normative_version_id,
                "zona_tributaria_codigo": zona_tributaria_codigo,
            },
        )
    ).fetchone()
    return float(row[0]) if row else None


async def resolve_tipologia_constructiva(
    db: AsyncSession,
    normative_version_id: str,
    calidad: str,
    categoria: str = "PREDIO",
):
    row = (
        await db.execute(
            text(
                """
                SELECT tipologia_constructiva_id, calidad, categoria, valor_m2, tipologia_origen_codigo
                FROM tabla_tipologias_constructivas
                WHERE normative_version_id = :normative_version_id
                  AND calidad = :calidad
                  AND categoria = :categoria
                  AND activo = TRUE
                LIMIT 1
                """
            ),
            {
                "normative_version_id": normative_version_id,
                "calidad": calidad.upper(),
                "categoria": categoria,
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


async def resolve_construction_matrix(
    db: AsyncSession,
    normative_version_id: str,
    *,
    calidad: str,
    material_estructural: str | None,
    tipo_cubierta: str | None,
    estado_conservacion: str | None,
    remodelaciones: str | None,
):
    row = (
        await db.execute(
            text(
                """
                SELECT
                    calidad,
                    material_estructural,
                    tipo_cubierta,
                    estado_conservacion,
                    factor_material,
                    factor_cubierta,
                    factor_estado,
                    factor_remodelacion
                FROM tabla_matriz_calidad_material
                WHERE normative_version_id = :normative_version_id
                  AND activo = TRUE
                  AND calidad = :calidad
                  AND estado_conservacion = :estado_conservacion
                  AND remodelacion_codigo = :remodelacion_codigo
                  AND (
                        (
                            material_estructural = :material_estructural
                            AND tipo_cubierta = :tipo_cubierta
                        )
                        OR (
                            material_estructural = 'GENERICA'
                            AND tipo_cubierta = 'GENERICA'
                        )
                  )
                -- Retain official condition/remodeling factors when no specific material matrix exists.
                ORDER BY CASE
                    WHEN material_estructural = :material_estructural
                     AND tipo_cubierta = :tipo_cubierta THEN 0
                    ELSE 1
                END
                LIMIT 1
                """
            ),
            {
                "normative_version_id": normative_version_id,
                "calidad": calidad.upper(),
                "material_estructural": str(material_estructural or "GENERICA").upper(),
                "tipo_cubierta": str(tipo_cubierta or "GENERICA").upper(),
                "estado_conservacion": str(estado_conservacion or "BUENO").upper(),
                "remodelacion_codigo": "SI" if remodelaciones else "NO",
            },
        )
    ).fetchone()
    return dict(row._mapping) if row else None


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


async def save_manual_data(
    db: AsyncSession,
    *,
    predio_id: str,
    usuario_id: str,
    payload: dict,
):
    await db.execute(
        text("UPDATE predio_manual_data SET vigente = FALSE WHERE predio_id = :predio_id"),
        {"predio_id": predio_id},
    )
    columns = [
        "predio_id",
        "vigente",
        "usuario_id",
        "motivo",
        "es_temporal",
        "superficie_manual",
        "frente",
        "fondo",
        "forma_lote",
        "uso_suelo",
        "tipo_via",
        "acceso_vehicular",
        "pendiente_manual",
        "zona_homogenea_manual",
        "zona_tributaria_manual",
        "coordenadas_manual",
        "distrito_manual",
        "macrodistrito_manual",
        "agua",
        "alcantarillado",
        "electricidad",
        "telefono",
        "gas",
        "internet",
        "alumbrado_publico",
        "riesgo_territorial_manual",
        "tipo_riesgo",
        "afectacion_riesgo",
        "valor_unitario_manual",
        "usar_valor_unitario_manual",
        "coeficiente_manual",
        "usar_coeficiente_manual",
        "depreciacion_manual",
        "usar_depreciacion_manual",
        "ajuste_comercial",
        "clasificacion_especial",
        "observacion_tecnica",
    ]
    values = {column: payload.get(column) for column in columns if column not in {"predio_id", "vigente", "usuario_id"}}
    values.update(
        {
            "predio_id": predio_id,
            "vigente": True,
            "usuario_id": usuario_id,
            "motivo": payload.get("motivo") or "Ajuste tecnico",
            "es_temporal": bool(payload.get("es_temporal", False)),
            "usar_valor_unitario_manual": bool(payload.get("usar_valor_unitario_manual", False)),
            "usar_coeficiente_manual": bool(payload.get("usar_coeficiente_manual", False)),
            "usar_depreciacion_manual": bool(payload.get("usar_depreciacion_manual", False)),
        }
    )
    await db.execute(
        text(
            """
            INSERT INTO predio_manual_data (
                predio_id, vigente, usuario_id, motivo, es_temporal,
                superficie_manual, frente, fondo, forma_lote, uso_suelo, tipo_via, acceso_vehicular,
                pendiente_manual, zona_homogenea_manual, zona_tributaria_manual, coordenadas_manual,
                distrito_manual, macrodistrito_manual, agua, alcantarillado, electricidad, telefono,
                gas, internet, alumbrado_publico, riesgo_territorial_manual, tipo_riesgo, afectacion_riesgo,
                valor_unitario_manual, usar_valor_unitario_manual, coeficiente_manual, usar_coeficiente_manual,
                depreciacion_manual, usar_depreciacion_manual, ajuste_comercial, clasificacion_especial, observacion_tecnica
            ) VALUES (
                :predio_id, :vigente, :usuario_id, :motivo, :es_temporal,
                :superficie_manual, :frente, :fondo, :forma_lote, :uso_suelo, :tipo_via, :acceso_vehicular,
                :pendiente_manual, :zona_homogenea_manual, :zona_tributaria_manual, :coordenadas_manual,
                :distrito_manual, :macrodistrito_manual, :agua, :alcantarillado, :electricidad, :telefono,
                :gas, :internet, :alumbrado_publico, :riesgo_territorial_manual, :tipo_riesgo, :afectacion_riesgo,
                :valor_unitario_manual, :usar_valor_unitario_manual, :coeficiente_manual, :usar_coeficiente_manual,
                :depreciacion_manual, :usar_depreciacion_manual, :ajuste_comercial, :clasificacion_especial, :observacion_tecnica
            )
            """
        ),
        values,
    )


async def save_audit_entries(
    db: AsyncSession,
    *,
    appraisal_id: str | None,
    predio_id: str,
    usuario_id: str,
    entries: list[dict],
):
    for entry in entries:
        await db.execute(
            text(
                """
                INSERT INTO avaluo_auditoria (
                    appraisal_id, predio_id, usuario_id, campo, valor_anterior, valor_nuevo,
                    fuente_anterior, fuente_nueva, motivo, es_temporal
                ) VALUES (
                    :appraisal_id, :predio_id, :usuario_id, :campo, :valor_anterior, :valor_nuevo,
                    :fuente_anterior, :fuente_nueva, :motivo, :es_temporal
                )
                """
            ),
            {
                "appraisal_id": appraisal_id,
                "predio_id": predio_id,
                "usuario_id": usuario_id,
                "campo": entry["campo"],
                "valor_anterior": entry.get("valor_anterior"),
                "valor_nuevo": entry.get("valor_nuevo"),
                "fuente_anterior": entry.get("fuente_anterior"),
                "fuente_nueva": entry["fuente_nueva"],
                "motivo": entry.get("motivo"),
                "es_temporal": bool(entry.get("es_temporal", False)),
            },
        )
    return None


async def save_appraisal_case_and_result(
    db: AsyncSession,
    *,
    predio_id: str,
    gestion_id: str | None,
    normative_version_id: str,
    usuario_id: str,
    appraisal_mode: str,
    regimen_inmueble: str,
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
                    calculation_mode, appraisal_mode, regimen_inmueble, superficie_gis, superficie_legal, superficie_manual,
                    superficie_calculo, superficie_override_reason, observaciones, finalized_at
                ) VALUES (
                    :predio_id, :gestion_id, :normative_version_id, 'CALCULATED', :usuario_id,
                    'INDIVIDUAL', :appraisal_mode, :regimen_inmueble, :superficie_gis, :superficie_legal, :superficie_manual,
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
                "appraisal_mode": appraisal_mode,
                "regimen_inmueble": regimen_inmueble,
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
                    tipologia_constructiva_id, valor_tipologia_m2, factor_antiguedad, valor_bloque,
                    estado_conservacion, numero_pisos, uso_construccion, material_estructural,
                    tipo_cubierta, remodelaciones, factor_estado, factor_material, factor_cubierta,
                    factor_remodelacion, valor_tipologia_ajustado_m2, factor_ubicacion_ph
                ) VALUES (
                    :appraisal_id, :orden, :superficie, :calidad_constructiva, :anio_construccion,
                    :tipologia_constructiva_id, :valor_tipologia_m2, :factor_antiguedad, :valor_bloque,
                    :estado_conservacion, :numero_pisos, :uso_construccion, :material_estructural,
                    :tipo_cubierta, :remodelaciones, :factor_estado, :factor_material, :factor_cubierta,
                    :factor_remodelacion, :valor_tipologia_ajustado_m2, :factor_ubicacion_ph
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
                "estado_conservacion": block.get("estado_conservacion"),
                "numero_pisos": block.get("numero_pisos"),
                "uso_construccion": block.get("uso_construccion"),
                "material_estructural": block.get("material_estructural"),
                "tipo_cubierta": block.get("tipo_cubierta"),
                "remodelaciones": block.get("remodelaciones"),
                "factor_estado": block.get("factor_estado", 1.0),
                "factor_material": block.get("factor_material", 1.0),
                "factor_cubierta": block.get("factor_cubierta", 1.0),
                "factor_remodelacion": block.get("factor_remodelacion", 1.0),
                "valor_tipologia_ajustado_m2": block.get("valor_tipologia_ajustado_m2", block["valor_tipologia_m2"]),
                "factor_ubicacion_ph": block.get("factor_ubicacion_ph", 1.0),
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
                    ac.appraisal_mode,
                    ac.regimen_inmueble,
                    nv.gestion_anio,
                    nv.nombre AS normative_nombre,
                    nv.version_codigo,
                    nv.resolucion_municipal,
                    nv.detalle_normativo,
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
                JOIN normative_version nv ON nv.normative_version_id = ac.normative_version_id
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
                       valor_tipologia_m2, factor_antiguedad, valor_bloque,
                       estado_conservacion, numero_pisos, uso_construccion,
                       material_estructural, tipo_cubierta, remodelaciones,
                       factor_estado, factor_material, factor_cubierta,
                       factor_remodelacion, valor_tipologia_ajustado_m2, factor_ubicacion_ph
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
                    ac.appraisal_mode,
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


async def save_public_beta_submission(
    db: AsyncSession,
    *,
    predio_id: str,
    gestion_anio: int,
    avaluo_tipo: str,
    regimen_inmueble: str,
    base_imponible: float,
    impuesto_estimado: float,
    calculation_input: dict,
    calculation_result: dict,
    utilidad_resultado: str | None,
    comentario: str | None,
    consentimiento_version: str,
    nombre_contacto: str | None,
    correo_contacto: str | None,
    telefono_contacto: str | None,
    acepta_contacto: bool,
):
    row = (
        await db.execute(
            text(
                """
                INSERT INTO public_beta_consulta (
                    predio_id, gestion_anio, avaluo_tipo, regimen_inmueble,
                    base_imponible, impuesto_estimado, calculation_input, calculation_result,
                    utilidad_resultado, comentario, consentimiento_version, consentimiento_registro
                ) VALUES (
                    :predio_id, :gestion_anio, :avaluo_tipo, :regimen_inmueble,
                    :base_imponible, :impuesto_estimado, CAST(:calculation_input AS jsonb),
                    CAST(:calculation_result AS jsonb), :utilidad_resultado, :comentario,
                    :consentimiento_version, TRUE
                )
                RETURNING beta_submission_id, created_at
                """
            ),
            {
                "predio_id": predio_id,
                "gestion_anio": gestion_anio,
                "avaluo_tipo": avaluo_tipo,
                "regimen_inmueble": regimen_inmueble,
                "base_imponible": base_imponible,
                "impuesto_estimado": impuesto_estimado,
                "calculation_input": json.dumps(calculation_input),
                "calculation_result": json.dumps(calculation_result),
                "utilidad_resultado": utilidad_resultado,
                "comentario": comentario,
                "consentimiento_version": consentimiento_version,
            },
        )
    ).fetchone()
    beta_submission_id = row[0]

    has_contact = bool(nombre_contacto or correo_contacto or telefono_contacto)
    if acepta_contacto and has_contact:
        await db.execute(
            text(
                """
                INSERT INTO public_beta_contacto (
                    beta_submission_id, nombre_contacto, correo_contacto, telefono_contacto,
                    consentimiento_contacto
                ) VALUES (
                    :beta_submission_id, :nombre_contacto, :correo_contacto, :telefono_contacto,
                    TRUE
                )
                """
            ),
            {
                "beta_submission_id": beta_submission_id,
                "nombre_contacto": nombre_contacto,
                "correo_contacto": correo_contacto,
                "telefono_contacto": telefono_contacto,
            },
        )

    return {
        "beta_submission_id": beta_submission_id,
        "created_at": row[1],
        "contacto_registrado": bool(acepta_contacto and has_contact),
    }


async def fetch_public_beta_summary(db: AsyncSession) -> dict:
    row = (
        await db.execute(
            text(
                """
                SELECT
                    COUNT(*) AS total_consultas,
                    COUNT(c.beta_contacto_id) AS total_con_contacto,
                    MAX(q.created_at) AS ultima_consulta,
                    COUNT(*) FILTER (WHERE q.utilidad_resultado = 'UTIL') AS utilidad_util,
                    COUNT(*) FILTER (WHERE q.utilidad_resultado = 'PARCIAL') AS utilidad_parcial,
                    COUNT(*) FILTER (WHERE q.utilidad_resultado = 'NO_REFLEJA') AS utilidad_no_refleja,
                    COUNT(*) FILTER (WHERE q.utilidad_resultado = 'NO_SE') AS utilidad_no_se
                FROM public_beta_consulta q
                LEFT JOIN public_beta_contacto c ON c.beta_submission_id = q.beta_submission_id
                """
            )
        )
    ).fetchone()
    return {
        "total_consultas": int(row[0] or 0),
        "total_con_contacto": int(row[1] or 0),
        "ultima_consulta": row[2],
        "utilidad": {
            "UTIL": int(row[3] or 0),
            "PARCIAL": int(row[4] or 0),
            "NO_REFLEJA": int(row[5] or 0),
            "NO_SE": int(row[6] or 0),
        },
    }


async def fetch_public_beta_submissions(db: AsyncSession, limit: int | None = 20) -> dict:
    total = (
        await db.execute(text("SELECT COUNT(*) FROM public_beta_consulta"))
    ).scalar_one()
    rows = (
        await db.execute(
            text(
                """
                SELECT
                    q.beta_submission_id,
                    q.predio_id,
                    p.codigo_catastral,
                    q.gestion_anio,
                    q.avaluo_tipo,
                    q.regimen_inmueble,
                    q.base_imponible,
                    q.impuesto_estimado,
                    q.utilidad_resultado,
                    q.comentario,
                    (c.beta_contacto_id IS NOT NULL) AS contacto_autorizado,
                    c.nombre_contacto,
                    c.correo_contacto,
                    c.telefono_contacto,
                    q.created_at
                FROM public_beta_consulta q
                LEFT JOIN predio p ON p.id_predio = q.predio_id
                LEFT JOIN public_beta_contacto c ON c.beta_submission_id = q.beta_submission_id
                ORDER BY q.created_at DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        )
    ).fetchall()
    return {
        "total": int(total or 0),
        "items": [dict(row._mapping) for row in rows],
    }


async def delete_public_beta_contact(db: AsyncSession, beta_submission_id: str) -> bool:
    row = (
        await db.execute(
            text(
                """
                DELETE FROM public_beta_contacto
                WHERE beta_submission_id = :beta_submission_id
                RETURNING beta_contacto_id
                """
            ),
            {"beta_submission_id": beta_submission_id},
        )
    ).fetchone()
    return row is not None


async def fetch_master_table(db: AsyncSession, table_name: str, gestion_anio: int):
    aliases = {
        "zonas_valor": "zonas-valor",
        "valores_zona": "zonas-valor",
        "factores_pendiente": "factores-pendiente",
        "factores_riesgo": "factores-riesgo",
        "coeficientes_terreno": "coeficientes-terreno",
        "matriz_construccion": "matriz-construccion",
        "factores_ubicacion_ph": "factores-ubicacion-ph",
        "escala_impbi": "escala-impbi",
    }
    table_name = aliases.get(table_name, table_name)
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
        "factores-riesgo": """
            SELECT CAST(riesgo_codigo AS VARCHAR) AS codigo,
                   factor AS valor,
                   riesgo_grado AS descripcion
            FROM tabla_factores_riesgo tfr
            JOIN normative_version nv ON nv.normative_version_id = tfr.normative_version_id
            WHERE nv.gestion_anio = :gestion_anio
              AND tfr.activo = TRUE
            ORDER BY riesgo_codigo
        """,
        "coeficientes-terreno": """
            SELECT CONCAT(coefficient_type, ':', coefficient_code) AS codigo,
                   factor AS valor,
                   descripcion
            FROM tabla_coeficientes_terreno tct
            JOIN normative_version nv ON nv.normative_version_id = tct.normative_version_id
            WHERE nv.gestion_anio = :gestion_anio
              AND tct.activo = TRUE
            ORDER BY coefficient_type, coefficient_code
        """,
        "matriz-construccion": """
            SELECT CONCAT(calidad, ':', material_estructural, ':', tipo_cubierta, ':', estado_conservacion) AS codigo,
                   (factor_material * factor_cubierta * factor_estado * factor_remodelacion) AS valor,
                   remodelacion_codigo AS descripcion
            FROM tabla_matriz_calidad_material tmcm
            JOIN normative_version nv ON nv.normative_version_id = tmcm.normative_version_id
            WHERE nv.gestion_anio = :gestion_anio
              AND tmcm.activo = TRUE
            ORDER BY calidad, material_estructural, tipo_cubierta, estado_conservacion
        """,
        "factores-ubicacion-ph": """
            SELECT zona_tributaria_codigo AS codigo,
                   factor AS valor,
                   fuente_documental AS descripcion
            FROM tabla_factores_ubicacion_ph tfu
            JOIN normative_version nv ON nv.normative_version_id = tfu.normative_version_id
            WHERE nv.gestion_anio = :gestion_anio
              AND tfu.activo = TRUE
            ORDER BY zona_tributaria_codigo
        """,
        "escala-impbi": """
            SELECT tramo_codigo AS codigo,
                   alicuota_excedente AS valor,
                   CONCAT('cuota=', cuota_fija, ', limite=', limite_inferior) AS descripcion
            FROM tabla_escala_impbi tei
            JOIN normative_version nv ON nv.normative_version_id = tei.normative_version_id
            WHERE nv.gestion_anio = :gestion_anio
              AND tei.activo = TRUE
            ORDER BY limite_inferior
        """,
    }
    sql = queries.get(table_name)
    if sql is None:
        raise ValueError(f"Tabla maestra no soportada: {table_name}")
    rows = (await db.execute(text(sql), {"gestion_anio": gestion_anio})).fetchall()
    return [dict(row._mapping) for row in rows]


async def fetch_audit_entries(db: AsyncSession, predio_id: str, limit: int = 100):
    rows = (
        await db.execute(
            text(
                """
                SELECT *
                FROM avaluo_auditoria
                WHERE predio_id = :predio_id
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            {"predio_id": predio_id, "limit": limit},
        )
    ).fetchall()
    return [dict(row._mapping) for row in rows]


async def fetch_predio_geometry(db: AsyncSession, predio_id: str):
    row = (
        await db.execute(
            text(
                """
                SELECT
                    ST_AsGeoJSON(ST_Transform(geom, 4326)) AS geometry_geojson,
                    ST_AsText(geom) AS geometry_wkt
                FROM predio
                WHERE id_predio = :predio_id
                LIMIT 1
                """
            ),
            {"predio_id": predio_id},
        )
    ).fetchone()
    return dict(row._mapping) if row else None


async def table_exists(db: AsyncSession, table_name: str) -> bool:
    row = (
        await db.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = :table_name
                )
                """
            ),
            {"table_name": table_name},
        )
    ).scalar()
    return bool(row)


async def fetch_coverage_stats(db: AsyncSession):
    contexto_table_exists = await table_exists(db, "predio_contexto_espacial")
    zonas_homogeneas_exists = await table_exists(db, "staging_zonas_homogeneas")
    contexto_join = (
        "LEFT JOIN predio_contexto_espacial ctx ON ctx.id_predio = p.id_predio"
        if contexto_table_exists
        else ""
    )
    contexto_filter = "ctx.pendiente_codigo IS NOT NULL" if contexto_table_exists else "FALSE"

    row = (
        await db.execute(
            text(
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
            ),
            {"zh_exists": zonas_homogeneas_exists},
        )
    ).fetchone()
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


async def fetch_gis_layer_bbox(
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
    elif capa == "diferencias_superficie":
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
                            WHEN :output_srid = 32719 THEN ST_SimplifyPreserveTopology(geom, 0.5)
                            ELSE ST_Transform(ST_SimplifyPreserveTopology(geom, 0.5), :output_srid)
                        END
                    )::jsonb,
                    'properties', jsonb_build_object(
                        'id', predio_id,
                        'codigo', codigo_catastral,
                        'clasificacion', clasificacion,
                        'porcentaje_diferencia', porcentaje_diferencia,
                        'capa', 'diferencias_superficie'
                    )
                ) AS f
                FROM mv_predio_superficie_diferencias
                WHERE geom && CASE
                    WHEN :input_srid = 32719 THEN ST_MakeEnvelope(:xmin, :ymin, :xmax, :ymax, 32719)
                    ELSE ST_Transform(ST_MakeEnvelope(:xmin, :ymin, :xmax, :ymax, :input_srid), 32719)
                END
                LIMIT :limit
            ) sub
            """
        )
    elif capa == "otbs":
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
                    'geometry', ST_AsGeoJSON(
                        CASE
                            WHEN :output_srid = 32719 THEN ST_SimplifyPreserveTopology(geometry, 1.5)
                            ELSE ST_Transform(ST_SimplifyPreserveTopology(geometry, 1.5), :output_srid)
                        END
                    )::jsonb,
                    'properties', jsonb_build_object(
                        'id', id,
                        'codigo', COALESCE(NULLIF(TRIM("NOM_OTB"), ''), 'Sin nombre'),
                        'nombre', COALESCE(NULLIF(TRIM("NOM_OTB"), ''), 'Sin nombre'),
                        'capa', 'otbs'
                    )
                ) AS f
                FROM staging_otbs
                WHERE geometry && CASE
                    WHEN :input_srid = 32719 THEN ST_MakeEnvelope(:xmin, :ymin, :xmax, :ymax, 32719)
                    ELSE ST_Transform(ST_MakeEnvelope(:xmin, :ymin, :xmax, :ymax, :input_srid), 32719)
                END
                ORDER BY "NOM_OTB"
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


async def refresh_surface_difference_view(db: AsyncSession):
    await db.execute(text("REFRESH MATERIALIZED VIEW mv_predio_superficie_diferencias"))
    await db.commit()


async def fetch_surface_difference_summary(db: AsyncSession):
    row = (
        await db.execute(
            text(
                """
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE clasificacion = 'OK') AS ok_count,
                    COUNT(*) FILTER (WHERE clasificacion = 'REVISAR') AS revisar_count,
                    COUNT(*) FILTER (WHERE clasificacion = 'CRITICO') AS critico_count,
                    ROUND(AVG(COALESCE(porcentaje_diferencia, 0)), 2) AS promedio_pct
                FROM mv_predio_superficie_diferencias
                """
            )
        )
    ).fetchone()
    return {
        "total": int(row.total or 0),
        "ok": int(row.ok_count or 0),
        "revisar": int(row.revisar_count or 0),
        "critico": int(row.critico_count or 0),
        "promedio_pct": float(row.promedio_pct or 0),
    }


async def fetch_surface_differences(
    db: AsyncSession,
    *,
    status: str | None,
    search: str | None,
    limit: int,
    offset: int,
):
    filters = []
    params: dict[str, object] = {"limit": limit, "offset": offset}
    if status:
        filters.append("clasificacion = :status")
        params["status"] = status
    if search:
        filters.append("(codigo_catastral ILIKE :search OR CAST(predio_id AS VARCHAR) ILIKE :search)")
        params["search"] = f"%{search}%"
    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""

    rows = (
        await db.execute(
            text(
                f"""
                SELECT predio_id, codigo_catastral, superficie_gis, superficie_legal,
                       diferencia, porcentaje_diferencia, clasificacion, color
                FROM mv_predio_superficie_diferencias
                {where_clause}
                ORDER BY
                    CASE clasificacion
                        WHEN 'CRITICO' THEN 0
                        WHEN 'REVISAR' THEN 1
                        ELSE 2
                    END,
                    porcentaje_diferencia DESC NULLS LAST,
                    codigo_catastral
                LIMIT :limit OFFSET :offset
                """
            ),
            params,
        )
    ).fetchall()

    total = (
        await db.execute(
            text(f"SELECT COUNT(*) FROM mv_predio_superficie_diferencias {where_clause}"),
            {key: value for key, value in params.items() if key not in {"limit", "offset"}},
        )
    ).scalar()

    return int(total or 0), [dict(row._mapping) for row in rows]

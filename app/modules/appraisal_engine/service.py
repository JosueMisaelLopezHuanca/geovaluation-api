from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.appraisal_engine import repository, rules, schemas


def _json_safe_dict(data: dict) -> dict:
    safe = {}
    for key, value in data.items():
        if isinstance(value, list):
            safe[key] = [_json_safe_dict(v) if isinstance(v, dict) else v for v in value]
        elif isinstance(value, dict):
            safe[key] = _json_safe_dict(value)
        elif hasattr(value, "isoformat"):
            safe[key] = value.isoformat()
        else:
            safe[key] = value
    return safe


async def get_predio_gis_context(db: AsyncSession, predio_id: str) -> schemas.PredioGisContextResponse:
    context = await repository.fetch_predio_gis_context(db, predio_id)
    if not context:
        raise HTTPException(status_code=404, detail="Predio no encontrado.")

    override = await repository.get_surface_override(db, predio_id)
    superficie_manual = float(override["superficie_manual"]) if override else None
    superficie_calculo, superficie_fuente = rules.choose_surface(
        float(context["superficie_gis"]),
        float(context["superficie_legal"]) if context.get("superficie_legal") is not None else None,
        superficie_manual,
    )
    official_services = [service for service in context.get("servicios_oficiales", []) if service in rules.OFFICIAL_SERVICES]

    return schemas.PredioGisContextResponse(
        predio_id=context["id_predio"],
        superficie_gis=float(context["superficie_gis"]),
        superficie_legal=float(context["superficie_legal"]) if context.get("superficie_legal") is not None else None,
        superficie_manual=superficie_manual,
        superficie_calculo=superficie_calculo,
        superficie_fuente=superficie_fuente,
        zona_homogenea_codigo=context.get("zona_homogenea_codigo"),
        zona_homogenea_grupo=context.get("zona_homogenea_grupo"),
        zona_tributaria_codigo=context.get("zona_tributaria_codigo"),
        material_via_codigo=context.get("material_via_codigo"),
        pendiente_codigo=context.get("pendiente_codigo"),
        pendiente_grados=float(context["pendiente_grados"]) if context.get("pendiente_grados") is not None else None,
        riesgo_codigo=context.get("riesgo_codigo"),
        riesgo_grado=context.get("riesgo_grado"),
        servicios_oficiales=official_services,
        overlays_utilizados=[
            "staging_zonas_homogeneas",
            "predio_contexto_espacial",
            "predio_servicio",
            "material_via",
            "zona_valor",
        ],
    )


async def calculate_appraisal(db: AsyncSession, payload: schemas.AppraisalRequestV2) -> schemas.AppraisalResponseV2:
    normative = await repository.get_normative_version(db, payload.gestion_anio)
    if not normative:
        raise HTTPException(status_code=404, detail=f"No existe normativa activa para la gestión {payload.gestion_anio}.")

    usuario_id = await repository.get_usuario_id(db, payload.usuario)
    if not usuario_id:
        raise HTTPException(status_code=404, detail=f"No existe el usuario '{payload.usuario}'.")

    gestion_id = await repository.get_gestion_id(db, payload.gestion_anio)
    predio_ctx = await repository.fetch_predio_gis_context(db, str(payload.predio_id))
    if not predio_ctx:
        raise HTTPException(status_code=404, detail="Predio no encontrado.")

    if payload.superficie_manual is not None and not payload.superficie_override_reason:
        raise HTTPException(status_code=422, detail="Debe enviar motivo cuando existe superficie manual.")

    official_context = await get_predio_gis_context(db, str(payload.predio_id))
    service_score, servicios_oficiales = rules.compute_service_score(official_context.servicios_oficiales)

    valor_unitario = await repository.get_official_land_value(
        db,
        normative["normative_version_id"],
        official_context.zona_tributaria_codigo,
        official_context.material_via_codigo,
    )
    if valor_unitario is None:
        raise HTTPException(status_code=409, detail="No existe valor unitario oficial para la combinación de zona y material de vía.")

    factor_pendiente = await repository.get_official_pendiente_factor(
        db,
        normative["normative_version_id"],
        official_context.pendiente_grados,
    )

    alicuota = await repository.get_alicuota(db, normative["normative_version_id"])
    if alicuota is None:
        raise HTTPException(status_code=409, detail="No existe alícuota oficial activa.")

    superficie_calculo, superficie_fuente = rules.choose_surface(
        official_context.superficie_gis,
        official_context.superficie_legal,
        payload.superficie_manual,
    )

    if payload.superficie_manual is not None:
        await repository.save_surface_override(
            db,
            predio_id=str(payload.predio_id),
            superficie_gis=official_context.superficie_gis,
            superficie_legal=official_context.superficie_legal,
            superficie_manual=payload.superficie_manual,
            motivo=payload.superficie_override_reason or "Override manual",
            usuario_id=str(usuario_id),
        )

    valor_terreno, valor_unitario_aplicado = rules.calculate_land_value(
        superficie_calculo=superficie_calculo,
        valor_unitario=valor_unitario,
        puntaje_servicios=service_score,
        factor_pendiente=factor_pendiente,
    )

    building_blocks = []
    total_building_value = 0.0
    for block in payload.bloques:
        tipologia = await repository.resolve_tipologia_constructiva(
            db, normative["normative_version_id"], block.calidad_constructiva
        )
        if not tipologia:
            raise HTTPException(
                status_code=409,
                detail=f"No existe tipología oficial para calidad '{block.calidad_constructiva}'.",
            )
        edad = max(0, payload.gestion_anio - block.anio_construccion)
        factor_antiguedad = await repository.resolve_depreciacion_factor(
            db, normative["normative_version_id"], edad
        )
        block_value = rules.calculate_building_block_value(
            block.superficie,
            float(tipologia["valor_m2"]),
            factor_antiguedad,
        )
        total_building_value += block_value
        building_blocks.append(
            {
                "superficie": round(block.superficie, 2),
                "calidad_constructiva": block.calidad_constructiva.upper(),
                "anio_construccion": block.anio_construccion,
                "tipologia_constructiva_id": str(tipologia["tipologia_constructiva_id"]),
                "valor_tipologia_m2": float(tipologia["valor_m2"]),
                "factor_antiguedad": factor_antiguedad,
                "valor_bloque": block_value,
            }
        )

    valor_construccion = round(total_building_value, 2)
    base_imponible = round(valor_terreno + valor_construccion, 2)
    impuesto_estimado = rules.calculate_tax(base_imponible, alicuota)

    trace_payload = _json_safe_dict(
        {
            "gestion_anio": payload.gestion_anio,
            "normative_version": f"{payload.gestion_anio}-{normative['version_codigo']}",
            "input_payload": payload.model_dump(mode="json"),
            "factores_aplicados": {
                "puntaje_servicios": service_score,
                "servicios_oficiales": servicios_oficiales,
                "factor_pendiente": factor_pendiente,
                "alicuota": alicuota,
                "valor_unitario": valor_unitario,
                "valor_unitario_aplicado": valor_unitario_aplicado,
            },
            "contexto_espacial": official_context.model_dump(mode="json"),
            "tablas_utilizadas": [
                f"tabla_zonas_valor:{payload.gestion_anio}:{normative['version_codigo']}",
                f"tabla_factores_pendiente:{payload.gestion_anio}:{normative['version_codigo']}",
                f"tabla_factores_servicios:{payload.gestion_anio}:{normative['version_codigo']}",
                f"tabla_tipologias_constructivas:{payload.gestion_anio}:{normative['version_codigo']}",
                f"tabla_depreciacion_antiguedad:{payload.gestion_anio}:{normative['version_codigo']}",
                f"tabla_alicuota_impuesto:{payload.gestion_anio}:{normative['version_codigo']}",
            ],
            "formulas_aplicadas": {
                "terreno": "superficie_calculo * valor_unitario * puntaje_servicios * factor_pendiente",
                "construccion": "sum(superficie * valor_tipologia * factor_antiguedad)",
                "base_imponible": "valor_terreno + valor_construccion",
            },
            "overrides_manuales": {
                "superficie_manual": payload.superficie_manual,
                "superficie_fuente": superficie_fuente,
                "motivo": payload.superficie_override_reason,
            },
            "geometries_used": {
                "predio_geometry": "predio.geom",
                "zona_homogenea": "staging_zonas_homogeneas.geometry",
                "pendiente": "predio_contexto_espacial",
                "riesgo": "predio_contexto_espacial",
            },
        }
    )

    appraisal_id = await repository.save_appraisal_case_and_result(
        db,
        predio_id=str(payload.predio_id),
        gestion_id=str(gestion_id) if gestion_id else None,
        normative_version_id=str(normative["normative_version_id"]),
        usuario_id=str(usuario_id),
        superficie_gis=official_context.superficie_gis,
        superficie_legal=official_context.superficie_legal,
        superficie_manual=payload.superficie_manual,
        superficie_calculo=superficie_calculo,
        superficie_override_reason=payload.superficie_override_reason,
        observaciones=payload.observaciones,
        valor_terreno=valor_terreno,
        valor_construccion=valor_construccion,
        base_imponible=base_imponible,
        impuesto_estimado=impuesto_estimado,
        alicuota=alicuota,
        bloques=building_blocks,
        trace_payload=trace_payload,
    )

    return schemas.AppraisalResponseV2(
        appraisal_id=appraisal_id,
        predio_id=payload.predio_id,
        created_at=None,
        valor_terreno=valor_terreno,
        valor_construccion=valor_construccion,
        base_imponible=base_imponible,
        impuesto_estimado=impuesto_estimado,
        factores_aplicados=trace_payload["factores_aplicados"],
        contexto_espacial=trace_payload["contexto_espacial"],
        tablas_utilizadas=trace_payload["tablas_utilizadas"],
        formula_aplicada=trace_payload["formulas_aplicadas"],
        auditoria={
            "superficie_gis": official_context.superficie_gis,
            "superficie_legal": official_context.superficie_legal,
            "superficie_manual": payload.superficie_manual,
            "superficie_calculo": superficie_calculo,
            "superficie_fuente": superficie_fuente,
            "usuario": payload.usuario,
            "normative_version": trace_payload["normative_version"],
        },
        bloques=building_blocks,
    )


async def get_appraisal(db: AsyncSession, appraisal_id: str) -> schemas.AppraisalResponseV2:
    row = await repository.fetch_appraisal_result(db, appraisal_id)
    if not row:
        raise HTTPException(status_code=404, detail="No existe el avalúo solicitado.")
    blocks = await repository.fetch_appraisal_blocks(db, appraisal_id)
    return schemas.AppraisalResponseV2(
        appraisal_id=row["appraisal_id"],
        predio_id=row["predio_id"],
        created_at=row.get("created_at"),
        valor_terreno=float(row["valor_terreno"]),
        valor_construccion=float(row["valor_construccion"]),
        base_imponible=float(row["base_imponible"]),
        impuesto_estimado=float(row["impuesto_estimado"]),
        factores_aplicados=row["factores_aplicados"],
        contexto_espacial=row["contexto_espacial"],
        tablas_utilizadas=row["tablas_utilizadas"],
        formula_aplicada=row["formulas_aplicadas"],
        auditoria={
            "superficie_gis": float(row["superficie_gis"]) if row.get("superficie_gis") is not None else None,
            "superficie_legal": float(row["superficie_legal"]) if row.get("superficie_legal") is not None else None,
            "superficie_manual": float(row["superficie_manual"]) if row.get("superficie_manual") is not None else None,
            "superficie_calculo": float(row["superficie_calculo"]),
            "motivo_override": row.get("superficie_override_reason"),
            "overrides": row["overrides_manuales"],
            "superficie_fuente": (
                row["overrides_manuales"].get("superficie_fuente")
                if isinstance(row["overrides_manuales"], dict)
                else None
            ),
            "normative_version": row.get("normative_version"),
            "usuario": row.get("generated_by"),
        },
        bloques=blocks,
    )


async def get_appraisal_trace(db: AsyncSession, appraisal_id: str) -> schemas.AppraisalTraceResponse:
    trace = await repository.fetch_appraisal_trace(db, appraisal_id)
    if not trace:
        raise HTTPException(status_code=404, detail="No existe traza para el avalúo solicitado.")
    return schemas.AppraisalTraceResponse(**trace)


async def get_master_table(db: AsyncSession, table_name: str, gestion_anio: int) -> list[schemas.MasterTableRow]:
    rows = await repository.fetch_master_table(db, table_name, gestion_anio)
    return [
        schemas.MasterTableRow(
            codigo=row["codigo"],
            valor=float(row["valor"]) if row.get("valor") is not None else None,
            descripcion=row.get("descripcion"),
            metadata={},
        )
        for row in rows
    ]


async def list_appraisals(db: AsyncSession, limit: int = 20) -> list[schemas.AppraisalListItem]:
    rows = await repository.fetch_appraisals(db, limit)
    return [
        schemas.AppraisalListItem(
            appraisal_id=row["appraisal_id"],
            predio_id=row["predio_id"],
            codigo_catastral=row.get("codigo_catastral"),
            gestion_anio=int(row["gestion_anio"]) if row.get("gestion_anio") is not None else 0,
            base_imponible=float(row["base_imponible"]),
            impuesto_estimado=float(row["impuesto_estimado"]),
            valor_terreno=float(row["valor_terreno"]),
            valor_construccion=float(row["valor_construccion"]),
            created_at=row["created_at"],
        )
        for row in rows
    ]


async def value_construction_blocks(
    db: AsyncSession, payload: schemas.ConstructionValuationRequest
) -> schemas.ConstructionValuationResponse:
    normative = await repository.get_normative_version(db, payload.gestion_anio)
    if not normative:
        raise HTTPException(status_code=404, detail=f"No existe normativa activa para la gestión {payload.gestion_anio}.")

    building_blocks = []
    total_building_value = 0.0
    for block in payload.bloques:
        tipologia = await repository.resolve_tipologia_constructiva(
            db, normative["normative_version_id"], block.calidad_constructiva
        )
        if not tipologia:
            raise HTTPException(
                status_code=409,
                detail=f"No existe tipología oficial para calidad '{block.calidad_constructiva}'.",
            )
        edad = max(0, payload.gestion_anio - block.anio_construccion)
        factor_antiguedad = await repository.resolve_depreciacion_factor(
            db, normative["normative_version_id"], edad
        )
        valor_bloque = rules.calculate_building_block_value(
            block.superficie,
            float(tipologia["valor_m2"]),
            factor_antiguedad,
        )
        total_building_value += valor_bloque
        building_blocks.append(
            {
                "superficie": round(block.superficie, 2),
                "calidad_constructiva": block.calidad_constructiva.upper(),
                "anio_construccion": block.anio_construccion,
                "edad": edad,
                "tipologia_constructiva_id": str(tipologia["tipologia_constructiva_id"]),
                "tipologia_origen_codigo": tipologia.get("tipologia_origen_codigo"),
                "categoria": tipologia.get("categoria"),
                "valor_tipologia_m2": float(tipologia["valor_m2"]),
                "factor_antiguedad": factor_antiguedad,
                "valor_bloque": valor_bloque,
            }
        )

    return schemas.ConstructionValuationResponse(
        gestion_anio=payload.gestion_anio,
        valor_construccion=round(total_building_value, 2),
        bloques=building_blocks,
    )


def get_methodology() -> dict:
    return {
        "version": "gamlp-v2",
        "enforced_rules": {
            "factor_riesgo_en_formula": False,
            "servicios_oficiales": [
                "AGUA POTABLE",
                "ALCANTARILLADO",
                "ENERGIA ELECTRICA",
                "TELEFONO",
            ],
            "puntaje_por_servicio": 0.20,
            "puntaje_servicios_maximo": 0.80,
            "superficie_calculo": "superficie_manual ?? superficie_gis",
        },
        "formulas": {
            "terreno": "superficie_calculo * valor_unitario * puntaje_servicios * factor_pendiente",
            "construccion": "SUM(superficie * valor_tipologia * factor_antiguedad)",
            "base_imponible": "valor_terreno + valor_construccion",
            "impuesto": "base_imponible * alicuota",
        },
        "tablas_maestras": [
            "tabla_zonas_valor",
            "tabla_factores_pendiente",
            "tabla_factores_servicios",
            "tabla_tipologias_constructivas",
            "tabla_depreciacion_antiguedad",
            "tabla_alicuota_impuesto",
        ],
    }

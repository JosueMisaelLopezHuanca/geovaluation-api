from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.avaluos import repository, rules, schemas
from app.domain.predios.service import infer_bbox_srid


def _normalizar_ficha_tecnica(
    ficha_tecnica: schemas.AvaluoFichaTecnica | None,
) -> dict:
    if not ficha_tecnica:
        return {}

    return ficha_tecnica.model_dump(exclude_none=True)


def _to_json_safe(value):
    if isinstance(value, Decimal):
        return float(value)

    if isinstance(value, UUID):
        return str(value)

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, dict):
        return {key: _to_json_safe(item) for key, item in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_to_json_safe(item) for item in value]

    return value


def _build_contexto_detectado(contexto: dict) -> dict:
    return {
        "superficie_terreno": float(contexto.get("superficie_terreno") or 0),
        "superficie_terreno_fuente": "predio.superficie_mensura",
        "material_via_detectado": contexto.get("material_via_nombre"),
        "zona_valor_detectada": contexto.get("zona_valor_nombre"),
        "zona_homogenea_codigo_detectada": contexto.get("zona_homogenea_codigo"),
        "zona_homogenea_grupo_detectado": contexto.get("zona_homogenea_grupo"),
        "servicios_detectados": list(contexto.get("servicios") or []),
        "riesgo_codigo_detectado": contexto.get("riesgo_codigo"),
        "riesgo_grado_detectado": contexto.get("riesgo_grado"),
        "pendiente_codigo_detectado": contexto.get("pendiente_codigo"),
        "pendiente_grados_detectado": contexto.get("pendiente_grados"),
        "pendiente_cobertura_pct": contexto.get("pendiente_cobertura_pct"),
        "riesgo_cobertura_pct": contexto.get("riesgo_cobertura_pct"),
        "contexto_precalculado": bool(contexto.get("contexto_precalculado", False)),
    }


def _build_campos_editados(ficha_tecnica: dict, contexto: dict) -> dict:
    if not ficha_tecnica:
        return {}

    comparables = {
        "material_via_aplicado": contexto.get("material_via_nombre"),
        "zona_valor_aplicada": contexto.get("zona_valor_nombre"),
        "servicios_aplicados": list(contexto.get("servicios") or []),
    }
    editados = {}

    for key, value in ficha_tecnica.items():
        detected_value = comparables.get(key)
        if detected_value is None:
            editados[key] = True
            continue

        editados[key] = value != detected_value

    return editados


async def obtener_contexto_avaluo(
    db: AsyncSession, id_predio
) -> schemas.AvaluoContextResponse:
    riesgo_geom_col = await repository.get_geometry_column(db, "staging_riesgos")
    pendiente_geom_col = await repository.get_geometry_column(db, "staging_pendientes")
    riesgo_columns = await repository.get_table_columns(db, "staging_riesgos")
    pendiente_columns = await repository.get_table_columns(db, "staging_pendientes")

    riesgo_code_col = "GRIDCODE" if "GRIDCODE" in riesgo_columns else "DN"
    riesgo_grade_col = "GRADO" if "GRADO" in riesgo_columns else None
    pendiente_code_col = "DN" if "DN" in pendiente_columns else "gridcode"

    contexto = await repository.fetch_predio_context(
        db,
        id_predio,
        riesgo_geom_col=riesgo_geom_col,
        pendiente_geom_col=pendiente_geom_col,
        riesgo_code_col=riesgo_code_col,
        riesgo_grade_col=riesgo_grade_col,
        pendiente_code_col=pendiente_code_col,
    )

    if not contexto:
        raise HTTPException(status_code=404, detail="El predio no existe.")

    return schemas.AvaluoContextResponse(
        id_predio=contexto["id_predio"],
        superficie_terreno=float(contexto["superficie_terreno"]),
        superficie_terreno_fuente="predio.superficie_mensura",
        superficie_terreno_permite_edicion=True,
        pendiente_grados=(
            float(contexto["pendiente_grados"])
            if contexto.get("pendiente_grados") is not None
            else None
        ),
        id_zona_valor=contexto.get("id_zona_valor"),
        id_material_via=contexto.get("id_material_via"),
        material_via_nombre=contexto.get("material_via_nombre"),
        material_via_orden=contexto.get("material_via_orden"),
        zona_valor_nombre=contexto.get("zona_valor_nombre"),
        zona_valor_macro_zona=contexto.get("zona_valor_macro_zona"),
        zona_valor_subzona_inicio=contexto.get("zona_valor_subzona_inicio"),
        zona_valor_subzona_fin=contexto.get("zona_valor_subzona_fin"),
        zona_homogenea_codigo=contexto.get("zona_homogenea_codigo"),
        zona_homogenea_grupo=contexto.get("zona_homogenea_grupo"),
        riesgo_codigo=(
            int(contexto["riesgo_codigo"])
            if contexto.get("riesgo_codigo") is not None
            else None
        ),
        riesgo_grado=contexto.get("riesgo_grado"),
        pendiente_codigo=(
            int(contexto["pendiente_codigo"])
            if contexto.get("pendiente_codigo") is not None
            else None
        ),
        pendiente_area_m2=(
            float(contexto["pendiente_area_m2"])
            if contexto.get("pendiente_area_m2") is not None
            else None
        ),
        pendiente_cobertura_pct=(
            float(contexto["pendiente_cobertura_pct"])
            if contexto.get("pendiente_cobertura_pct") is not None
            else None
        ),
        riesgo_area_m2=(
            float(contexto["riesgo_area_m2"])
            if contexto.get("riesgo_area_m2") is not None
            else None
        ),
        riesgo_cobertura_pct=(
            float(contexto["riesgo_cobertura_pct"])
            if contexto.get("riesgo_cobertura_pct") is not None
            else None
        ),
        servicios=list(contexto.get("servicios") or []),
        construcciones_registradas=int(
            contexto.get("construcciones_registradas") or 0
        ),
        superficie_construida_total=float(
            contexto.get("superficie_construida_total") or 0.0
        ),
        geojson=contexto.get("geojson"),
        columnas_origen={
            "contexto_precalculado": bool(
                contexto.get("contexto_precalculado", False)
            ),
            "riesgo_geom_col": riesgo_geom_col,
            "riesgo_code_col": riesgo_code_col,
            "riesgo_grade_col": riesgo_grade_col,
            "pendiente_geom_col": pendiente_geom_col,
            "pendiente_code_col": pendiente_code_col,
        },
    )


async def obtener_estadisticas_contexto(db: AsyncSession) -> dict:
    return await repository.fetch_contexto_espacial_stats(db)


async def obtener_estadisticas_cobertura(db: AsyncSession) -> dict:
    return await repository.fetch_valuacion_coverage_stats(db)


async def obtener_metodologia_avaluo() -> dict:
    return {
        "superficie_terreno": {
            "fuente_automatica": "predio.superficie_mensura",
            "descripcion": (
                "La superficie automatica del terreno se toma desde el campo "
                "superficie_mensura del predio."
            ),
            "editable_en_calculo": True,
            "campo_override": "superficie_terreno_override",
        },
        "zona_homogenea": {
            "tabla": "staging_zonas_homogeneas",
            "metodo": "ST_PointOnSurface(predio.geom) + ST_Intersects",
            "campos_origen": ["zonavalor", "grupovalor", "idzonavalo"],
            "uso": (
                "Se consulta primero la zona homogenea para afinar la asignacion "
                "de zona_valor del suelo."
            ),
        },
        "material_via": {
            "tabla_origen": "staging_manzanas",
            "campo_origen": "TIPO",
            "mapeo": {
                "1": "ASFALTO",
                "2": "ADOQUIN",
                "3": "CEMENTO",
                "4": "LOSETA",
                "5": "PIEDRA",
                "6": "RIPIO",
                "0|999": "TIERRA",
            },
        },
        "servicios": {
            "tablas_origen": ["staging_predios.GSBSSERV", "staging_manzanas.SERVICIOS"],
            "lectura": "codigo binario de hasta 6 posiciones",
            "mapeo": {
                "1": "ENERGIA ELECTRICA",
                "2": "AGUA POTABLE",
                "3": "ALCANTARILLADO",
                "4": "TELEFONO",
                "5": "GAS DOMICILIARIO",
                "6": "INTERNET",
            },
        },
    }


async def listar_avaluos(
    db: AsyncSession, *, limit: int
) -> list[schemas.AvaluoListItem]:
    rows = await repository.fetch_avaluos(db, limit=limit)
    items = []

    for row in rows:
        base_imponible = float(row.get("base_imponible") or 0)
        alicuota = float(row.get("alicuota_impuesto") or 0)
        impuesto_estimado = round(base_imponible * alicuota, 3)
        items.append(
            schemas.AvaluoListItem(
                id_avaluo=row["id_avaluo"],
                id_predio=row["id_predio"],
                codigo_catastral=row.get("codigo_catastral"),
                valor_total=float(row.get("valor_total") or 0),
                impuesto_estimado=impuesto_estimado,
                fecha_calculo=row["fecha_calculo"],
                nombre_usuario=row.get("nombre_usuario"),
                estado=row.get("estado") or "PENDIENTE",
                gestion_anio=row.get("gestion_anio"),
            )
        )

    return items


async def obtener_avaluo_por_id(
    db: AsyncSession, *, id_avaluo: str
) -> schemas.AvaluoResponse:
    row = await repository.fetch_avaluo_by_id(db, id_avaluo=id_avaluo)
    if not row:
        raise HTTPException(status_code=404, detail="El avaluo no existe.")

    parametros = row.get("parametros_utilizados") or {}
    return schemas.AvaluoResponse(
        id_avaluo=row["id_avaluo"],
        id_predio=row["id_predio"],
        valor_terreno=float(row.get("valor_terreno") or 0),
        valor_construccion=float(row.get("valor_construccion") or 0),
        valor_total=float(row.get("valor_total") or 0),
        base_imponible=float(row.get("base_imponible") or 0),
        impuesto_estimado=round(
            float(row.get("base_imponible") or 0)
            * float(parametros.get("alicuota_impuesto") or 0),
            3,
        ),
        fecha_calculo=row["fecha_calculo"],
        superficie_terreno=float(
            parametros.get("superficie_terreno_aplicada")
            or parametros.get("contexto_detectado", {}).get("superficie_terreno")
            or 0
        ),
        pendiente_grados=parametros.get("pendiente_grados"),
        factor_pendiente=float(parametros.get("factor_pendiente") or 0),
        factor_riesgo=float(parametros.get("factor_riesgo") or 0),
        factor_servicios=float(parametros.get("factor_servicios") or 0),
        valor_unitario_aplicado=float(parametros.get("valor_unitario_aplicado") or 0),
        valor_unitario_construccion=float(
            parametros.get("valor_unitario_construccion") or 0
        ),
        factor_depreciacion=float(
            parametros.get("factor_depreciacion_promedio") or 0
        ),
        construcciones_procesadas=len(parametros.get("construcciones") or []),
        riesgo_dn=parametros.get("riesgo_codigo"),
        pendiente_dn=parametros.get("pendiente_codigo"),
        geojson=parametros.get("geojson"),
        parametros_utilizados=parametros,
    )


async def obtener_capa_bbox(
    db: AsyncSession,
    *,
    capa: str,
    xmin: float,
    ymin: float,
    xmax: float,
    ymax: float,
    limit: int,
):
    if capa not in {"pendientes", "riesgos", "zonas_homogeneas"}:
        raise HTTPException(status_code=404, detail="Capa no soportada.")
    srid = infer_bbox_srid(xmin, ymin, xmax, ymax)
    return await repository.fetch_capa_geojson_bbox(
        db,
        capa=capa,
        xmin=xmin,
        ymin=ymin,
        xmax=xmax,
        ymax=ymax,
        limit=limit,
        input_srid=srid,
        output_srid=srid,
    )


async def calcular_y_guardar_avaluo(
    db: AsyncSession, avaluo_in: schemas.AvaluoCreate
) -> schemas.AvaluoResponse:
    id_gestion = await repository.get_gestion_id(db, avaluo_in.gestion_anio)
    if not id_gestion:
        raise HTTPException(
            status_code=404,
            detail=f"No existe la gestion {avaluo_in.gestion_anio}.",
        )

    id_usuario = await repository.get_usuario_id(db, avaluo_in.nombre_usuario)
    if not id_usuario:
        raise HTTPException(
            status_code=404,
            detail=f"No existe el usuario '{avaluo_in.nombre_usuario}'.",
        )

    riesgo_geom_col = await repository.get_geometry_column(db, "staging_riesgos")
    pendiente_geom_col = await repository.get_geometry_column(db, "staging_pendientes")
    riesgo_columns = await repository.get_table_columns(db, "staging_riesgos")
    pendiente_columns = await repository.get_table_columns(db, "staging_pendientes")
    riesgo_code_col = "GRIDCODE" if "GRIDCODE" in riesgo_columns else "DN"
    riesgo_grade_col = "GRADO" if "GRADO" in riesgo_columns else None
    pendiente_code_col = "DN" if "DN" in pendiente_columns else "gridcode"
    contexto = await repository.fetch_predio_context(
        db,
        avaluo_in.id_predio,
        riesgo_geom_col=riesgo_geom_col,
        pendiente_geom_col=pendiente_geom_col,
        riesgo_code_col=riesgo_code_col,
        riesgo_grade_col=riesgo_grade_col,
        pendiente_code_col=pendiente_code_col,
    )

    if not contexto:
        raise HTTPException(status_code=404, detail="El predio no existe.")

    id_esquema = await repository.get_latest_esquema_id(db)
    factor_pendiente = rules.factor_pendiente_desde_dn(contexto.get("pendiente_codigo"))
    factor_riesgo = rules.factor_riesgo_desde_dn(contexto.get("riesgo_codigo"))
    valor_base_m2 = avaluo_in.valor_base_m2

    if avaluo_in.usar_tablas_maestras:
        valor_suelo = await repository.get_valor_suelo(
            db,
            id_esquema=id_esquema,
            id_zona_valor=contexto.get("id_zona_valor"),
            id_material_via=contexto.get("id_material_via"),
        )
        if valor_suelo is not None:
            valor_base_m2 = valor_suelo

    factor_servicios = avaluo_in.factor_servicios
    if avaluo_in.usar_tablas_maestras:
        factor_servicios = await repository.get_factor_servicios(
            db, id_predio=avaluo_in.id_predio
        )

    superficie_terreno = float(
        avaluo_in.superficie_terreno_override or contexto["superficie_terreno"]
    )
    superficie_origen = (
        "manual.superficie_terreno_override"
        if avaluo_in.superficie_terreno_override is not None
        else "predio.superficie_mensura"
    )

    valor_terreno, valor_unitario_aplicado = rules.calcular_valor_terreno(
        superficie_terreno=superficie_terreno,
        valor_base_m2=valor_base_m2,
        factor_servicios=factor_servicios,
        factor_pendiente=factor_pendiente,
        factor_riesgo=factor_riesgo,
    )
    construcciones = []
    if id_esquema:
        construcciones = await repository.fetch_construcciones_context(
            db,
            id_predio=avaluo_in.id_predio,
            id_esquema=id_esquema,
            gestion_anio=avaluo_in.gestion_anio,
        )

    valor_construccion = 0.0
    valor_unitario_construccion = 0.0
    factor_depreciacion_promedio = 1.0

    if construcciones:
        desglose_construcciones = []
        suma_factores = 0.0
        for construccion in construcciones:
            factor_dep = float(construccion.get("factor_depreciacion") or 1.0)
            valor_tipologia_m2 = float(construccion.get("valor_tipologia_m2") or 0.0)
            valor_construccion_item, valor_unitario_item = (
                rules.calcular_valor_construccion(
                    superficie_construida=float(
                        construccion.get("superficie_construida") or 0.0
                    ),
                    valor_tipologia_m2=valor_tipologia_m2,
                    factor_depreciacion=factor_dep,
                )
            )
            valor_construccion += valor_construccion_item
            valor_unitario_construccion = max(
                valor_unitario_construccion, valor_unitario_item
            )
            suma_factores += factor_dep
            desglose_construcciones.append(
                {
                    "id_construccion": str(construccion["id_construccion"]),
                    "tipologia_codigo": construccion.get("tipologia_codigo"),
                    "superficie_construida": float(
                        construccion.get("superficie_construida") or 0.0
                    ),
                    "anio_construccion": construccion.get("anio_construccion"),
                    "valor_tipologia_m2": valor_tipologia_m2,
                    "factor_depreciacion": factor_dep,
                    "valor_unitario_aplicado": valor_unitario_item,
                    "valor_construccion": valor_construccion_item,
                }
            )
        factor_depreciacion_promedio = round(
            suma_factores / len(construcciones), 4
        )
    else:
        desglose_construcciones = []

    valor_construccion = round(valor_construccion, 2)
    valor_total = round(valor_terreno + valor_construccion, 2)
    base_imponible = valor_total
    impuesto_estimado = rules.calcular_impuesto(
        base_imponible=base_imponible,
        alicuota_impuesto=avaluo_in.alicuota_impuesto,
    )
    ficha_tecnica = _normalizar_ficha_tecnica(avaluo_in.ficha_tecnica)
    contexto_detectado = _build_contexto_detectado(contexto)
    contexto_detectado["superficie_terreno_aplicada"] = superficie_terreno
    contexto_detectado["superficie_terreno_origen_aplicado"] = superficie_origen
    campos_editados = _build_campos_editados(ficha_tecnica, contexto)

    parametros_utilizados = _to_json_safe({
        "gestion_anio": avaluo_in.gestion_anio,
        "nombre_usuario": avaluo_in.nombre_usuario,
        "valor_base_m2": valor_base_m2,
        "factor_servicios": factor_servicios,
        "factor_pendiente": factor_pendiente,
        "factor_riesgo": factor_riesgo,
        "valor_unitario_aplicado": valor_unitario_aplicado,
        "superficie_terreno_aplicada": superficie_terreno,
        "superficie_terreno_origen_aplicado": superficie_origen,
        "valor_unitario_construccion": valor_unitario_construccion,
        "factor_depreciacion_promedio": factor_depreciacion_promedio,
        "alicuota_impuesto": avaluo_in.alicuota_impuesto,
        "riesgo_codigo": contexto.get("riesgo_codigo"),
        "riesgo_grado": contexto.get("riesgo_grado"),
        "pendiente_codigo": contexto.get("pendiente_codigo"),
        "esquema_valuacion_id": str(id_esquema) if id_esquema else None,
        "uso_tablas_maestras": avaluo_in.usar_tablas_maestras,
        "construcciones": desglose_construcciones,
        "columnas_origen": {
            "contexto_precalculado": bool(
                contexto.get("contexto_precalculado", False)
            ),
            "riesgo_geom_col": riesgo_geom_col,
            "riesgo_code_col": riesgo_code_col,
            "riesgo_grade_col": riesgo_grade_col,
            "pendiente_geom_col": pendiente_geom_col,
            "pendiente_code_col": pendiente_code_col,
        },
        "fuente_contexto": "predio + staging_riesgos + staging_pendientes",
        "contexto_detectado": contexto_detectado,
        "ficha_tecnica": ficha_tecnica,
        "campos_editados": campos_editados,
    })

    nuevo_avaluo = await repository.save_avaluo_predio(
        db,
        id_gestion=id_gestion,
        id_predio=avaluo_in.id_predio,
        usuario_creador_id=id_usuario,
        valor_terreno=valor_terreno,
        valor_construccion=valor_construccion,
        valor_total=valor_total,
        base_imponible=base_imponible,
        parametros_utilizados=parametros_utilizados,
    )

    return schemas.AvaluoResponse(
        id_avaluo=nuevo_avaluo.id_avaluo,
        id_predio=nuevo_avaluo.id_predio,
        valor_terreno=float(nuevo_avaluo.valor_terreno or 0),
        valor_construccion=float(nuevo_avaluo.valor_construccion or 0),
        valor_total=float(nuevo_avaluo.valor_total),
        base_imponible=float(nuevo_avaluo.base_imponible),
        impuesto_estimado=impuesto_estimado,
        fecha_calculo=nuevo_avaluo.fecha_calculo,
        superficie_terreno=superficie_terreno,
        pendiente_grados=(
            float(contexto["pendiente_grados"])
            if contexto.get("pendiente_grados") is not None
            else None
        ),
        factor_pendiente=factor_pendiente,
        factor_riesgo=factor_riesgo,
        factor_servicios=factor_servicios,
        valor_unitario_aplicado=valor_unitario_aplicado,
        valor_unitario_construccion=valor_unitario_construccion,
        factor_depreciacion=factor_depreciacion_promedio,
        construcciones_procesadas=len(construcciones),
        riesgo_dn=contexto.get("riesgo_codigo"),
        pendiente_dn=contexto.get("pendiente_codigo"),
        geojson=contexto.get("geojson"),
        parametros_utilizados=parametros_utilizados,
    )

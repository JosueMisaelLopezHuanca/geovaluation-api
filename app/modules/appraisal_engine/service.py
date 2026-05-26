import csv
import io
import json
import logging
from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.predios.service import infer_bbox_srid
from app.modules.appraisal_engine import repository, rules, schemas
from app.modules.appraisal_engine.cache import appraisal_cache

logger = logging.getLogger("catastro.appraisal_v2")
PUBLIC_APPRAISAL_USER = "consulta_publica"
FISCAL_SOURCE_YEAR = 2023
FISCAL_SOURCE_NAME = "RA GAMLP/ATM No. 14/2023 - Anexo A"
FISCAL_SOURCE_STATUS = "Fuente oficial verificada para 2023; confirmar vigencia para la gestion consultada."

PUBLIC_CATALOGS = {
    "forma_lote": [
        ("REGULAR", "Regular", "Lote con forma simple y aprovechamiento directo."),
        ("IRREGULAR", "Irregular", "Lote con quiebres, retiros o geometria poco uniforme."),
        ("ESQUINERO", "Esquinero", "Predio con frente hacia dos vias."),
        ("PASILLO", "Pasillo", "Acceso angosto o predio interior."),
        ("LADERA", "Ladera", "Terreno con condicion topografica marcada."),
    ],
    "uso_suelo": [
        ("RESIDENCIAL", "Residencial", "Uso principal de vivienda."),
        ("MIXTO", "Mixto", "Vivienda combinada con comercio u otra actividad."),
        ("COMERCIAL", "Comercial", "Uso predominante de comercio o servicios."),
        ("INSTITUCIONAL", "Institucional", "Equipamiento publico, educativo, salud o similar."),
        ("EQUIPAMIENTO", "Equipamiento", "Infraestructura de soporte urbano."),
        ("LOTE BALDIO", "Lote baldio", "Predio sin construccion declarada."),
    ],
    "tipo_via": [
        ("ASFALTO", "Asfalto", "Via pavimentada con asfalto."),
        ("ADOQUIN", "Adoquin", "Via con adoquinado."),
        ("CEMENTO", "Cemento", "Via pavimentada con cemento."),
        ("LOSETA", "Loseta", "Via pavimentada con loseta."),
        ("PIEDRA", "Piedra", "Via con piedra o empedrado."),
        ("RIPIO", "Ripio", "Via afirmada con ripio."),
        ("TIERRA", "Tierra", "Via sin tratamiento pavimentado."),
    ],
    "riesgo_territorial": [
        ("MUY BAJO", "Muy bajo", None),
        ("BAJO", "Bajo", None),
        ("MODERADO", "Moderado", None),
        ("ALTO", "Alto", None),
        ("MUY ALTO", "Muy alto", None),
    ],
    "calidad_constructiva": [
        ("ALTA", "Alta", "Acabados y materiales superiores al promedio."),
        ("MEDIA", "Media", "Condicion constructiva habitual."),
        ("BASICA", "Basica", "Materiales y acabados simples."),
        ("SOCIAL", "Social", "Construccion de interes social o economica."),
        ("MARGINAL", "Marginal", "Construccion precaria o de baja calidad."),
        ("LUJO", "Lujo", "Construccion de alta gama."),
    ],
    "estado_conservacion": [
        ("EXCELENTE", "Excelente", None),
        ("BUENO", "Bueno", None),
        ("REGULAR", "Regular", None),
        ("MALO", "Malo", None),
    ],
    "uso_construccion": [
        ("VIVIENDA", "Vivienda", None),
        ("COMERCIO", "Comercio", None),
        ("MIXTO", "Mixto", None),
        ("OFICINA", "Oficina", None),
        ("DEPOSITO", "Deposito", None),
        ("EQUIPAMIENTO", "Equipamiento", None),
        ("OTRO", "Otro", None),
    ],
    "material_estructural": [
        ("HORMIGON ARMADO", "Hormigon armado", None),
        ("LADRILLO", "Ladrillo", None),
        ("ADOBE", "Adobe", None),
        ("MIXTO", "Mixto", None),
        ("MADERA", "Madera", None),
        ("METALICO", "Metalico", None),
        ("OTRO", "Otro", None),
    ],
    "tipo_cubierta": [
        ("LOSA", "Losa", None),
        ("CALAMINA", "Calamina", None),
        ("TEJA", "Teja", None),
        ("FIBROCEMENTO", "Fibrocemento", None),
        ("MIXTA", "Mixta", None),
        ("OTRO", "Otro", None),
    ],
}


MANUAL_CONTEXT_FIELDS = [
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

MANUAL_CONTROL_FIELDS = {
    "motivo",
    "es_temporal",
    "usar_valor_unitario_manual",
    "usar_coeficiente_manual",
    "usar_depreciacion_manual",
}


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


async def _resolve_usuario_id(db: AsyncSession, nombre_usuario: str):
    usuario_id = await repository.get_usuario_id(db, nombre_usuario)
    if usuario_id:
        return usuario_id

    if nombre_usuario == PUBLIC_APPRAISAL_USER:
        return await repository.ensure_public_user(db, nombre_usuario)

    raise HTTPException(status_code=404, detail=f"No existe el usuario '{nombre_usuario}'.")


def get_public_catalogs() -> schemas.PublicCatalogsResponse:
    return schemas.PublicCatalogsResponse(
        **{
            catalog_name: [
                schemas.CatalogOption(value=value, label=label, description=description)
                for value, label, description in options
            ]
            for catalog_name, options in PUBLIC_CATALOGS.items()
        }
    )


def _build_source_detail(value: Any, source: str, *, temporary: bool = False, note: str | None = None):
    return schemas.DataSourceDetail(value=value, source=source, is_temporary=temporary, note=note)


def _first_non_null(*values):
    for value in values:
        if value is not None:
            return value
    return None


def _resolve_special_location_flags(value: str | None) -> tuple[bool, bool]:
    classification = str(value or "").upper()
    return (
        classification in {"ESQUINA", "ESQUINA_AVENIDA"},
        classification in {"AVENIDA", "ESQUINA_AVENIDA"},
    )


def _normalize_manual(payload: schemas.ManualInputPayload | None) -> dict:
    return payload.model_dump(exclude_unset=True) if payload else {}


def _bool_service_name_map() -> dict[str, str]:
    return {
        "agua": "AGUA POTABLE",
        "alcantarillado": "ALCANTARILLADO",
        "electricidad": "ENERGIA ELECTRICA",
        "telefono": "TELEFONO",
        "gas": "GAS DOMICILIARIO",
        "internet": "INTERNET",
        "alumbrado_publico": "ALUMBRADO PUBLICO",
    }


def _resolve_services(automatic_services: list[str], manual_data: dict) -> tuple[list[str], dict[str, bool], dict[str, schemas.DataSourceDetail]]:
    automatic_set = set(automatic_services)
    full_services = {}
    source_map = {}
    for field_name, label in _bool_service_name_map().items():
        manual_value = manual_data.get(field_name)
        if manual_value is not None:
            full_services[label] = bool(manual_value)
            source_map[label] = _build_source_detail(
                bool(manual_value),
                "manual",
                temporary=bool(manual_data.get("es_temporal")),
            )
        else:
            full_services[label] = label in automatic_set
            source_map[label] = _build_source_detail(label in automatic_set, "automatico")
    active = [name for name, enabled in full_services.items() if enabled]
    return active, full_services, source_map


def _resolve_difference(superficie_gis: float, superficie_legal: float | None) -> schemas.DifferenceReport:
    return schemas.DifferenceReport(**rules.compute_difference(superficie_gis, superficie_legal))


def _fmt_number(value: float | int | None, precision: int = 4) -> str:
    if value is None:
        return "sin_dato"
    if isinstance(value, int):
        return str(value)
    return f"{float(value):.{precision}f}".rstrip("0").rstrip(".")


def _table_descriptor(name: str, normative: dict, *, description: str | None = None) -> dict:
    return {
        "nombre": name,
        "gestion_anio": normative["gestion_anio"],
        "version_codigo": normative["version_codigo"],
        "resolucion_municipal": normative.get("resolucion_municipal"),
        "descripcion": description,
    }


def _build_formula_detail(
    *,
    symbolic: str,
    components: list[schemas.FormulaComponent],
    result: float,
) -> schemas.FormulaDetail:
    expansion_parts = [_fmt_number(component.valor, 4) for component in components]
    expanded = " x ".join(expansion_parts)
    if expanded:
        expanded = f"{expanded} = {_fmt_number(result, 2)}"
    else:
        expanded = _fmt_number(result, 2)
    return schemas.FormulaDetail(
        simbolica=symbolic,
        expandida=expanded,
        resultado=round(float(result), 2),
        componentes=components,
    )


def _build_normative_metadata(normative: dict) -> schemas.NormativeMetadata:
    return schemas.NormativeMetadata(
        gestion_anio=int(normative["gestion_anio"]),
        nombre=normative["nombre"],
        version_codigo=normative["version_codigo"],
        fuente_gestion_anio=FISCAL_SOURCE_YEAR,
        vigente_para_gestion=int(normative["gestion_anio"]),
        alcance=FISCAL_SOURCE_STATUS,
        resolucion_municipal=normative.get("resolucion_municipal"),
        detalle_normativo=normative.get("detalle_normativo"),
    )


async def _resolve_predio_context(db: AsyncSession, predio_id: str) -> tuple[dict, dict | None, dict | None]:
    context = await repository.fetch_predio_gis_context(db, predio_id)
    if not context:
        raise HTTPException(status_code=404, detail="Predio no encontrado.")
    manual_data = await repository.get_manual_data(db, predio_id)
    surface_override = await repository.get_surface_override(db, predio_id)
    return context, manual_data, surface_override


def _build_context_response(context: dict, manual_data: dict | None, surface_override: dict | None) -> schemas.PredioGisContextResponse:
    manual_data = manual_data or {}
    surface_manual = _first_non_null(
        manual_data.get("superficie_manual"),
        surface_override.get("superficie_manual") if surface_override else None,
    )
    superficie_gis = float(context["superficie_gis"])
    superficie_legal = float(context["superficie_legal"]) if context.get("superficie_legal") is not None else None
    superficie_calculo, superficie_fuente = rules.choose_surface(superficie_gis, superficie_legal, surface_manual)
    surface_source_badge = {
        "superficie_manual": "manual",
        "superficie_legal": "oficial",
        "superficie_gis": "automatico",
    }.get(superficie_fuente, "sin_dato")

    services_active, full_services, service_sources = _resolve_services(
        context.get("servicios_oficiales", []),
        manual_data,
    )
    pendiente_value, pendiente_source = rules.choose_value(
        manual_data.get("pendiente_manual"),
        context.get("pendiente_grados"),
        context.get("pendiente_codigo"),
    )
    riesgo_value, riesgo_source = rules.choose_value(
        manual_data.get("riesgo_territorial_manual"),
        context.get("riesgo_grado"),
        context.get("riesgo_grado"),
    )

    fuentes = {
        "superficie_gis": _build_source_detail(superficie_gis, "automatico", note="predio.superficie_mensura"),
        "superficie_legal": _build_source_detail(
            superficie_legal,
            "oficial" if superficie_legal is not None else "sin_dato",
            note="predio.superficie_titulo",
        ),
        "superficie": _build_source_detail(
            superficie_calculo,
            surface_source_badge,
            temporary=bool(manual_data.get("es_temporal")),
            note=superficie_fuente,
        ),
        "frente": _build_source_detail(
            _first_non_null(manual_data.get("frente"), context.get("frente")),
            "manual" if manual_data.get("frente") is not None else "automatico",
        ),
        "fondo": _build_source_detail(
            _first_non_null(manual_data.get("fondo"), context.get("fondo")),
            "manual" if manual_data.get("fondo") is not None else "automatico",
        ),
        "forma_lote": _build_source_detail(
            _first_non_null(manual_data.get("forma_lote"), context.get("forma_lote")),
            "manual" if manual_data.get("forma_lote") is not None else "automatico",
        ),
        "uso_suelo": _build_source_detail(
            manual_data.get("uso_suelo"),
            "manual" if manual_data.get("uso_suelo") is not None else "sin_dato",
        ),
        "tipo_via": _build_source_detail(
            _first_non_null(manual_data.get("tipo_via"), context.get("material_via_codigo")),
            "manual" if manual_data.get("tipo_via") is not None else "automatico",
        ),
        "pendiente": _build_source_detail(
            pendiente_value,
            pendiente_source,
            temporary=bool(manual_data.get("es_temporal")),
        ),
        "riesgo": _build_source_detail(
            riesgo_value,
            riesgo_source,
            temporary=bool(manual_data.get("es_temporal")),
        ),
        "zona_homogenea": _build_source_detail(
            _first_non_null(manual_data.get("zona_homogenea_manual"), context.get("zona_homogenea_codigo")),
            "manual" if manual_data.get("zona_homogenea_manual") is not None else "automatico",
        ),
        "zona_tributaria": _build_source_detail(
            _first_non_null(manual_data.get("zona_tributaria_manual"), context.get("zona_tributaria_codigo")),
            "manual" if manual_data.get("zona_tributaria_manual") is not None else "oficial",
        ),
        "coordenadas": _build_source_detail(
            _first_non_null(manual_data.get("coordenadas_manual"), context.get("coordenadas")),
            "manual" if manual_data.get("coordenadas_manual") is not None else "automatico",
        ),
        "distrito": _build_source_detail(
            _first_non_null(manual_data.get("distrito_manual"), context.get("distrito")),
            "manual" if manual_data.get("distrito_manual") is not None else "automatico",
        ),
        "macrodistrito": _build_source_detail(
            _first_non_null(manual_data.get("macrodistrito_manual"), context.get("macrodistrito")),
            "manual" if manual_data.get("macrodistrito_manual") is not None else "automatico",
        ),
    }
    for name, source in service_sources.items():
        fuentes[f"servicio:{name}"] = source

    return schemas.PredioGisContextResponse(
        predio_id=context["id_predio"],
        superficie_gis=superficie_gis,
        superficie_legal=superficie_legal,
        superficie_manual=float(surface_manual) if surface_manual is not None else None,
        superficie_calculo=superficie_calculo,
        superficie_fuente=superficie_fuente,
        zona_homogenea_codigo=_first_non_null(manual_data.get("zona_homogenea_manual"), context.get("zona_homogenea_codigo")),
        zona_homogenea_grupo=context.get("zona_homogenea_grupo"),
        zona_tributaria_codigo=_first_non_null(manual_data.get("zona_tributaria_manual"), context.get("zona_tributaria_codigo")),
        material_via_codigo=_first_non_null(manual_data.get("tipo_via"), context.get("material_via_codigo")),
        pendiente_codigo=context.get("pendiente_codigo"),
        pendiente_grados=float(context["pendiente_grados"]) if context.get("pendiente_grados") is not None else None,
        pendiente_final=pendiente_value,
        pendiente_fuente=pendiente_source,
        riesgo_codigo=context.get("riesgo_codigo"),
        riesgo_grado=context.get("riesgo_grado"),
        riesgo_final=riesgo_value,
        riesgo_fuente=riesgo_source,
        servicios_oficiales=[service for service in services_active if service in rules.OFFICIAL_SERVICES],
        servicios_completos=full_services,
        frente=float(_first_non_null(manual_data.get("frente"), context.get("frente"))) if _first_non_null(manual_data.get("frente"), context.get("frente")) is not None else None,
        fondo=float(_first_non_null(manual_data.get("fondo"), context.get("fondo"))) if _first_non_null(manual_data.get("fondo"), context.get("fondo")) is not None else None,
        forma_lote=_first_non_null(manual_data.get("forma_lote"), context.get("forma_lote")),
        uso_suelo=manual_data.get("uso_suelo"),
        tipo_via=_first_non_null(manual_data.get("tipo_via"), context.get("material_via_codigo")),
        acceso_vehicular=manual_data.get("acceso_vehicular"),
        coordenadas=_first_non_null(manual_data.get("coordenadas_manual"), context.get("coordenadas")),
        distrito=str(_first_non_null(manual_data.get("distrito_manual"), context.get("distrito"))) if _first_non_null(manual_data.get("distrito_manual"), context.get("distrito")) is not None else None,
        macrodistrito=str(_first_non_null(manual_data.get("macrodistrito_manual"), context.get("macrodistrito"))) if _first_non_null(manual_data.get("macrodistrito_manual"), context.get("macrodistrito")) is not None else None,
        tipo_riesgo=manual_data.get("tipo_riesgo"),
        afectacion_riesgo=manual_data.get("afectacion_riesgo"),
        diferencia_superficie=_resolve_difference(superficie_gis, superficie_legal),
        fuentes=fuentes,
        overlays_utilizados=[
            "staging_zonas_homogeneas",
            "predio_contexto_espacial",
            "predio_servicio",
            "material_via",
            "zona_valor",
        ],
    )


async def get_predio_gis_context(db: AsyncSession, predio_id: str) -> schemas.PredioGisContextResponse:
    context, manual_data, surface_override = await _resolve_predio_context(db, predio_id)
    return _build_context_response(context, manual_data, surface_override)


def _build_audit_entries(
    context: schemas.PredioGisContextResponse,
    manual: dict,
    *,
    motivo: str | None,
) -> list[dict]:
    if not manual:
        return []

    auto_snapshot = {
        "superficie_manual": context.superficie_calculo,
        "frente": context.frente,
        "fondo": context.fondo,
        "forma_lote": context.forma_lote,
        "uso_suelo": context.uso_suelo,
        "tipo_via": context.tipo_via,
        "acceso_vehicular": context.acceso_vehicular,
        "pendiente_manual": context.pendiente_final,
        "zona_homogenea_manual": context.zona_homogenea_codigo,
        "zona_tributaria_manual": context.zona_tributaria_codigo,
        "coordenadas_manual": context.coordenadas,
        "distrito_manual": context.distrito,
        "macrodistrito_manual": context.macrodistrito,
        "agua": context.servicios_completos.get("AGUA POTABLE"),
        "alcantarillado": context.servicios_completos.get("ALCANTARILLADO"),
        "electricidad": context.servicios_completos.get("ENERGIA ELECTRICA"),
        "telefono": context.servicios_completos.get("TELEFONO"),
        "gas": context.servicios_completos.get("GAS DOMICILIARIO"),
        "internet": context.servicios_completos.get("INTERNET"),
        "alumbrado_publico": context.servicios_completos.get("ALUMBRADO PUBLICO"),
        "riesgo_territorial_manual": context.riesgo_final,
        "tipo_riesgo": context.tipo_riesgo,
        "afectacion_riesgo": context.afectacion_riesgo,
    }
    entries = []
    for field in MANUAL_CONTEXT_FIELDS:
        if field not in manual:
            continue
        new_value = manual.get(field)
        if new_value is None:
            continue
        entries.append(
            {
                "campo": field,
                "valor_anterior": None if auto_snapshot.get(field) is None else str(auto_snapshot.get(field)),
                "valor_nuevo": str(new_value),
                "fuente_anterior": "automatico",
                "fuente_nueva": "manual",
                "motivo": motivo,
                "es_temporal": bool(manual.get("es_temporal", False)),
            }
        )
    return entries


def _has_manual_payload_data(payload: dict) -> bool:
    for key, value in payload.items():
        if key in MANUAL_CONTROL_FIELDS:
            continue
        if isinstance(value, bool):
            return True
        if value not in (None, ""):
            return True
    return False


async def _appraise_building_block(
    db: AsyncSession,
    *,
    block: schemas.BuildingBlockInput,
    normative_version_id: str,
    gestion_anio: int,
    avaluo_tipo: str = rules.APPRAISAL_FISCAL,
    regimen_inmueble: str = "VIVIENDA_FAMILIAR",
    zona_tributaria_codigo: str | None = None,
) -> tuple[dict, schemas.FormulaDetail]:
    is_horizontal = regimen_inmueble == "PROPIEDAD_HORIZONTAL"
    categoria = "PROPIEDAD_HORIZONTAL" if is_horizontal else "PREDIO"
    tipologia = await repository.resolve_tipologia_constructiva(
        db, normative_version_id, block.calidad_constructiva, categoria=categoria
    )
    if not tipologia:
        raise HTTPException(
            status_code=409,
            detail=(
                f"No existe tipologia oficial para calidad '{block.calidad_constructiva}' "
                f"en el regimen '{regimen_inmueble}'."
            ),
        )

    is_commercial = avaluo_tipo == rules.APPRAISAL_COMERCIAL
    matrix = None
    if is_commercial:
        matrix = await repository.resolve_construction_matrix(
            db,
            normative_version_id,
            calidad=block.calidad_constructiva,
            material_estructural=block.material_estructural,
            tipo_cubierta=block.tipo_cubierta,
            estado_conservacion=block.estado_conservacion,
            remodelaciones=block.remodelaciones,
        )
        if not matrix:
            raise HTTPException(
                status_code=409,
                detail=(
                    "No existe matriz constructiva referencial para la calidad y estado seleccionados. "
                    "Revisa el estado de conservacion o carga una matriz comercial aplicable."
                ),
            )

    edad = max(0, gestion_anio - block.anio_construccion)
    official_depreciation = await repository.resolve_depreciacion_factor(
        db, normative_version_id, edad
    )
    depreciation, depreciation_source = rules.choose_value(
        block.depreciacion_manual,
        official_depreciation,
        official_depreciation,
        manual_enabled=is_commercial and bool(block.usar_depreciacion_manual),
    )
    factor_ubicacion_ph = 1.0
    if is_horizontal:
        factor_ubicacion_ph = await repository.get_ph_location_factor(
            db, normative_version_id, zona_tributaria_codigo
        )
        if factor_ubicacion_ph is None:
            raise HTTPException(
                status_code=422,
                detail=(
                    "La propiedad horizontal requiere una zona tributaria con factor "
                    f"de ubicacion registrado. Zona recibida: '{zona_tributaria_codigo}'."
                ),
            )

    factor_material = float(matrix.get("factor_material") or 1.0) if matrix else 1.0
    factor_cubierta = float(matrix.get("factor_cubierta") or 1.0) if matrix else 1.0
    factor_estado = float(matrix.get("factor_estado") or 1.0) if matrix else 1.0
    factor_remodelacion = float(matrix.get("factor_remodelacion") or 1.0) if matrix else 1.0
    requested_material = str(block.material_estructural or "GENERICA").upper()
    requested_cover = str(block.tipo_cubierta or "GENERICA").upper()
    applied_material = str(matrix.get("material_estructural") or "NO_APLICA_FISCAL").upper() if matrix else "NO_APLICA_FISCAL"
    applied_cover = str(matrix.get("tipo_cubierta") or "NO_APLICA_FISCAL").upper() if matrix else "NO_APLICA_FISCAL"
    used_generic_matrix = bool(matrix) and (
        requested_material != applied_material or requested_cover != applied_cover
    )
    valor_tipologia_ajustado = round(
        float(tipologia["valor_m2"]) * factor_material * factor_cubierta * factor_estado * factor_remodelacion,
        4,
    )
    block_value = rules.calculate_building_block_value(
        block.superficie,
        valor_tipologia_ajustado,
        float(depreciation),
    )
    block_value = round(block_value * float(factor_ubicacion_ph), 2)

    formula_components = [
        schemas.FormulaComponent(
            nombre="superficie_bloque",
            valor=round(block.superficie, 2),
            fuente="manual",
            tabla="input.bloques",
        ),
        schemas.FormulaComponent(
            nombre="valor_tipologia_ajustado_m2" if is_commercial else "valor_tipologia_m2",
            valor=valor_tipologia_ajustado,
            fuente="oficial",
            tabla=(
                "tabla_tipologias_constructivas + tabla_matriz_calidad_material"
                if is_commercial
                else "tabla_tipologias_constructivas"
            ),
            descripcion=(
                (
                    f"{block.calidad_constructiva.upper()} / "
                    f"{applied_material} / "
                    f"{applied_cover} / "
                    f"{str(block.estado_conservacion or 'BUENO').upper()}"
                    + (
                        f" (declarado: {requested_material} / {requested_cover}; matriz generica aplicada)"
                        if used_generic_matrix
                        else ""
                    )
                )
                if is_commercial
                else f"{block.calidad_constructiva.upper()} / fuente oficial {FISCAL_SOURCE_YEAR}"
            ),
        ),
        schemas.FormulaComponent(
            nombre="factor_antiguedad",
            valor=float(depreciation),
            fuente=depreciation_source,
            tabla="tabla_depreciacion_antiguedad",
        ),
    ]
    if is_horizontal:
        formula_components.append(
            schemas.FormulaComponent(
                nombre="factor_ubicacion_ph",
                valor=float(factor_ubicacion_ph),
                fuente="oficial",
                tabla="tabla_factores_ubicacion_ph",
                descripcion=zona_tributaria_codigo,
            )
        )
    formula_block = _build_formula_detail(
        symbolic=(
            "superficie_unidad x valor_tipologia_ph_m2 x factor_antiguedad x factor_ubicacion_ph"
            if is_horizontal
            else (
                "superficie x valor_tipologia_ajustado x factor_antiguedad"
                if is_commercial
                else "superficie x valor_tipologia_m2 x factor_antiguedad"
            )
        ),
        components=formula_components,
        result=block_value,
    )

    building_block = {
        "regimen_inmueble": regimen_inmueble,
        "superficie": round(block.superficie, 2),
        "calidad_constructiva": block.calidad_constructiva.upper(),
        "anio_construccion": block.anio_construccion,
        "edad": edad,
        "estado_conservacion": block.estado_conservacion,
        "numero_pisos": block.numero_pisos,
        "uso_construccion": block.uso_construccion,
        "material_estructural": block.material_estructural,
        "tipo_cubierta": block.tipo_cubierta,
        "remodelaciones": block.remodelaciones,
        "tipologia_constructiva_id": str(tipologia["tipologia_constructiva_id"]),
        "tipologia_origen_codigo": tipologia.get("tipologia_origen_codigo"),
        "categoria": tipologia.get("categoria"),
        "valor_tipologia_m2": float(tipologia["valor_m2"]),
        "valor_tipologia_ajustado_m2": valor_tipologia_ajustado,
        "factor_antiguedad": float(depreciation),
        "factor_antiguedad_fuente": depreciation_source,
        "factor_material": factor_material,
        "factor_cubierta": factor_cubierta,
        "factor_estado": factor_estado,
        "factor_remodelacion": factor_remodelacion,
        "factor_ubicacion_ph": float(factor_ubicacion_ph),
        "ajustes_comerciales_aplicados": is_commercial,
        "matriz_material_aplicada": applied_material,
        "matriz_cubierta_aplicada": applied_cover,
        "matriz_generica_aplicada": used_generic_matrix,
        "valor_bloque": block_value,
        "formula": formula_block.model_dump(mode="json"),
    }
    return building_block, formula_block


async def _assemble_appraisal(
    db: AsyncSession,
    *,
    payload: schemas.AppraisalRequestV2 | schemas.AppraisalPreviewRequest,
    persist: bool,
) -> schemas.AppraisalResponseV2:
    avaluo_tipo = payload.avaluo_tipo.upper()
    regimen_inmueble = payload.regimen_inmueble
    is_horizontal = regimen_inmueble == "PROPIEDAD_HORIZONTAL"
    if avaluo_tipo not in {rules.APPRAISAL_FISCAL, rules.APPRAISAL_COMERCIAL}:
        raise HTTPException(status_code=422, detail=f"Modo de avaluo no soportado: {payload.avaluo_tipo}")
    if is_horizontal and not payload.bloques:
        raise HTTPException(
            status_code=422,
            detail="La propiedad horizontal requiere al menos una unidad construida para valorar.",
        )

    normative = await repository.get_normative_version(db, payload.gestion_anio)
    if not normative:
        raise HTTPException(status_code=404, detail=f"No existe normativa activa para la gestion {payload.gestion_anio}.")

    # A public preview must be read-only; user provisioning is only needed for persisted cases.
    usuario_id = await _resolve_usuario_id(db, payload.usuario) if persist else None

    context_raw, manual_current, surface_override = await _resolve_predio_context(db, str(payload.predio_id))
    manual_payload = _normalize_manual(getattr(payload, "manual", None))
    persisted_manual_payload = {
        key: value
        for key, value in manual_payload.items()
        if value is not None or isinstance(value, bool)
    }
    if getattr(payload, "superficie_manual", None) is not None:
        persisted_manual_payload["superficie_manual"] = payload.superficie_manual

    has_manual_data = _has_manual_payload_data(persisted_manual_payload)
    override_reason = (
        persisted_manual_payload.get("motivo")
        or getattr(payload, "superficie_override_reason", None)
        or getattr(payload, "observaciones", None)
    )
    if persist and has_manual_data and not override_reason:
        raise HTTPException(status_code=422, detail="Debe enviar motivo para cambios manuales.")
    if not has_manual_data:
        persisted_manual_payload = {}

    merged_manual = {**(manual_current or {}), **persisted_manual_payload}
    context = _build_context_response(context_raw, merged_manual, surface_override)

    services_active, _, _ = _resolve_services(context_raw.get("servicios_oficiales", []), merged_manual)
    service_score, servicios_oficiales = rules.compute_service_score(services_active)
    factor_servicios = service_score
    factor_servicios_minimo_aplicado = not servicios_oficiales

    if merged_manual.get("usar_valor_unitario_manual") and merged_manual.get("valor_unitario_manual") is None:
        raise HTTPException(status_code=422, detail="Debe indicar el valor unitario manual antes de activarlo.")
    if merged_manual.get("usar_coeficiente_manual") and merged_manual.get("coeficiente_manual") is None:
        raise HTTPException(status_code=422, detail="Debe indicar el coeficiente manual antes de activarlo.")
    for index, block in enumerate(payload.bloques, start=1):
        if block.anio_construccion > payload.gestion_anio:
            raise HTTPException(
                status_code=422,
                detail=f"El anio de construccion del bloque {index} no puede ser posterior a la gestion del avaluo.",
            )
        if (
            avaluo_tipo == rules.APPRAISAL_COMERCIAL
            and block.usar_depreciacion_manual
            and block.depreciacion_manual is None
        ):
            raise HTTPException(
                status_code=422,
                detail=f"Debe indicar la depreciacion manual del bloque {index} antes de activarla.",
            )

    if is_horizontal:
        official_land_value = 0.0
        valor_unitario_final = 0.0
        valor_unitario_fuente = "no_aplica_propiedad_horizontal"
        factor_pendiente = 1.0
        pendiente_factor_fuente = "no_aplica_propiedad_horizontal"
    else:
        official_land_value = await repository.get_official_land_value(
            db,
            normative["normative_version_id"],
            context.zona_tributaria_codigo,
            context.material_via_codigo,
        )
        if official_land_value is None and not bool(merged_manual.get("usar_valor_unitario_manual")):
            raise HTTPException(
                status_code=422,
                detail=(
                    "No existe valor unitario oficial para la combinacion de zona tributaria "
                    f"'{context.zona_tributaria_codigo}' y via '{context.material_via_codigo}'."
                ),
            )
        valor_unitario_final, valor_unitario_fuente = rules.choose_value(
            merged_manual.get("valor_unitario_manual"),
            official_land_value,
            official_land_value,
            manual_enabled=bool(merged_manual.get("usar_valor_unitario_manual")),
        )

    if not is_horizontal and (merged_manual.get("pendiente_manual") is not None or context.pendiente_grados is not None):
        factor_pendiente = await repository.get_official_pendiente_factor(
            db,
            normative["normative_version_id"],
            float(context.pendiente_final) if isinstance(context.pendiente_final, (int, float)) else None,
        )
        pendiente_factor_fuente = "tabla_factores_pendiente_grados"
    elif not is_horizontal:
        factor_pendiente = rules.compute_slope_class_factor(context.pendiente_codigo)
        pendiente_factor_fuente = "clasificacion_gis_dn"

    factor_riesgo = 1.0
    factor_riesgo_fuente = "no_aplica_fiscal"
    coeficiente_comercial = 1.0
    coeficiente_fuente = "no_aplica_fiscal"
    factor_esquina = 1.0
    factor_avenida = 1.0
    factor_forma = 1.0
    factor_uso = 1.0
    ajuste_comercial = 1.0

    if avaluo_tipo == rules.APPRAISAL_COMERCIAL:
        es_esquina, es_avenida = _resolve_special_location_flags(
            merged_manual.get("clasificacion_especial")
        )
        factor_riesgo = await repository.get_official_risk_factor(
            db,
            normative["normative_version_id"],
            context.riesgo_codigo,
        ) or 1.0
        factor_riesgo_fuente = "oficial" if context.riesgo_codigo is not None else "automatico"
        coeficiente_comercial, coeficiente_fuente = rules.choose_value(
            merged_manual.get("coeficiente_manual"),
            await repository.get_terrain_coefficient(
                db,
                normative["normative_version_id"],
                "COMERCIAL",
                "DEFAULT",
            ),
            1.0,
            manual_enabled=bool(merged_manual.get("usar_coeficiente_manual")),
        )
        factor_esquina = await repository.get_terrain_coefficient(
            db,
            normative["normative_version_id"],
            "ESQUINA",
            "SI" if es_esquina else "NO",
        ) or 1.0
        factor_avenida = await repository.get_terrain_coefficient(
            db,
            normative["normative_version_id"],
            "AVENIDA",
            "SI" if es_avenida else "NO",
        ) or 1.0
        factor_forma = await repository.get_terrain_coefficient(
            db,
            normative["normative_version_id"],
            "FORMA",
            "IRREGULAR" if str(context.forma_lote or "").upper() not in {"REGULAR", ""} else "REGULAR",
        ) or 1.0
        factor_uso = await repository.get_terrain_coefficient(
            db,
            normative["normative_version_id"],
            "USO",
            str(context.uso_suelo or "RESIDENCIAL").upper(),
        ) or 1.0
        ajuste_comercial = float(merged_manual.get("ajuste_comercial") or 1.0)

    if is_horizontal:
        valor_terreno = 0.0
        valor_unitario_aplicado = 0.0
    else:
        valor_terreno, valor_unitario_aplicado = rules.calculate_land_value(
            superficie_calculo=context.superficie_calculo,
            valor_unitario=float(valor_unitario_final),
            puntaje_servicios=factor_servicios,
            factor_pendiente=factor_pendiente,
            avaluo_tipo=avaluo_tipo,
            factor_riesgo=factor_riesgo,
            coeficiente_comercial=float(coeficiente_comercial or 1.0),
            factor_esquina=factor_esquina,
            factor_avenida=factor_avenida,
            factor_forma=factor_forma,
            factor_uso=factor_uso,
            ajuste_comercial=ajuste_comercial,
        )

    building_blocks: list[dict] = []
    building_formula_blocks: list[dict] = []
    total_building_value = 0.0
    for block in payload.bloques:
        building_block, building_formula = await _appraise_building_block(
            db,
            block=block,
            normative_version_id=normative["normative_version_id"],
            gestion_anio=payload.gestion_anio,
            avaluo_tipo=avaluo_tipo,
            regimen_inmueble=regimen_inmueble,
            zona_tributaria_codigo=context.zona_tributaria_codigo,
        )
        total_building_value += float(building_block["valor_bloque"])
        building_blocks.append(building_block)
        building_formula_blocks.append(building_formula.model_dump(mode="json"))

    valor_construccion = round(total_building_value, 2)
    base_imponible = round(valor_terreno + valor_construccion, 2)
    impbi_bracket = await repository.get_impbi_bracket(db, normative["normative_version_id"], base_imponible)
    if not impbi_bracket:
        raise HTTPException(status_code=409, detail="No existe una escala IMPBI de referencia para la base imponible calculada.")
    alicuota = float(impbi_bracket["alicuota_excedente"])
    cuota_fija = float(impbi_bracket["cuota_fija"])
    limite_inferior = float(impbi_bracket["limite_inferior"])
    impuesto_estimado = rules.calculate_progressive_tax(
        base_imponible, cuota_fija, alicuota, limite_inferior
    )

    tabla_referencias = [
        _table_descriptor("tabla_tipologias_constructivas", normative, description="Base oficial de tipologias"),
        _table_descriptor("tabla_depreciacion_antiguedad", normative, description="Depreciacion oficial por antiguedad"),
        _table_descriptor("tabla_escala_impbi", normative, description="Escala IMPBI oficial verificada para 2023; vigencia posterior por confirmar"),
    ]
    if is_horizontal:
        tabla_referencias.append(
            _table_descriptor("tabla_factores_ubicacion_ph", normative, description="Factor de ubicacion de propiedad horizontal")
        )
    else:
        tabla_referencias.extend(
            [
                _table_descriptor("tabla_zonas_valor", normative, description="Valor unitario oficial de suelo"),
                _table_descriptor("tabla_factores_pendiente", normative, description="Factor oficial de pendiente"),
                _table_descriptor("tabla_factores_servicios", normative, description="Puntaje oficial de servicios"),
            ]
        )
    if avaluo_tipo == rules.APPRAISAL_COMERCIAL:
        tabla_referencias.extend(
            [
                _table_descriptor("tabla_matriz_calidad_material", normative, description="Matriz referencial de calidad, material, cubierta y estado"),
                _table_descriptor("tabla_factores_riesgo", normative, description="Factor de riesgo solo comercial"),
                _table_descriptor("tabla_coeficientes_terreno", normative, description="Coeficientes comerciales y de posicion"),
            ]
        )

    terreno_components = []
    terreno_symbolic = "No aplica: la propiedad horizontal incorpora la fraccion ideal de terreno mediante el factor de ubicacion"
    if not is_horizontal:
        terreno_components = [
            schemas.FormulaComponent(
                nombre="superficie_calculo",
                valor=context.superficie_calculo,
                fuente=context.superficie_fuente,
                tabla=f"predio.{context.superficie_fuente}",
            ),
            schemas.FormulaComponent(
                nombre="valor_unitario_final",
                valor=float(valor_unitario_final),
                fuente=valor_unitario_fuente,
                tabla="tabla_zonas_valor" if valor_unitario_fuente != "manual" else "input.manual.valor_unitario_manual",
            ),
            schemas.FormulaComponent(
                nombre="factor_servicios",
                valor=factor_servicios,
                fuente="oficial",
                tabla="tabla_factores_servicios",
                descripcion=(
                    ", ".join(servicios_oficiales)
                    if servicios_oficiales
                    else f"Minimo normativo {rules.MINIMUM_SERVICE_FACTOR:.2f} sin servicios confirmados"
                ),
            ),
            schemas.FormulaComponent(
                nombre="factor_pendiente",
                valor=factor_pendiente,
                fuente=pendiente_factor_fuente,
                tabla="tabla_factores_pendiente" if pendiente_factor_fuente != "clasificacion_gis_dn" else "staging_pendientes.DN",
            ),
        ]
        terreno_symbolic = "superficie_calculo x valor_unitario_final x factor_servicios x factor_pendiente"
    if avaluo_tipo == rules.APPRAISAL_COMERCIAL and not is_horizontal:
        terreno_symbolic += " x factor_riesgo x coeficiente_comercial x factor_esquina x factor_avenida x factor_forma x factor_uso x ajuste_comercial"
        terreno_components.extend(
            [
                schemas.FormulaComponent(
                    nombre="factor_riesgo",
                    valor=factor_riesgo,
                    fuente=factor_riesgo_fuente,
                    tabla="tabla_factores_riesgo",
                ),
                schemas.FormulaComponent(
                    nombre="coeficiente_comercial",
                    valor=float(coeficiente_comercial or 1.0),
                    fuente=coeficiente_fuente,
                    tabla="tabla_coeficientes_terreno",
                ),
                schemas.FormulaComponent(
                    nombre="factor_esquina",
                    valor=factor_esquina,
                    fuente="oficial",
                    tabla="tabla_coeficientes_terreno",
                ),
                schemas.FormulaComponent(
                    nombre="factor_avenida",
                    valor=factor_avenida,
                    fuente="oficial",
                    tabla="tabla_coeficientes_terreno",
                ),
                schemas.FormulaComponent(
                    nombre="factor_forma",
                    valor=factor_forma,
                    fuente="oficial",
                    tabla="tabla_coeficientes_terreno",
                ),
                schemas.FormulaComponent(
                    nombre="factor_uso",
                    valor=factor_uso,
                    fuente="oficial",
                    tabla="tabla_coeficientes_terreno",
                ),
                schemas.FormulaComponent(
                    nombre="ajuste_comercial",
                    valor=ajuste_comercial,
                    fuente="manual" if merged_manual.get("ajuste_comercial") is not None else "automatico",
                    tabla="input.manual.ajuste_comercial",
                ),
            ]
        )

    terreno_formula = _build_formula_detail(
        symbolic=terreno_symbolic,
        components=terreno_components,
        result=valor_terreno,
    )
    construccion_formula = {
        "simbolica": (
            "SUM(superficie_unidad x valor_tipologia_ph_m2 x factor_antiguedad x factor_ubicacion_ph)"
            if is_horizontal
            else (
            "SUM(superficie x valor_tipologia_ajustado x factor_antiguedad)"
            if avaluo_tipo == rules.APPRAISAL_COMERCIAL
            else "SUM(superficie x valor_tipologia_m2 x factor_antiguedad)"
            )
        ),
        "expandida": (
            " + ".join(block["formula"]["expandida"].rsplit(" = ", 1)[0] for block in building_blocks) + f" = {_fmt_number(valor_construccion, 2)}"
            if building_blocks
            else _fmt_number(valor_construccion, 2)
        ),
        "resultado": valor_construccion,
        "bloques": building_formula_blocks,
    }
    base_formula = schemas.FormulaDetail(
        simbolica="valor_terreno + valor_construccion",
        expandida=f"{_fmt_number(valor_terreno, 2)} + {_fmt_number(valor_construccion, 2)} = {_fmt_number(base_imponible, 2)}",
        resultado=base_imponible,
        componentes=[
            schemas.FormulaComponent(
                nombre="valor_terreno",
                valor=valor_terreno,
                fuente="calculado",
                tabla="appraisal_result",
            ),
            schemas.FormulaComponent(
                nombre="valor_construccion",
                valor=valor_construccion,
                fuente="calculado",
                tabla="appraisal_result",
            ),
        ],
    )
    impuesto_formula = schemas.FormulaDetail(
        simbolica="cuota_fija + (base_imponible - limite_inferior) x alicuota_excedente",
        expandida=(
            f"{_fmt_number(cuota_fija, 2)} + "
            f"({_fmt_number(base_imponible, 2)} - {_fmt_number(limite_inferior, 2)}) x "
            f"{_fmt_number(alicuota, 8)} = {_fmt_number(impuesto_estimado, 2)}"
        ),
        resultado=impuesto_estimado,
        componentes=[
            schemas.FormulaComponent(
                nombre="cuota_fija",
                valor=cuota_fija,
                fuente="oficial_referencia_2023",
                tabla="tabla_escala_impbi",
            ),
            schemas.FormulaComponent(
                nombre="base_imponible",
                valor=base_imponible,
                fuente="calculado",
                tabla="appraisal_result",
            ),
            schemas.FormulaComponent(
                nombre="limite_inferior",
                valor=limite_inferior,
                fuente="oficial_referencia_2023",
                tabla="tabla_escala_impbi",
            ),
            schemas.FormulaComponent(
                nombre="alicuota_excedente",
                valor=alicuota,
                fuente="oficial_referencia_2023",
                tabla="tabla_escala_impbi",
            ),
        ],
    )

    normative_metadata = _build_normative_metadata(normative)
    trace_payload = _json_safe_dict(
        {
            "gestion_anio": payload.gestion_anio,
            "avaluo_tipo": avaluo_tipo,
            "regimen_inmueble": regimen_inmueble,
            "normative_version": f"RA-14-{FISCAL_SOURCE_YEAR}-REFERENCIA/calculo-{payload.gestion_anio}",
            "normativa": normative_metadata.model_dump(mode="json"),
            "input_payload": payload.model_dump(mode="json"),
            "factores_aplicados": {
                "avaluo_tipo": avaluo_tipo,
                "regimen_inmueble": regimen_inmueble,
                "puntaje_servicios": service_score,
                "factor_servicios": factor_servicios,
                "factor_servicios_minimo_aplicado": factor_servicios_minimo_aplicado,
                "factor_servicios_fuente": (
                    "tabla_factores_servicios.MINIMO"
                    if factor_servicios_minimo_aplicado
                    else "tabla_factores_servicios"
                ),
                "servicios_oficiales": servicios_oficiales,
                "factor_pendiente": factor_pendiente if not is_horizontal else None,
                "factor_pendiente_fuente": pendiente_factor_fuente,
                "factor_riesgo": factor_riesgo if avaluo_tipo == rules.APPRAISAL_COMERCIAL else None,
                "coeficiente_comercial": float(coeficiente_comercial or 1.0) if avaluo_tipo == rules.APPRAISAL_COMERCIAL else None,
                "factor_esquina": factor_esquina if avaluo_tipo == rules.APPRAISAL_COMERCIAL else None,
                "factor_avenida": factor_avenida if avaluo_tipo == rules.APPRAISAL_COMERCIAL else None,
                "factor_forma": factor_forma if avaluo_tipo == rules.APPRAISAL_COMERCIAL else None,
                "factor_uso": factor_uso if avaluo_tipo == rules.APPRAISAL_COMERCIAL else None,
                "ajuste_comercial": ajuste_comercial if avaluo_tipo == rules.APPRAISAL_COMERCIAL else None,
                "factor_ubicacion_ph": building_blocks[0]["factor_ubicacion_ph"] if is_horizontal and building_blocks else None,
                "impbi_tramo": impbi_bracket["tramo_codigo"],
                "impbi_cuota_fija": cuota_fija,
                "impbi_limite_inferior": limite_inferior,
                "impbi_fuente_gestion_anio": int(impbi_bracket["fuente_gestion_anio"]),
                "impbi_fuente_documental": impbi_bracket["fuente_documental"],
                "impbi_vigente_confirmada": bool(impbi_bracket["vigente_confirmada"]),
                "alicuota_excedente": alicuota,
                "valor_unitario": official_land_value if not is_horizontal else None,
                "valor_unitario_final": float(valor_unitario_final) if not is_horizontal else None,
                "valor_unitario_fuente": valor_unitario_fuente,
                "valor_unitario_aplicado": valor_unitario_aplicado if not is_horizontal else None,
            },
            "contexto_espacial": context.model_dump(mode="json"),
            "tablas_utilizadas": tabla_referencias,
            "formulas_aplicadas": {
                "terreno": terreno_formula.model_dump(mode="json"),
                "construccion": construccion_formula,
                "base_imponible": base_formula.model_dump(mode="json"),
                "impuesto": impuesto_formula.model_dump(mode="json"),
            },
            "overrides_manuales": persisted_manual_payload,
            "geometries_used": {
                "predio_geometry": "predio.geom",
                "zona_homogenea": "staging_zonas_homogeneas.geometry",
                "pendiente": "predio_contexto_espacial",
                "riesgo": "predio_contexto_espacial",
            },
        }
    )

    appraisal_id = None
    if persist:
        try:
            if persisted_manual_payload.get("superficie_manual") is not None:
                await repository.save_surface_override(
                    db,
                    predio_id=str(payload.predio_id),
                    superficie_gis=context.superficie_gis,
                    superficie_legal=context.superficie_legal,
                    superficie_manual=float(persisted_manual_payload["superficie_manual"]),
                    motivo=override_reason or "Ajuste tecnico",
                    usuario_id=str(usuario_id),
                )
            if has_manual_data:
                await repository.save_manual_data(
                    db,
                    predio_id=str(payload.predio_id),
                    usuario_id=str(usuario_id),
                    payload={
                        **persisted_manual_payload,
                        "motivo": override_reason or "Ajuste tecnico",
                    },
                )

            gestion_id = await repository.get_gestion_id(db, payload.gestion_anio)
            appraisal_id = await repository.save_appraisal_case_and_result(
                db,
                predio_id=str(payload.predio_id),
                gestion_id=str(gestion_id) if gestion_id else None,
                normative_version_id=str(normative["normative_version_id"]),
                usuario_id=str(usuario_id),
                appraisal_mode=avaluo_tipo,
                regimen_inmueble=regimen_inmueble,
                superficie_gis=context.superficie_gis,
                superficie_legal=context.superficie_legal,
                superficie_manual=context.superficie_manual,
                superficie_calculo=context.superficie_calculo,
                superficie_override_reason=override_reason,
                observaciones=getattr(payload, "observaciones", None),
                valor_terreno=valor_terreno,
                valor_construccion=valor_construccion,
                base_imponible=base_imponible,
                impuesto_estimado=impuesto_estimado,
                alicuota=alicuota,
                bloques=building_blocks,
                trace_payload=trace_payload,
            )
            audit_entries = _build_audit_entries(
                context,
                persisted_manual_payload,
                motivo=override_reason,
            )
            if audit_entries:
                await repository.save_audit_entries(
                    db,
                    appraisal_id=str(appraisal_id),
                    predio_id=str(payload.predio_id),
                    usuario_id=str(usuario_id),
                    entries=audit_entries,
                )
            await db.commit()
            appraisal_cache.invalidate("coverage_stats_v2")
            appraisal_cache.invalidate_prefix("surface_differences")
            logger.info(
                "avaluo_v2_calculado predio=%s appraisal_id=%s modo=%s gestion=%s",
                payload.predio_id,
                appraisal_id,
                avaluo_tipo,
                payload.gestion_anio,
            )
        except Exception:
            await db.rollback()
            logger.exception(
                "avaluo_v2_error predio=%s modo=%s gestion=%s",
                payload.predio_id,
                avaluo_tipo,
                payload.gestion_anio,
            )
            raise

    export_urls = {}
    if appraisal_id:
        export_urls = {
            "pdf": f"/api/v2/avaluos/{appraisal_id}/export/pdf",
            "excel": f"/api/v2/avaluos/{appraisal_id}/export/excel",
            "csv": f"/api/v2/avaluos/{appraisal_id}/export/csv",
            "geojson": f"/api/v2/avaluos/{appraisal_id}/export/geojson",
        }

    return schemas.AppraisalResponseV2(
        appraisal_id=appraisal_id or payload.predio_id,
        predio_id=payload.predio_id,
        created_at=None,
        preview=not persist,
        avaluo_tipo=avaluo_tipo,
        regimen_inmueble=regimen_inmueble,
        valor_terreno=valor_terreno,
        valor_construccion=valor_construccion,
        base_imponible=base_imponible,
        impuesto_estimado=impuesto_estimado,
        normativa=normative_metadata,
        factores_aplicados=trace_payload["factores_aplicados"],
        contexto_espacial=trace_payload["contexto_espacial"],
        tablas_utilizadas=trace_payload["tablas_utilizadas"],
        formula_aplicada=trace_payload["formulas_aplicadas"],
        auditoria={
            "superficie_gis": context.superficie_gis,
            "superficie_legal": context.superficie_legal,
            "superficie_manual": context.superficie_manual,
            "superficie_calculo": context.superficie_calculo,
            "superficie_fuente": context.superficie_fuente,
            "usuario": payload.usuario,
            "normative_version": trace_payload["normative_version"],
            "manual_temporal": bool(persisted_manual_payload.get("es_temporal", False)),
            "motivo_override": override_reason,
        },
        bloques=building_blocks,
        export_urls=export_urls,
    )


async def preview_appraisal(db: AsyncSession, payload: schemas.AppraisalPreviewRequest) -> schemas.AppraisalResponseV2:
    return await _assemble_appraisal(db, payload=payload, persist=False)


async def calculate_appraisal(db: AsyncSession, payload: schemas.AppraisalRequestV2) -> schemas.AppraisalResponseV2:
    return await _assemble_appraisal(db, payload=payload, persist=payload.persistir_override)


async def submit_public_beta_consultation(
    db: AsyncSession,
    payload: schemas.PublicBetaSubmissionRequest,
) -> schemas.PublicBetaSubmissionResponse:
    if not payload.acepta_registro_consulta:
        raise HTTPException(
            status_code=422,
            detail="Debes autorizar el registro de la consulta para participar en la prueba beta.",
        )

    has_contact = any(
        value and value.strip()
        for value in (payload.nombre_contacto, payload.correo_contacto, payload.telefono_contacto)
    )
    if has_contact and not payload.acepta_contacto:
        raise HTTPException(
            status_code=422,
            detail="Debes autorizar el contacto antes de enviar nombre, correo o telefono.",
        )
    if payload.acepta_contacto and not (payload.correo_contacto or payload.telefono_contacto):
        raise HTTPException(
            status_code=422,
            detail="Si deseas seguimiento, indica un correo o telefono de contacto.",
        )

    calculation_payload = payload.calculo.model_copy(update={"usuario": PUBLIC_APPRAISAL_USER})
    result = await preview_appraisal(db, calculation_payload)
    try:
        saved = await repository.save_public_beta_submission(
            db,
            predio_id=str(calculation_payload.predio_id),
            gestion_anio=calculation_payload.gestion_anio,
            avaluo_tipo=calculation_payload.avaluo_tipo,
            regimen_inmueble=calculation_payload.regimen_inmueble,
            base_imponible=result.base_imponible,
            impuesto_estimado=result.impuesto_estimado,
            calculation_input=calculation_payload.model_dump(mode="json"),
            calculation_result=result.model_dump(mode="json"),
            utilidad_resultado=payload.utilidad_resultado,
            comentario=payload.comentario.strip() if payload.comentario else None,
            consentimiento_version=payload.consentimiento_version,
            nombre_contacto=payload.nombre_contacto.strip() if payload.nombre_contacto else None,
            correo_contacto=payload.correo_contacto.strip() if payload.correo_contacto else None,
            telefono_contacto=payload.telefono_contacto.strip() if payload.telefono_contacto else None,
            acepta_contacto=payload.acepta_contacto,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        logger.exception("consulta_beta_publica_error predio=%s", calculation_payload.predio_id)
        raise

    return schemas.PublicBetaSubmissionResponse(
        **saved,
        message=(
            "Consulta y contacto registrados para la prueba beta."
            if saved["contacto_registrado"]
            else "Consulta registrada para la prueba beta sin datos de contacto."
        ),
    )


async def get_public_beta_summary(db: AsyncSession) -> schemas.PublicBetaSummaryResponse:
    return schemas.PublicBetaSummaryResponse(**(await repository.fetch_public_beta_summary(db)))


async def list_public_beta_consultations(
    db: AsyncSession,
    limit: int = 20,
) -> schemas.PublicBetaAdminListResponse:
    return schemas.PublicBetaAdminListResponse(
        **(await repository.fetch_public_beta_submissions(db, limit=limit))
    )


async def export_public_beta_consultations_csv(db: AsyncSession) -> tuple[bytes, str, str]:
    data = await repository.fetch_public_beta_submissions(db, limit=None)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "beta_submission_id",
            "fecha_consulta",
            "codigo_catastral",
            "predio_id",
            "gestion_anio",
            "avaluo_tipo",
            "regimen_inmueble",
            "base_imponible",
            "impuesto_estimado",
            "utilidad_resultado",
            "comentario",
            "contacto_autorizado",
            "nombre_contacto",
            "correo_contacto",
            "telefono_contacto",
        ]
    )
    for item in data["items"]:
        writer.writerow(
            [
                item["beta_submission_id"],
                item["created_at"],
                item.get("codigo_catastral"),
                item["predio_id"],
                item["gestion_anio"],
                item["avaluo_tipo"],
                item["regimen_inmueble"],
                item["base_imponible"],
                item["impuesto_estimado"],
                item.get("utilidad_resultado"),
                item.get("comentario"),
                item.get("contacto_autorizado"),
                item.get("nombre_contacto"),
                item.get("correo_contacto"),
                item.get("telefono_contacto"),
            ]
        )
    return (
        output.getvalue().encode("utf-8-sig"),
        "text/csv; charset=utf-8",
        "consultas_beta_publicas.csv",
    )


async def delete_public_beta_contact(db: AsyncSession, beta_submission_id: str) -> dict:
    try:
        removed = await repository.delete_public_beta_contact(db, beta_submission_id)
        if not removed:
            raise HTTPException(status_code=404, detail="La consulta no tiene contacto registrado.")
        await db.commit()
    except HTTPException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        logger.exception("consulta_beta_eliminar_contacto_error id=%s", beta_submission_id)
        raise
    return {"message": "Datos de contacto eliminados; la consulta estadistica se conserva."}


async def get_appraisal(db: AsyncSession, appraisal_id: str) -> schemas.AppraisalResponseV2:
    row = await repository.fetch_appraisal_result(db, appraisal_id)
    if not row:
        raise HTTPException(status_code=404, detail="No existe el avaluo solicitado.")

    blocks = await repository.fetch_appraisal_blocks(db, appraisal_id)
    normative_metadata = schemas.NormativeMetadata(
        gestion_anio=int(row["gestion_anio"]),
        nombre=row["normative_nombre"],
        version_codigo=row["version_codigo"],
        fuente_gestion_anio=FISCAL_SOURCE_YEAR,
        vigente_para_gestion=int(row["gestion_anio"]),
        alcance=FISCAL_SOURCE_STATUS,
        resolucion_municipal=row.get("resolucion_municipal"),
        detalle_normativo=row.get("detalle_normativo"),
    )

    return schemas.AppraisalResponseV2(
        appraisal_id=row["appraisal_id"],
        predio_id=row["predio_id"],
        created_at=row.get("created_at"),
        preview=False,
        avaluo_tipo=row.get("appraisal_mode") or rules.APPRAISAL_FISCAL,
        regimen_inmueble=row.get("regimen_inmueble") or "VIVIENDA_FAMILIAR",
        valor_terreno=float(row["valor_terreno"]),
        valor_construccion=float(row["valor_construccion"]),
        base_imponible=float(row["base_imponible"]),
        impuesto_estimado=float(row["impuesto_estimado"]),
        normativa=normative_metadata,
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
            "superficie_fuente": row["overrides_manuales"].get("superficie_fuente") if isinstance(row["overrides_manuales"], dict) else None,
            "normative_version": row.get("normative_version"),
            "usuario": row.get("generated_by"),
        },
        bloques=blocks,
        export_urls={
            "pdf": f"/api/v2/avaluos/{appraisal_id}/export/pdf",
            "excel": f"/api/v2/avaluos/{appraisal_id}/export/excel",
            "csv": f"/api/v2/avaluos/{appraisal_id}/export/csv",
            "geojson": f"/api/v2/avaluos/{appraisal_id}/export/geojson",
        },
    )


async def get_appraisal_trace(db: AsyncSession, appraisal_id: str) -> schemas.AppraisalTraceResponse:
    trace = await repository.fetch_appraisal_trace(db, appraisal_id)
    if not trace:
        raise HTTPException(status_code=404, detail="No existe traza para el avaluo solicitado.")
    return schemas.AppraisalTraceResponse(**trace)


async def get_master_table(db: AsyncSession, table_name: str, gestion_anio: int) -> list[schemas.MasterTableRow]:
    try:
        rows = await repository.fetch_master_table(db, table_name, gestion_anio)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
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
            avaluo_tipo=row.get("appraisal_mode"),
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
        raise HTTPException(status_code=404, detail=f"No existe normativa activa para la gestion {payload.gestion_anio}.")

    building_blocks = []
    total_building_value = 0.0
    for block in payload.bloques:
        building_block, _ = await _appraise_building_block(
            db,
            block=block,
            normative_version_id=normative["normative_version_id"],
            gestion_anio=payload.gestion_anio,
            avaluo_tipo=payload.avaluo_tipo,
            regimen_inmueble=payload.regimen_inmueble,
            zona_tributaria_codigo=payload.zona_tributaria_codigo,
        )
        total_building_value += float(building_block["valor_bloque"])
        building_blocks.append(building_block)

    return schemas.ConstructionValuationResponse(
        gestion_anio=payload.gestion_anio,
        valor_construccion=round(total_building_value, 2),
        bloques=building_blocks,
        factores_aplicados={"normative_version": normative["version_codigo"]},
    )


async def get_audit_entries(db: AsyncSession, predio_id: str, limit: int = 100) -> list[schemas.AuditEntryResponse]:
    rows = await repository.fetch_audit_entries(db, predio_id, limit)
    return [schemas.AuditEntryResponse(**row) for row in rows]


def _to_csv_bytes(detail: schemas.AppraisalResponseV2) -> bytes:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["campo", "valor"])
    writer.writerow(["appraisal_id", detail.appraisal_id])
    writer.writerow(["predio_id", detail.predio_id])
    writer.writerow(["avaluo_tipo", detail.avaluo_tipo])
    writer.writerow(["normativa.version_codigo", detail.normativa.version_codigo])
    writer.writerow(["normativa.resolucion_municipal", detail.normativa.resolucion_municipal])
    writer.writerow(["valor_terreno", detail.valor_terreno])
    writer.writerow(["valor_construccion", detail.valor_construccion])
    writer.writerow(["base_imponible", detail.base_imponible])
    writer.writerow(["impuesto_estimado", detail.impuesto_estimado])
    for key, value in detail.auditoria.items():
        writer.writerow([f"auditoria.{key}", value])
    for key, value in detail.factores_aplicados.items():
        writer.writerow([f"factor.{key}", value])
    for key, value in detail.contexto_espacial.items():
        writer.writerow([f"contexto.{key}", value])
    return output.getvalue().encode("utf-8-sig")


def _to_geojson_bytes(detail: schemas.AppraisalResponseV2, geometry_geojson: str | None) -> bytes:
    geometry = json.loads(geometry_geojson) if geometry_geojson else None
    geojson = {
        "type": "FeatureCollection",
        "name": "avaluo_predial",
        "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
        "features": [
            {
                "type": "Feature",
                "geometry": geometry,
                "properties": {
                    "appraisal_id": str(detail.appraisal_id),
                    "predio_id": str(detail.predio_id),
                    "avaluo_tipo": detail.avaluo_tipo,
                    "normativa_version": detail.normativa.version_codigo,
                    "resolucion_municipal": detail.normativa.resolucion_municipal,
                    "valor_terreno": detail.valor_terreno,
                    "valor_construccion": detail.valor_construccion,
                    "base_imponible": detail.base_imponible,
                    "impuesto_estimado": detail.impuesto_estimado,
                    "contexto": detail.contexto_espacial,
                    "auditoria": detail.auditoria,
                },
            }
        ],
    }
    return json.dumps(geojson, ensure_ascii=False, indent=2).encode("utf-8")


def _rows_to_excel_xml_bytes(rows: list[tuple[str, Any]]) -> bytes:
    xml_rows = []
    for left, right in rows:
        xml_rows.append(
            f'<Row><Cell><Data ss:Type="String">{left}</Data></Cell><Cell><Data ss:Type="String">{right}</Data></Cell></Row>'
        )
    xml = f"""<?xml version="1.0"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:o="urn:schemas-microsoft-com:office:office"
 xmlns:x="urn:schemas-microsoft-com:office:excel"
 xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
 <Worksheet ss:Name="Avaluo">
  <Table>
   {''.join(xml_rows)}
  </Table>
 </Worksheet>
</Workbook>"""
    return xml.encode("utf-8")


def _to_excel_xml_bytes(detail: schemas.AppraisalResponseV2) -> bytes:
    rows = [
        ("Campo", "Valor"),
        ("appraisal_id", str(detail.appraisal_id)),
        ("predio_id", str(detail.predio_id)),
        ("avaluo_tipo", detail.avaluo_tipo),
        ("normativa.version_codigo", detail.normativa.version_codigo),
        ("normativa.resolucion_municipal", detail.normativa.resolucion_municipal),
        ("valor_terreno", detail.valor_terreno),
        ("valor_construccion", detail.valor_construccion),
        ("base_imponible", detail.base_imponible),
        ("impuesto_estimado", detail.impuesto_estimado),
    ]
    for key, value in detail.auditoria.items():
        rows.append((f"auditoria.{key}", value))
    for key, value in detail.factores_aplicados.items():
        rows.append((f"factor.{key}", value))
    return _rows_to_excel_xml_bytes(rows)


def _escape_pdf_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _to_pdf_bytes(detail: schemas.AppraisalResponseV2) -> bytes:
    lines = [
        "Reporte Tecnico de Avaluo",
        f"Avaluo: {detail.appraisal_id}",
        f"Predio: {detail.predio_id}",
        f"Modo: {detail.avaluo_tipo}",
        f"Normativa: {detail.normativa.version_codigo}",
        f"Resolucion: {detail.normativa.resolucion_municipal}",
        f"Valor terreno: {detail.valor_terreno}",
        f"Valor construccion: {detail.valor_construccion}",
        f"Base imponible: {detail.base_imponible}",
        f"Impuesto estimado: {detail.impuesto_estimado}",
        f"Zona tributaria: {detail.contexto_espacial.get('zona_tributaria_codigo')}",
        f"Zona homogenea: {detail.contexto_espacial.get('zona_homogenea_codigo')}",
        f"Riesgo: {detail.contexto_espacial.get('riesgo_final')}",
        f"Pendiente: {detail.contexto_espacial.get('pendiente_final')}",
        f"Superficie GIS: {detail.auditoria.get('superficie_gis')}",
        f"Superficie legal: {detail.auditoria.get('superficie_legal')}",
        f"Superficie calculo: {detail.auditoria.get('superficie_calculo')}",
    ]
    content_lines = ["BT /F1 12 Tf 50 800 Td"]
    for line in lines:
        content_lines.append(f"0 -18 Td ({_escape_pdf_text(str(line))}) Tj")
    content_lines.append("ET")
    content = "\n".join(content_lines).encode("latin-1", errors="replace")
    objects = []
    objects.append(b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj")
    objects.append(b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj")
    objects.append(b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj")
    objects.append(f"4 0 obj << /Length {len(content)} >> stream\n".encode() + content + b"\nendstream endobj")
    objects.append(b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj")
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(pdf))
        pdf.extend(obj)
        pdf.extend(b"\n")
    xref_start = len(pdf)
    pdf.extend(f"xref\n0 {len(offsets)}\n".encode())
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode())
    pdf.extend(f"trailer << /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF".encode())
    return bytes(pdf)


async def export_appraisal(db: AsyncSession, appraisal_id: str, export_format: str) -> tuple[bytes, str, str]:
    detail = await get_appraisal(db, appraisal_id)
    if export_format == "csv":
        return _to_csv_bytes(detail), "text/csv; charset=utf-8", f"avaluo_{appraisal_id}.csv"
    if export_format == "geojson":
        geometry_row = await repository.fetch_predio_geometry(db, str(detail.predio_id))
        return (
            _to_geojson_bytes(detail, geometry_row.get("geometry_geojson") if geometry_row else None),
            "application/geo+json",
            f"avaluo_{appraisal_id}.geojson",
        )
    if export_format == "excel":
        return _to_excel_xml_bytes(detail), "application/vnd.ms-excel", f"avaluo_{appraisal_id}.xls"
    if export_format == "pdf":
        return _to_pdf_bytes(detail), "application/pdf", f"avaluo_{appraisal_id}.pdf"
    raise HTTPException(status_code=400, detail="Formato de exportacion no soportado.")


async def get_coverage_stats(db: AsyncSession) -> dict:
    cache_key = "coverage_stats_v2"
    cached = appraisal_cache.get(cache_key)
    if cached is not None:
        return cached
    result = await repository.fetch_coverage_stats(db)
    return appraisal_cache.set(cache_key, result, ttl_seconds=120)


async def get_gis_layer_bbox(
    db: AsyncSession,
    *,
    capa: str,
    xmin: float,
    ymin: float,
    xmax: float,
    ymax: float,
    limit: int,
):
    input_srid = infer_bbox_srid(xmin, ymin, xmax, ymax)
    output_srid = input_srid
    cache_key = f"gis_layer:{capa}:{input_srid}:{xmin:.3f}:{ymin:.3f}:{xmax:.3f}:{ymax:.3f}:{limit}"
    cached = appraisal_cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        result = await repository.fetch_gis_layer_bbox(
            db,
            capa=capa,
            xmin=xmin,
            ymin=ymin,
            xmax=xmax,
            ymax=ymax,
            limit=limit,
            input_srid=input_srid,
            output_srid=output_srid,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return appraisal_cache.set(cache_key, result, ttl_seconds=60)


async def refresh_surface_differences(db: AsyncSession) -> dict:
    await repository.refresh_surface_difference_view(db)
    appraisal_cache.invalidate_prefix("surface_differences")
    appraisal_cache.invalidate_prefix("gis_layer:diferencias_superficie:")
    return {"status": "ok", "message": "Vista materializada actualizada."}


async def list_surface_differences(
    db: AsyncSession,
    *,
    status: str | None,
    search: str | None,
    limit: int,
    offset: int,
) -> schemas.SurfaceDifferenceListResponse:
    cache_key = f"surface_differences:list:{status or 'ALL'}:{search or ''}:{limit}:{offset}"
    cached = appraisal_cache.get(cache_key)
    if cached is not None:
        return schemas.SurfaceDifferenceListResponse(**cached)

    resumen = await repository.fetch_surface_difference_summary(db)
    total, rows = await repository.fetch_surface_differences(
        db,
        status=status,
        search=search,
        limit=limit,
        offset=offset,
    )
    payload = {
        "total": total,
        "items": [
            schemas.SurfaceDifferenceItem(
                predio_id=row["predio_id"],
                codigo_catastral=row.get("codigo_catastral"),
                superficie_gis=float(row["superficie_gis"]),
                superficie_legal=float(row["superficie_legal"]) if row.get("superficie_legal") is not None else None,
                diferencia=float(row["diferencia"]),
                porcentaje_diferencia=float(row["porcentaje_diferencia"]) if row.get("porcentaje_diferencia") is not None else None,
                clasificacion=row["clasificacion"],
                color=row["color"],
            ).model_dump(mode="json")
            for row in rows
        ],
        "resumen": resumen,
    }
    appraisal_cache.set(cache_key, payload, ttl_seconds=60)
    return schemas.SurfaceDifferenceListResponse(**payload)


async def export_surface_differences(
    db: AsyncSession,
    *,
    export_format: str,
    status: str | None,
    search: str | None,
) -> tuple[bytes, str, str]:
    _, rows = await repository.fetch_surface_differences(
        db,
        status=status,
        search=search,
        limit=50000,
        offset=0,
    )
    if export_format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "predio_id",
                "codigo_catastral",
                "superficie_gis",
                "superficie_legal",
                "diferencia",
                "porcentaje_diferencia",
                "clasificacion",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row["predio_id"],
                    row.get("codigo_catastral"),
                    row["superficie_gis"],
                    row.get("superficie_legal"),
                    row["diferencia"],
                    row.get("porcentaje_diferencia"),
                    row["clasificacion"],
                ]
            )
        return (
            output.getvalue().encode("utf-8-sig"),
            "text/csv; charset=utf-8",
            "diferencias_superficie.csv",
        )

    if export_format == "excel":
        rows_data = [("predio_id", "codigo_catastral | superficie_gis | superficie_legal | diferencia | porcentaje_diferencia | clasificacion")]
        for row in rows:
            rows_data.append(
                (
                    str(row["predio_id"]),
                    " | ".join(
                        [
                            str(row.get("codigo_catastral") or ""),
                            str(row["superficie_gis"]),
                            str(row.get("superficie_legal") or ""),
                            str(row["diferencia"]),
                            str(row.get("porcentaje_diferencia") or ""),
                            str(row["clasificacion"]),
                        ]
                    ),
                )
            )
        return (
            _rows_to_excel_xml_bytes(rows_data),
            "application/vnd.ms-excel",
            "diferencias_superficie.xls",
        )

    if export_format == "geojson":
        bbox_world = (-180.0, -90.0, 180.0, 90.0)
        geojson = await repository.fetch_gis_layer_bbox(
            db,
            capa="diferencias_superficie",
            xmin=bbox_world[0],
            ymin=bbox_world[1],
            xmax=bbox_world[2],
            ymax=bbox_world[3],
            limit=50000,
            input_srid=4326,
            output_srid=4326,
        )
        return (
            json.dumps(geojson, ensure_ascii=False, indent=2).encode("utf-8"),
            "application/geo+json",
            "diferencias_superficie.geojson",
        )

    raise HTTPException(status_code=400, detail="Formato de exportacion no soportado.")


def get_methodology() -> dict:
    return {
        "version": "ra-14-2023-referencia-v3",
        "normativa_fuente": {
            "nombre": FISCAL_SOURCE_NAME,
            "gestion_tributaria": FISCAL_SOURCE_YEAR,
            "estado": "REFERENCIA_OFICIAL_VERIFICADA",
            "nota": FISCAL_SOURCE_STATUS,
        },
        "motores": {
            "FISCAL": {
                "descripcion": "Calculo catastral con fuente municipal verificada para 2023; su vigencia posterior debe confirmarse.",
                "usa": [
                    "superficie_calculo",
                    "valor_unitario_oficial",
                    "factor_servicios",
                    "factor_pendiente",
                    "construcciones",
                    "depreciacion_oficial",
                ],
                "no_usa": [
                    "factor_estado_conservacion",
                    "factor_material_estructural",
                    "factor_cubierta",
                    "factor_remodelacion",
                    "factor_riesgo",
                    "coeficiente_comercial",
                    "factor_esquina",
                    "factor_avenida",
                    "factor_forma",
                    "ajuste_comercial",
                ],
                "formula_terreno": "superficie_calculo x valor_unitario_final x factor_servicios x factor_pendiente",
                "formula_construccion": "superficie_construida x tipologia x antiguedad",
                "formula_propiedad_horizontal": "superficie_unidad x tipologia_ph x antiguedad x factor_ubicacion_ph",
            },
            "COMERCIAL": {
                "descripcion": "Estimacion tecnica referencial no oficial con factores adicionales de mercado y localizacion.",
                "usa": [
                    "superficie_calculo",
                    "valor_unitario_oficial",
                    "factor_servicios",
                    "factor_pendiente",
                    "factor_riesgo",
                    "coeficiente_comercial",
                    "factor_esquina",
                    "factor_avenida",
                    "factor_forma",
                    "factor_uso",
                    "ajuste_comercial",
                ],
                "formula_terreno": (
                    "superficie_calculo x valor_unitario_final x factor_servicios x factor_pendiente "
                    "x factor_riesgo x coeficiente_comercial x factor_esquina x factor_avenida "
                    "x factor_forma x factor_uso x ajuste_comercial"
                ),
                "formula_construccion": "superficie_construida x tipologia_ajustada x antiguedad",
            },
        },
        "fallbacks": {
            "superficie": "superficie_manual ?? superficie_legal ?? superficie_gis",
            "pendiente": "pendiente_manual ?? pendiente_gis",
            "riesgo": "riesgo_manual ?? riesgo_overlay",
            "valor_unitario": "valor_manual ?? valor_zona_oficial ?? automatico",
        },
        "servicios_oficiales": list(sorted(rules.OFFICIAL_SERVICES)),
        "servicios_minimo": rules.MINIMUM_SERVICE_FACTOR,
        "regimenes_inmueble": {
            "VIVIENDA_FAMILIAR": "Valora suelo y construccion de forma separada.",
            "PROPIEDAD_HORIZONTAL": "Valora la unidad con factor de ubicacion; el suelo no se suma por separado.",
        },
        "impbi": {
            "formula": "cuota_fija + (base_imponible - limite_inferior) x alicuota_excedente",
            "fuente_gestion_anio": 2023,
            "vigencia_confirmada_gestion_calculo": False,
        },
        "tablas_maestras": [
            "tabla_zonas_valor",
            "tabla_factores_pendiente",
            "tabla_factores_servicios",
            "tabla_tipologias_constructivas",
            "tabla_depreciacion_antiguedad",
            "tabla_matriz_calidad_material",
            "tabla_factores_ubicacion_ph",
            "tabla_escala_impbi",
            "tabla_factores_riesgo",
            "tabla_coeficientes_terreno",
        ],
    }

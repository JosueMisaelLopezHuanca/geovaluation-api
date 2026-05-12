"""
=====================================================
CLI DE IMPORTACIÓN DE SHAPEFILES — AVALIX v2
=====================================================
Uso (desde la raíz del proyecto):
    python -m scripts.importar explorar         → Ver columnas de los .shp
    python -m scripts.importar staging          → Importar .shp a tablas staging (con reparación)
    python -m scripts.importar reparar          → Reparar geometrías en PostgreSQL
    python -m scripts.importar transferir       → Staging → tablas definitivas
    python -m scripts.importar todo             → Ejecutar todo el flujo
    python -m scripts.importar diagnostico      → Ver estado de la BD
    python -m scripts.importar explorar-staging → Ver columnas en staging
=====================================================
"""

import csv
import typer
import geopandas as gpd
import os
import sys

from pathlib import Path
from shapely.validation import make_valid
from shapely.geometry import MultiPolygon
from rich.console import Console
from rich.table import Table
from sqlalchemy import text

# Agregar raíz del proyecto al path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.sync_database import sync_engine, test_connection

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

console = Console()
app = typer.Typer(help="Importador de Shapefiles → BD Avalix Catastral")

# =====================================================
# CONFIGURACIÓN DE SHAPEFILES
# =====================================================

SHAPEFILES_DIR = Path(__file__).resolve().parent.parent.parent / "shapefiles"
SRID = 32719  # UTM 19S - Bolivia

CAPAS = {
    "predios": {
        "archivo": "Predio_lpz.shp",
        "tabla_staging": "staging_predios",
    },
    "manzanas": {
        "archivo": "Manzanos_lpz.shp",
        "tabla_staging": "staging_manzanas",
    },
    "pendientes": {
        "archivo": "PendienteLApaz.shp",
        "tabla_staging": "staging_pendientes",
    },
    "riesgos": {
        "archivo": "Riesgo_Lpz.shp",
        "tabla_staging": "staging_riesgos",
    },
    "zonas_homogeneas": {
        "archivo": "zonas homogeneas La Paz.shp",
        "tabla_staging": "staging_zonas_homogeneas",
    },
}

# Jerarquía territorial mínima para datos de prueba La Paz
JERARQUIA_LA_PAZ = {
    "departamento": {"nombre": "La Paz",               "codigo_departamento": "02", "codigo_interno": "02"},
    "provincia":    {"nombre": "Pedro Domingo Murillo", "codigo_provincia": "01",    "codigo_interno": "0201"},
    "municipio":    {"nombre": "La Paz",                "codigo_municipio": "01",    "codigo_interno": "020101"},
    "distrito":     {"nombre": "Distrito Centro",       "codigo_distrito": "01",     "codigo_interno": "02010101"},
    "zona":         {"nombre": "Zona Central",          "codigo_zona": "01",         "codigo_interno": "0201010101", "tipo": "URBANO"},
}


def build_contexto_espacial_sql(modo: str) -> str:
    if modo == "exacto":
        return """
            WITH batch_predios AS (
                SELECT
                    p.id_predio,
                    p.superficie_mensura,
                    p.geom
                FROM predio p
                WHERE p.geom IS NOT NULL
                ORDER BY p.id_predio
                LIMIT :limit OFFSET :offset
            ),
            pendiente_intersecciones AS (
                SELECT
                    p.id_predio,
                    sp."DN"::INT AS pendiente_codigo,
                    ST_Area(ST_Intersection(p.geom, sp.geometry)) AS area_interseccion
                FROM batch_predios p
                JOIN staging_pendientes sp
                    ON p.geom && sp.geometry
                   AND ST_Intersects(p.geom, sp.geometry)
            ),
            pendiente_ranked AS (
                SELECT
                    p.id_predio,
                    p.pendiente_codigo,
                    p.area_interseccion,
                    ROW_NUMBER() OVER (
                        PARTITION BY p.id_predio
                        ORDER BY p.area_interseccion DESC, p.pendiente_codigo DESC
                    ) AS rn
                FROM pendiente_intersecciones p
                WHERE p.area_interseccion > 0
            ),
            riesgo_intersecciones AS (
                SELECT
                    p.id_predio,
                    sr."GRIDCODE"::INT AS riesgo_codigo,
                    sr."GRADO"::VARCHAR(50) AS riesgo_grado,
                    ST_Area(ST_Intersection(p.geom, sr.geometry)) AS area_interseccion
                FROM batch_predios p
                JOIN staging_riesgos sr
                    ON p.geom && sr.geometry
                   AND ST_Intersects(p.geom, sr.geometry)
            ),
            riesgo_ranked AS (
                SELECT
                    r.id_predio,
                    r.riesgo_codigo,
                    r.riesgo_grado,
                    r.area_interseccion,
                    ROW_NUMBER() OVER (
                        PARTITION BY r.id_predio
                        ORDER BY r.area_interseccion DESC, r.riesgo_codigo DESC
                    ) AS rn
                FROM riesgo_intersecciones r
                WHERE r.area_interseccion > 0
            ),
            resumen AS (
                SELECT
                    p.id_predio,
                    pen.pendiente_codigo,
                    ROUND(pen.area_interseccion::numeric, 2) AS pendiente_area_m2,
                    ROUND(
                        CASE
                            WHEN p.superficie_mensura > 0
                            THEN ((pen.area_interseccion / p.superficie_mensura) * 100)::numeric
                            ELSE NULL
                        END,
                        4
                    ) AS pendiente_cobertura_pct,
                    rie.riesgo_codigo,
                    rie.riesgo_grado,
                    ROUND(rie.area_interseccion::numeric, 2) AS riesgo_area_m2,
                    ROUND(
                        CASE
                            WHEN p.superficie_mensura > 0
                            THEN ((rie.area_interseccion / p.superficie_mensura) * 100)::numeric
                            ELSE NULL
                        END,
                        4
                    ) AS riesgo_cobertura_pct
                FROM batch_predios p
                LEFT JOIN pendiente_ranked pen
                    ON pen.id_predio = p.id_predio
                   AND pen.rn = 1
                LEFT JOIN riesgo_ranked rie
                    ON rie.id_predio = p.id_predio
                   AND rie.rn = 1
            )
            INSERT INTO predio_contexto_espacial (
                id_predio,
                pendiente_codigo,
                pendiente_area_m2,
                pendiente_cobertura_pct,
                riesgo_codigo,
                riesgo_grado,
                riesgo_area_m2,
                riesgo_cobertura_pct,
                fecha_calculo
            )
            SELECT
                id_predio,
                pendiente_codigo,
                pendiente_area_m2,
                pendiente_cobertura_pct,
                riesgo_codigo,
                riesgo_grado,
                riesgo_area_m2,
                riesgo_cobertura_pct,
                CURRENT_TIMESTAMP
            FROM resumen
            ON CONFLICT (id_predio) DO UPDATE
            SET
                pendiente_codigo = EXCLUDED.pendiente_codigo,
                pendiente_area_m2 = EXCLUDED.pendiente_area_m2,
                pendiente_cobertura_pct = EXCLUDED.pendiente_cobertura_pct,
                riesgo_codigo = EXCLUDED.riesgo_codigo,
                riesgo_grado = EXCLUDED.riesgo_grado,
                riesgo_area_m2 = EXCLUDED.riesgo_area_m2,
                riesgo_cobertura_pct = EXCLUDED.riesgo_cobertura_pct,
                fecha_calculo = CURRENT_TIMESTAMP
        """

    return """
        WITH batch_predios AS (
            SELECT
                p.id_predio,
                p.superficie_mensura,
                ST_PointOnSurface(p.geom) AS punto_representativo
            FROM predio p
            WHERE p.geom IS NOT NULL
            ORDER BY p.id_predio
            LIMIT :limit OFFSET :offset
        ),
        pendiente_match AS (
            SELECT
                p.id_predio,
                sp."DN"::INT AS pendiente_codigo,
                ROW_NUMBER() OVER (
                    PARTITION BY p.id_predio
                    ORDER BY sp."DN" DESC
                ) AS rn
            FROM batch_predios p
            LEFT JOIN staging_pendientes sp
                ON sp.geometry && p.punto_representativo
               AND ST_Intersects(sp.geometry, p.punto_representativo)
        ),
        riesgo_match AS (
            SELECT
                p.id_predio,
                sr."GRIDCODE"::INT AS riesgo_codigo,
                sr."GRADO"::VARCHAR(50) AS riesgo_grado,
                ROW_NUMBER() OVER (
                    PARTITION BY p.id_predio
                    ORDER BY sr."GRIDCODE" DESC
                ) AS rn
            FROM batch_predios p
            LEFT JOIN staging_riesgos sr
                ON sr.geometry && p.punto_representativo
               AND ST_Intersects(sr.geometry, p.punto_representativo)
        ),
        resumen AS (
            SELECT
                p.id_predio,
                pen.pendiente_codigo,
                CASE
                    WHEN pen.pendiente_codigo IS NOT NULL
                    THEN ROUND(p.superficie_mensura::numeric, 2)
                    ELSE NULL
                END AS pendiente_area_m2,
                CASE
                    WHEN pen.pendiente_codigo IS NOT NULL
                    THEN 100.0
                    ELSE NULL
                END AS pendiente_cobertura_pct,
                rie.riesgo_codigo,
                rie.riesgo_grado,
                CASE
                    WHEN rie.riesgo_codigo IS NOT NULL
                    THEN ROUND(p.superficie_mensura::numeric, 2)
                    ELSE NULL
                END AS riesgo_area_m2,
                CASE
                    WHEN rie.riesgo_codigo IS NOT NULL
                    THEN 100.0
                    ELSE NULL
                END AS riesgo_cobertura_pct
            FROM batch_predios p
            LEFT JOIN pendiente_match pen
                ON pen.id_predio = p.id_predio
               AND pen.rn = 1
            LEFT JOIN riesgo_match rie
                ON rie.id_predio = p.id_predio
               AND rie.rn = 1
        )
        INSERT INTO predio_contexto_espacial (
            id_predio,
            pendiente_codigo,
            pendiente_area_m2,
            pendiente_cobertura_pct,
            riesgo_codigo,
            riesgo_grado,
            riesgo_area_m2,
            riesgo_cobertura_pct,
            fecha_calculo
        )
        SELECT
            id_predio,
            pendiente_codigo,
            pendiente_area_m2,
            pendiente_cobertura_pct,
            riesgo_codigo,
            riesgo_grado,
            riesgo_area_m2,
            riesgo_cobertura_pct,
            CURRENT_TIMESTAMP
        FROM resumen
        ON CONFLICT (id_predio) DO UPDATE
        SET
            pendiente_codigo = EXCLUDED.pendiente_codigo,
            pendiente_area_m2 = EXCLUDED.pendiente_area_m2,
            pendiente_cobertura_pct = EXCLUDED.pendiente_cobertura_pct,
            riesgo_codigo = EXCLUDED.riesgo_codigo,
            riesgo_grado = EXCLUDED.riesgo_grado,
            riesgo_area_m2 = EXCLUDED.riesgo_area_m2,
            riesgo_cobertura_pct = EXCLUDED.riesgo_cobertura_pct,
            fecha_calculo = CURRENT_TIMESTAMP
    """


def build_actualizar_valoracion_sql() -> str:
    return """
        WITH zh AS (
            SELECT
                idzonavalo,
                NULLIF(TRIM(zonavalor), '') AS zonavalor,
                NULLIF(TRIM(grupovalor), '') AS grupovalor,
                geometry
            FROM staging_zonas_homogeneas
            WHERE geometry IS NOT NULL
        ),
        sm_codigo AS (
            SELECT DISTINCT ON (CAST("DISTCAT" AS INT), CAST("MANZANA" AS INT))
                CAST("DISTCAT" AS INT) AS distcat,
                CAST("MANZANA" AS INT) AS manzana,
                "MACRODISTR" AS macrodistr,
                "TIPO" AS tipo,
                "AJUSTE" AS ajuste,
                "SERVICIOS" AS servicios_manzana,
                CASE
                    WHEN split_part("DDMM", '-', 1) ~ '^[0-9]+$'
                    THEN split_part("DDMM", '-', 1)::INT
                    ELSE NULL
                END AS prefijo_ddmm
            FROM staging_manzanas
            WHERE "DISTCAT" IS NOT NULL
              AND "MANZANA" IS NOT NULL
            ORDER BY
                CAST("DISTCAT" AS INT),
                CAST("MANZANA" AS INT),
                ("DDMM" IS NOT NULL) DESC,
                ("TIPO" IS NOT NULL) DESC,
                ("SERVICIOS" IS NOT NULL) DESC
        ),
        sm_espacial AS (
            SELECT DISTINCT ON (m.id_manzana)
                m.id_manzana,
                sm."MACRODISTR" AS macrodistr,
                sm."TIPO" AS tipo,
                sm."AJUSTE" AS ajuste,
                sm."SERVICIOS" AS servicios_manzana,
                CASE
                    WHEN split_part(sm."DDMM", '-', 1) ~ '^[0-9]+$'
                    THEN split_part(sm."DDMM", '-', 1)::INT
                    ELSE NULL
                END AS prefijo_ddmm
            FROM manzana m
            JOIN staging_manzanas sm
                ON m.geom && sm.geometry
               AND ST_Intersects(m.geom, sm.geometry)
            ORDER BY
                m.id_manzana,
                ST_Area(ST_Intersection(m.geom, sm.geometry)) DESC
        ),
        sp AS (
            SELECT DISTINCT ON ("COD_SIFCA")
                "COD_SIFCA" AS codigo_catastral,
                "GSBSSERV" AS servicios_predio
            FROM staging_predios
            WHERE "COD_SIFCA" IS NOT NULL
            ORDER BY "COD_SIFCA", ("GSBSSERV" IS NOT NULL) DESC
        ),
        predio_ctx AS (
            SELECT
                p.id_predio,
                p.codigo_catastral,
                COALESCE(sm_codigo.macrodistr, sm_espacial.macrodistr) AS macrodistr,
                COALESCE(sm_codigo.tipo, sm_espacial.tipo) AS tipo,
                COALESCE(sm_codigo.ajuste, sm_espacial.ajuste) AS ajuste,
                COALESCE(sm_codigo.servicios_manzana, sm_espacial.servicios_manzana) AS servicios_manzana,
                COALESCE(sm_codigo.prefijo_ddmm, sm_espacial.prefijo_ddmm) AS prefijo_ddmm,
                sp.servicios_predio,
                zh_predio.zonavalor AS zh_zonavalor,
                zh_predio.grupovalor AS zh_grupovalor,
                CASE
                    WHEN sm_codigo.distcat IS NOT NULL THEN 'codigo'
                    WHEN sm_espacial.id_manzana IS NOT NULL THEN 'espacial'
                    ELSE 'sin_match'
                END AS fuente_staging,
                CASE
                    WHEN COALESCE(sm_codigo.macrodistr, sm_espacial.macrodistr) IN (4, 5, 6) THEN 1
                    WHEN COALESCE(sm_codigo.macrodistr, sm_espacial.macrodistr) IN (0, 1, 2, 3, 7, 8, 9) THEN 2
                    ELSE NULL
                END AS macro_zona_heuristica,
                CASE
                    WHEN COALESCE(sm_codigo.tipo, sm_espacial.tipo) = 1 THEN 'ASFALTO'
                    WHEN COALESCE(sm_codigo.tipo, sm_espacial.tipo) = 2 THEN 'ADOQUIN'
                    WHEN COALESCE(sm_codigo.tipo, sm_espacial.tipo) = 3 THEN 'CEMENTO'
                    WHEN COALESCE(sm_codigo.tipo, sm_espacial.tipo) = 4 THEN 'LOSETA'
                    WHEN COALESCE(sm_codigo.tipo, sm_espacial.tipo) = 5 THEN 'PIEDRA'
                    WHEN COALESCE(sm_codigo.tipo, sm_espacial.tipo) = 6 THEN 'RIPIO'
                    WHEN COALESCE(sm_codigo.tipo, sm_espacial.tipo) IN (0, 999) THEN 'TIERRA'
                    ELSE NULL
                END AS material_via_nombre
            FROM predio p
            JOIN manzana m
                ON m.id_manzana = p.id_manzana
            LEFT JOIN sm_codigo
                ON sm_codigo.distcat = CAST(substring(m.codigo_interno from 11 for 3) AS INT)
               AND sm_codigo.manzana = CAST(m.codigo_manzana AS INT)
            LEFT JOIN sm_espacial
                ON sm_espacial.id_manzana = m.id_manzana
            LEFT JOIN sp
                ON sp.codigo_catastral = p.codigo_catastral
            LEFT JOIN LATERAL (
                SELECT
                    zh.zonavalor,
                    zh.grupovalor
                FROM zh
                WHERE zh.geometry && ST_PointOnSurface(p.geom)
                  AND ST_Intersects(zh.geometry, ST_PointOnSurface(p.geom))
                ORDER BY zh.idzonavalo
                LIMIT 1
            ) zh_predio ON TRUE
        ),
        prefijo_macro_unico AS (
            SELECT
                prefijo,
                MIN(macro_zona) AS macro_zona_unica
            FROM (
                SELECT
                    generate_series(subzona_inicio, subzona_fin) AS prefijo,
                    macro_zona
                FROM zona_valor
                WHERE vigencia_desde = DATE '2015-01-01'
            ) rangos
            GROUP BY prefijo
            HAVING COUNT(DISTINCT macro_zona) = 1
        ),
        predio_update AS (
            SELECT
                pc.id_predio,
                mv.id_material_via,
                COALESCE(zv_homogenea.id_zona_valor, zv_directa.id_zona_valor, zv_fallback.id_zona_valor) AS id_zona_valor,
                COALESCE(NULLIF(pc.servicios_predio, ''), NULLIF(pc.servicios_manzana, '')) AS servicios_codigo
            FROM predio_ctx pc
            LEFT JOIN material_via mv
                ON mv.nombre = pc.material_via_nombre
            LEFT JOIN zona_valor zv_homogenea
                ON zv_homogenea.vigencia_desde = DATE '2015-01-01'
               AND (
                    (
                        pc.zh_zonavalor IS NOT NULL
                        AND pc.zh_zonavalor ~ '^[0-9]+-[0-9]+$'
                        AND zv_homogenea.macro_zona = split_part(pc.zh_zonavalor, '-', 1)::INT
                        AND split_part(pc.zh_zonavalor, '-', 2)::INT BETWEEN zv_homogenea.subzona_inicio AND zv_homogenea.subzona_fin
                    )
                    OR (
                        pc.zh_grupovalor = '1-1' AND zv_homogenea.macro_zona = 1 AND zv_homogenea.subzona_inicio = 10 AND zv_homogenea.subzona_fin = 10
                    )
                    OR (
                        pc.zh_grupovalor = '1-2' AND zv_homogenea.macro_zona = 1 AND zv_homogenea.subzona_inicio = 20 AND zv_homogenea.subzona_fin = 28
                    )
                    OR (
                        pc.zh_grupovalor = '1-3' AND zv_homogenea.macro_zona = 1 AND zv_homogenea.subzona_inicio = 30 AND zv_homogenea.subzona_fin = 38
                    )
                    OR (
                        pc.zh_grupovalor = '1-4' AND zv_homogenea.macro_zona = 1 AND zv_homogenea.subzona_inicio = 40 AND zv_homogenea.subzona_fin = 47
                    )
                    OR (
                        pc.zh_grupovalor = '1-5' AND zv_homogenea.macro_zona = 1 AND zv_homogenea.subzona_inicio = 50 AND zv_homogenea.subzona_fin = 58
                    )
                    OR (
                        pc.zh_grupovalor = '2-1' AND zv_homogenea.macro_zona = 2 AND zv_homogenea.subzona_inicio = 10 AND zv_homogenea.subzona_fin = 18
                    )
                    OR (
                        pc.zh_grupovalor = '2-2' AND zv_homogenea.macro_zona = 2 AND zv_homogenea.subzona_inicio = 20 AND zv_homogenea.subzona_fin = 29
                    )
                    OR (
                        pc.zh_grupovalor = '2-3' AND zv_homogenea.macro_zona = 2 AND zv_homogenea.subzona_inicio = 30 AND zv_homogenea.subzona_fin = 34
                    )
                    OR (
                        pc.zh_grupovalor = '2-4' AND zv_homogenea.macro_zona = 2 AND zv_homogenea.subzona_inicio = 40 AND zv_homogenea.subzona_fin = 45
                    )
                    OR (
                        pc.zh_grupovalor = '2-5' AND zv_homogenea.macro_zona = 2 AND zv_homogenea.subzona_inicio = 50 AND zv_homogenea.subzona_fin = 58
                    )
                    OR (
                        pc.zh_grupovalor = '2-6' AND zv_homogenea.macro_zona = 2 AND zv_homogenea.subzona_inicio = 60 AND zv_homogenea.subzona_fin = 68
                    )
                    OR (
                        pc.zh_grupovalor = '2-7' AND zv_homogenea.macro_zona = 2 AND zv_homogenea.subzona_inicio = 70 AND zv_homogenea.subzona_fin = 76
                    )
                    OR (
                        pc.zh_grupovalor = '2-8' AND zv_homogenea.macro_zona = 2 AND zv_homogenea.subzona_inicio = 80 AND zv_homogenea.subzona_fin = 82
                    )
                    OR (
                        pc.zh_grupovalor = '3-1' AND zv_homogenea.macro_zona = 3 AND zv_homogenea.subzona_inicio = 10 AND zv_homogenea.subzona_fin = 16
                    )
                    OR (
                        pc.zh_grupovalor = '3-2' AND zv_homogenea.macro_zona = 3 AND zv_homogenea.subzona_inicio = 20 AND zv_homogenea.subzona_fin = 21
                    )
                    OR (
                        pc.zh_grupovalor = '3-3' AND zv_homogenea.macro_zona = 3 AND zv_homogenea.subzona_inicio = 30 AND zv_homogenea.subzona_fin = 36
                    )
               )
            LEFT JOIN zona_valor zv_directa
                ON zv_directa.macro_zona = pc.macro_zona_heuristica
               AND pc.prefijo_ddmm BETWEEN zv_directa.subzona_inicio AND zv_directa.subzona_fin
               AND zv_directa.vigencia_desde = DATE '2015-01-01'
            LEFT JOIN prefijo_macro_unico pmu
                ON pmu.prefijo = pc.prefijo_ddmm
            LEFT JOIN zona_valor zv_fallback
                ON zv_directa.id_zona_valor IS NULL
               AND zv_fallback.macro_zona = pmu.macro_zona_unica
               AND pc.prefijo_ddmm BETWEEN zv_fallback.subzona_inicio AND zv_fallback.subzona_fin
               AND zv_fallback.vigencia_desde = DATE '2015-01-01'
        )
        UPDATE predio p
        SET
            id_material_via = pu.id_material_via,
            id_zona_valor = pu.id_zona_valor
        FROM predio_update pu
        WHERE pu.id_predio = p.id_predio
    """


def build_insert_predio_servicio_sql() -> str:
    return """
        WITH sm_codigo AS (
            SELECT DISTINCT ON (CAST("DISTCAT" AS INT), CAST("MANZANA" AS INT))
                CAST("DISTCAT" AS INT) AS distcat,
                CAST("MANZANA" AS INT) AS manzana,
                "SERVICIOS" AS servicios_manzana
            FROM staging_manzanas
            WHERE "DISTCAT" IS NOT NULL
              AND "MANZANA" IS NOT NULL
            ORDER BY
                CAST("DISTCAT" AS INT),
                CAST("MANZANA" AS INT),
                ("SERVICIOS" IS NOT NULL) DESC
        ),
        sm_espacial AS (
            SELECT DISTINCT ON (m.id_manzana)
                m.id_manzana,
                sm."SERVICIOS" AS servicios_manzana
            FROM manzana m
            JOIN staging_manzanas sm
                ON m.geom && sm.geometry
               AND ST_Intersects(m.geom, sm.geometry)
            ORDER BY
                m.id_manzana,
                ST_Area(ST_Intersection(m.geom, sm.geometry)) DESC
        ),
        sp AS (
            SELECT DISTINCT ON ("COD_SIFCA")
                "COD_SIFCA" AS codigo_catastral,
                "GSBSSERV" AS servicios_predio
            FROM staging_predios
            WHERE "COD_SIFCA" IS NOT NULL
            ORDER BY "COD_SIFCA", ("GSBSSERV" IS NOT NULL) DESC
        ),
        predio_servicios_src AS (
            SELECT
                p.id_predio,
                LEFT(
                    COALESCE(
                        NULLIF(sp.servicios_predio, ''),
                        NULLIF(sm_codigo.servicios_manzana, ''),
                        NULLIF(sm_espacial.servicios_manzana, '')
                    ),
                    6
                ) AS bits_servicio
            FROM predio p
            JOIN manzana m
                ON m.id_manzana = p.id_manzana
            LEFT JOIN sm_codigo
                ON sm_codigo.distcat = CAST(substring(m.codigo_interno from 11 for 3) AS INT)
               AND sm_codigo.manzana = CAST(m.codigo_manzana AS INT)
            LEFT JOIN sm_espacial
                ON sm_espacial.id_manzana = m.id_manzana
            LEFT JOIN sp
                ON sp.codigo_catastral = p.codigo_catastral
        ),
        expanded AS (
            SELECT DISTINCT
                pss.id_predio,
                svc.id_servicio,
                tc.id_tipo_conexion
            FROM predio_servicios_src pss
            CROSS JOIN LATERAL (
                VALUES
                    (1, 'ENERGIA ELECTRICA'),
                    (2, 'AGUA POTABLE'),
                    (3, 'ALCANTARILLADO'),
                    (4, 'TELEFONO'),
                    (5, 'GAS DOMICILIARIO'),
                    (6, 'INTERNET')
            ) AS mapa(posicion, nombre_servicio)
            JOIN servicio svc
                ON svc.nombre = mapa.nombre_servicio
            JOIN tipo_conexion tc
                ON tc.nombre = 'DIRECTA'
            WHERE LENGTH(COALESCE(pss.bits_servicio, '')) >= mapa.posicion
              AND SUBSTRING(pss.bits_servicio FROM mapa.posicion FOR 1) = '1'
        )
        INSERT INTO predio_servicio (
            id_predio,
            id_servicio,
            id_tipo_conexion
        )
        SELECT
            e.id_predio,
            e.id_servicio,
            e.id_tipo_conexion
        FROM expanded e
        ON CONFLICT (id_predio, id_servicio) DO UPDATE
        SET id_tipo_conexion = EXCLUDED.id_tipo_conexion
    """


def build_construccion_insert_sql() -> str:
    return """
        INSERT INTO construccion (
            id_predio,
            id_tipologia,
            anio_construccion,
            superficie_construida,
            numero_bloques,
            es_propiedad_horizontal
        )
        VALUES (
            :id_predio,
            :id_tipologia,
            :anio_construccion,
            :superficie_construida,
            :numero_bloques,
            :es_propiedad_horizontal
        )
    """


# =====================================================
# FUNCIONES AUXILIARES
# =====================================================

def reparar_geometria(geom):
    """
    Repara una geometría individual:
    1. make_valid (Shapely)
    2. Extraer polígonos si es GeometryCollection
    3. Convertir a MultiPolygon
    """
    if geom is None or geom.is_empty:
        return None

    if not geom.is_valid:
        geom = make_valid(geom)

    if geom.geom_type == 'GeometryCollection':
        polygons = [g for g in geom.geoms
                    if g.geom_type in ('Polygon', 'MultiPolygon')]
        if not polygons:
            return None
        if len(polygons) == 1:
            geom = polygons[0]
        else:
            all_polys = []
            for p in polygons:
                if p.geom_type == 'MultiPolygon':
                    all_polys.extend(p.geoms)
                else:
                    all_polys.append(p)
            geom = MultiPolygon(all_polys)

    if geom.geom_type == 'Polygon':
        geom = MultiPolygon([geom])

    if geom.geom_type != 'MultiPolygon' or geom.is_empty:
        return None

    return geom


def cargar_y_reparar_shp(nombre_capa: str):
    """Lee un shapefile, reproyecta y repara geometrías."""
    ruta = SHAPEFILES_DIR / CAPAS[nombre_capa]["archivo"]

    if not ruta.exists():
        console.print(f"[red]  ✗ No encontrado: {ruta}[/red]")
        return None

    console.print(f"\n[cyan]  📂 Leyendo {nombre_capa}: {ruta.name}[/cyan]")
    gdf = gpd.read_file(ruta)
    total_original = len(gdf)
    console.print(f"     Registros: {total_original}")
    console.print(f"     CRS: {gdf.crs}")

    # Reproyectar si es necesario
    if gdf.crs is not None and gdf.crs.to_epsg() != SRID:
        console.print(f"     [yellow]🔄 Reproyectando EPSG:{gdf.crs.to_epsg()} → EPSG:{SRID}[/yellow]")
        gdf = gdf.to_crs(epsg=SRID)
    elif gdf.crs is None:
        console.print(f"     [yellow]⚠ Sin CRS. Asignando EPSG:{SRID}[/yellow]")
        gdf = gdf.set_crs(epsg=SRID)

    # Reparar geometrías
    console.print("     🔧 Reparando geometrías...")
    gdf['geometry'] = gdf['geometry'].apply(reparar_geometria)

    antes = len(gdf)
    gdf = gdf[gdf['geometry'].notna()].copy()
    descartadas = antes - len(gdf)

    if descartadas > 0:
        console.print(f"     [yellow]⚠ {descartadas} geometrías irrecuperables descartadas[/yellow]")

    console.print(f"     [green]✓ {len(gdf)}/{total_original} features válidas[/green]")
    return gdf


# =====================================================
# COMANDO: explorar
# =====================================================

@app.command()
def explorar():
    """Muestra las columnas y tipos de cada shapefile."""
    console.print("\n[bold]═══ EXPLORADOR DE SHAPEFILES ═══[/bold]\n")

    for nombre, config in CAPAS.items():
        ruta = SHAPEFILES_DIR / config["archivo"]

        if not ruta.exists():
            console.print(f"[red]✗ {nombre}: {ruta} NO ENCONTRADO[/red]\n")
            continue

        gdf = gpd.read_file(ruta)

        table = Table(title=f"📋 {nombre.upper()} — {config['archivo']}")
        table.add_column("Columna", style="cyan")
        table.add_column("Tipo", style="green")
        table.add_column("Ejemplo", style="white", max_width=50)
        table.add_column("Nulos", style="yellow")

        for col in gdf.columns:
            if col != 'geometry':
                ejemplo = str(gdf[col].iloc[0]) if len(gdf) > 0 else "N/A"
                nulos = str(gdf[col].isna().sum())
                table.add_row(col, str(gdf[col].dtype), ejemplo[:50], nulos)

        console.print(table)
        console.print(f"  Total: {len(gdf)} | CRS: {gdf.crs} | Geom: {gdf.geom_type.unique().tolist()}")

        invalidas = sum(1 for g in gdf.geometry if g is not None and not g.is_valid)
        nulas = sum(1 for g in gdf.geometry if g is None or g.is_empty)
        console.print(f"  Inválidas: [red]{invalidas}[/red] | Nulas: [red]{nulas}[/red]\n")


# =====================================================
# COMANDO: staging
# =====================================================

@app.command()
def staging():
    """Importa los shapefiles a tablas staging con reparación de geometrías."""
    console.print("\n[bold]═══ IMPORTACIÓN A STAGING ═══[/bold]")

    try:
        version = test_connection()
        console.print(f"\n[green]  ✓ Conectado — PostGIS {version}[/green]")
    except Exception as e:
        console.print(f"\n[red]  ✗ Error de conexión: {e}[/red]")
        raise typer.Exit(1)

    for nombre, config in CAPAS.items():
        tabla = config["tabla_staging"]

        console.print(f"\n[bold]--- {nombre.upper()} → {tabla} ---[/bold]")

        gdf = cargar_y_reparar_shp(nombre)
        if gdf is None:
            continue

        # Limpiar nombres de columnas
        gdf.columns = [c.strip() for c in gdf.columns]

        # Eliminar tabla staging previa
        with sync_engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {tabla} CASCADE"))

        # Escribir a PostGIS
        console.print(f"     📥 Escribiendo a {tabla}...")
        try:
            gdf.to_postgis(
                tabla,
                sync_engine,
                if_exists='replace',
                index=True,
                index_label='id',
            )

            # Crear índice espacial
            with sync_engine.begin() as conn:
                conn.execute(text(
                    f"CREATE INDEX IF NOT EXISTS idx_{tabla}_geom "
                    f"ON {tabla} USING GIST (geometry)"
                ))

            console.print(f"     [green]✓ {len(gdf)} registros en {tabla}[/green]")

        except Exception as e:
            console.print(f"     [red]✗ Error: {e}[/red]")
            import traceback
            traceback.print_exc()

    console.print("\n[green bold]═══ STAGING COMPLETADO ═══[/green bold]\n")


# =====================================================
# COMANDO: explorar-staging
# =====================================================

@app.command("explorar-staging")
def explorar_staging():
    """Muestra las columnas importadas en las tablas staging."""
    console.print("\n[bold]═══ COLUMNAS EN TABLAS STAGING ═══[/bold]\n")

    for nombre, config in CAPAS.items():
        tabla = config["tabla_staging"]

        try:
            with sync_engine.connect() as conn:
                result = conn.execute(text(
                    "SELECT column_name, data_type "
                    "FROM information_schema.columns "
                    "WHERE table_name = :tabla ORDER BY ordinal_position"
                ), {"tabla": tabla})
                columnas = result.fetchall()

                if not columnas:
                    console.print(f"[yellow]  ⚠ {tabla}: no existe[/yellow]\n")
                    continue

                count = conn.execute(text(f"SELECT COUNT(*) FROM {tabla}")).scalar()

                table = Table(title=f"📋 {tabla} ({count} registros)")
                table.add_column("Columna", style="cyan")
                table.add_column("Tipo", style="green")

                for col_name, col_type in columnas:
                    table.add_row(col_name, col_type)

                console.print(table)

                # Muestra de datos
                cols_no_geom = [c[0] for c in columnas if c[1] not in ('USER-DEFINED',)][:6]
                if cols_no_geom:
                    cols_str = ", ".join(f'"{c}"' for c in cols_no_geom)
                    result = conn.execute(text(f"SELECT {cols_str} FROM {tabla} LIMIT 3"))
                    rows = result.fetchall()
                    if rows:
                        console.print("  Muestra:")
                        for row in rows:
                            console.print(f"    {dict(zip(cols_no_geom, row))}")
                console.print()

        except Exception as e:
            console.print(f"[red]  ✗ {tabla}: {e}[/red]\n")


# =====================================================
# COMANDO: reparar
# =====================================================

@app.command()
def reparar():
    """Repara geometrías directamente en PostgreSQL (doble seguridad)."""
    console.print("\n[bold]═══ REPARACIÓN EN POSTGRESQL ═══[/bold]\n")

    tablas = [c["tabla_staging"] for c in CAPAS.values()]

    for tabla in tablas:
        console.print(f"[cyan]  🔧 Reparando {tabla}...[/cyan]")

        try:
            with sync_engine.begin() as conn:
                # Verificar si la tabla existe
                exists = conn.execute(text(
                    "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                    "WHERE table_name = :tabla)"
                ), {"tabla": tabla}).scalar()

                if not exists:
                    console.print(f"     [yellow]⚠ No existe, saltando[/yellow]")
                    continue

                # Detectar nombre de columna geométrica
                geom_col_result = conn.execute(text(
                    "SELECT f_geometry_column FROM geometry_columns "
                    "WHERE f_table_name = :tabla LIMIT 1"
                ), {"tabla": tabla})
                geom_col_row = geom_col_result.fetchone()
                geom_col = geom_col_row[0] if geom_col_row else 'geometry'

                # Diagnóstico previo
                result = conn.execute(text(f"""
                    SELECT
                        COUNT(*) as total,
                        COUNT(*) FILTER (WHERE NOT ST_IsValid({geom_col})) as invalidas,
                        COUNT(*) FILTER (WHERE {geom_col} IS NULL) as nulas,
                        COUNT(*) FILTER (WHERE ST_IsEmpty({geom_col})) as vacias
                    FROM {tabla}
                """))
                row = result.fetchone()
                console.print(f"     Pre: {row[0]} total, {row[1]} inválidas, {row[2]} nulas, {row[3]} vacías")

                # Reparar con ST_MakeValid
                conn.execute(text(f"""
                    UPDATE {tabla}
                    SET {geom_col} = ST_Multi(ST_CollectionExtract(ST_MakeValid({geom_col}), 3))
                    WHERE NOT ST_IsValid({geom_col})
                """))

                # Forzar MultiPolygon
                conn.execute(text(f"""
                    UPDATE {tabla}
                    SET {geom_col} = ST_Multi({geom_col})
                    WHERE GeometryType({geom_col}) = 'POLYGON'
                """))

                # Asegurar SRID
                conn.execute(text(f"""
                    UPDATE {tabla}
                    SET {geom_col} = ST_SetSRID({geom_col}, {SRID})
                    WHERE ST_SRID({geom_col}) != {SRID} OR ST_SRID({geom_col}) = 0
                """))

                # Eliminar irrecuperables
                result = conn.execute(text(f"""
                    DELETE FROM {tabla}
                    WHERE {geom_col} IS NULL
                       OR ST_IsEmpty({geom_col})
                       OR GeometryType({geom_col}) NOT LIKE '%POLYGON%'
                """))
                console.print(f"     Eliminadas irrecuperables: {result.rowcount}")

                # Diagnóstico posterior
                result = conn.execute(text(f"""
                    SELECT COUNT(*) as total,
                           COUNT(*) FILTER (WHERE NOT ST_IsValid({geom_col})) as invalidas
                    FROM {tabla}
                """))
                row = result.fetchone()
                console.print(f"     [green]✓ Post: {row[0]} válidas, {row[1]} aún inválidas[/green]")

        except Exception as e:
            console.print(f"     [red]✗ Error: {e}[/red]")
            import traceback
            traceback.print_exc()

    console.print("\n[green bold]═══ REPARACIÓN COMPLETADA ═══[/green bold]\n")


# =====================================================
# COMANDO: transferir
# =====================================================

@app.command()
def transferir():
    console.print("\n=== TRANSFERENCIA STAGING -> TABLAS DEFINITIVAS ===")

    with sync_engine.begin() as conn:
        cur = conn.connection.cursor()

        # =====================================================
        # 1. JERARQUÍA (dummy para pruebas)
        # =====================================================
        print("\n  1. Creando jerarquía territorial...")

        cur.execute("""
        INSERT INTO departamento (id_departamento, nombre, codigo_departamento, codigo_interno)
        VALUES (gen_random_uuid(), 'LA PAZ', '02', '02')
        ON CONFLICT DO NOTHING;
        """)

        cur.execute("""
        INSERT INTO provincia (id_provincia, id_departamento, nombre, codigo_provincia, codigo_interno)
        SELECT gen_random_uuid(), d.id_departamento, 'MURILLO', '01', '0201'
        FROM departamento d LIMIT 1
        ON CONFLICT DO NOTHING;
        """)

        cur.execute("""
        INSERT INTO municipio (id_municipio, id_provincia, nombre, codigo_municipio, codigo_interno)
        SELECT gen_random_uuid(), p.id_provincia, 'LA PAZ', '01', '020101'
        FROM provincia p LIMIT 1
        ON CONFLICT DO NOTHING;
        """)

        cur.execute("""
        INSERT INTO distrito (id_distrito, id_municipio, nombre, codigo_distrito, codigo_interno)
        SELECT gen_random_uuid(), m.id_municipio, 'DISTRITO 1', '01', '02010101'
        FROM municipio m LIMIT 1
        ON CONFLICT DO NOTHING;
        """)

        cur.execute("""
        INSERT INTO zona (id_zona, id_distrito, nombre, codigo_zona, codigo_interno)
        SELECT gen_random_uuid(), d.id_distrito, 'ZONA 1', '01', '0201010101'
        FROM distrito d LIMIT 1
        ON CONFLICT DO NOTHING;
        """)

        # Ajustes para compatibilizar el modelo con los codigos reales del catastro.
        cur.execute("""
        ALTER TABLE manzana
        DROP CONSTRAINT IF EXISTS chk_manzana_codigo;
        """)
        cur.execute("""
        ALTER TABLE manzana
        DROP CONSTRAINT IF EXISTS manzana_codigo_manzana_id_zona_key;
        """)
        cur.execute("""
        ALTER TABLE manzana
        DROP CONSTRAINT IF EXISTS chk_manzana_interno;
        """)
        cur.execute("""
        ALTER TABLE manzana
        ALTER COLUMN codigo_manzana TYPE VARCHAR(10);
        """)
        cur.execute("""
        ALTER TABLE manzana
        ALTER COLUMN codigo_interno TYPE VARCHAR(20);
        """)
        cur.execute("""
        ALTER TABLE predio
        ALTER COLUMN codigo_catastral TYPE VARCHAR(50);
        """)
        cur.execute("""
        ALTER TABLE manzana
        ADD CONSTRAINT chk_manzana_codigo
        CHECK (codigo_manzana ~ '^[0-9]{1,5}$');
        """)
        cur.execute("""
        ALTER TABLE manzana
        ADD CONSTRAINT chk_manzana_interno
        CHECK (codigo_interno ~ '^[0-9]{10,20}$');
        """)

        # Asegura un estado por defecto para poder insertar predios.
        cur.execute("""
        INSERT INTO estado_predio (id_estado_predio, nombre, descripcion)
        VALUES (gen_random_uuid(), 'ACTIVO', 'Estado por defecto para importacion inicial')
        ON CONFLICT (nombre) DO NOTHING;
        """)

        print("     OK Jerarquia territorial lista")

        # Evita duplicados si vuelves a correr la carga.
        cur.execute("TRUNCATE predio CASCADE;")
        cur.execute("TRUNCATE manzana CASCADE;")

        # =====================================================
        # 2. MANZANAS
        # =====================================================
        print("\n  2. Transfiriendo manzanas...")

        sql_mzn = """
        INSERT INTO manzana (
            id_manzana,
            id_zona,
            codigo_manzana,
            codigo_interno,
            geom
        )
        SELECT
            gen_random_uuid(),
            z.id_zona,
            m.codigo_manzana,
            m.codigo_interno,
            m.geometry
        FROM (
            SELECT DISTINCT ON (codigo_interno, codigo_manzana)
                LPAD(CAST("MANZANA" AS TEXT), 3, '0') AS codigo_manzana,
                '0201010101'
                || LPAD(CAST("DISTCAT" AS TEXT), 3, '0')
                || LPAD(CAST("MANZANA" AS TEXT), 4, '0') AS codigo_interno,
                geometry
            FROM staging_manzanas
            WHERE geometry IS NOT NULL
              AND "MANZANA" IS NOT NULL
              AND CAST("MANZANA" AS BIGINT) > 0
            ORDER BY codigo_interno, codigo_manzana, ST_Area(geometry) DESC
        ) AS m
        CROSS JOIN zona z;
        """

        cur.execute(sql_mzn)
        print(f"     OK {cur.rowcount} manzanas")

        # =====================================================
        # 3. PREDIOS
        # =====================================================
        print("\n  3. Transfiriendo predios...")

        sql_pred = """
        INSERT INTO predio (
            id_predio,
            id_manzana,
            id_estado_predio,
            codigo_catastral,
            superficie_mensura,
            geom
        )
        SELECT
            gen_random_uuid(),
            m.id_manzana,
            ep.id_estado_predio,
            p.codigo_catastral,
            p.superficie,
            p.geometry
        FROM (
            SELECT DISTINCT ON ("COD_SIFCA")
                "COD_SIFCA" AS codigo_catastral,
                ST_Area(geometry) AS superficie,
                geometry,
                '0201010101'
                || LPAD(CAST("DISTCAT" AS TEXT), 3, '0')
                || LPAD(CAST("MANZANA" AS TEXT), 4, '0') AS codigo_interno
            FROM staging_predios
            WHERE geometry IS NOT NULL
              AND ST_Area(geometry) >= 0.01
            ORDER BY "COD_SIFCA", ST_Area(geometry) DESC
        ) AS p
        JOIN manzana m ON m.codigo_interno = p.codigo_interno
        CROSS JOIN (
            SELECT id_estado_predio
            FROM estado_predio
            ORDER BY nombre
            LIMIT 1
        ) AS ep;
        """

        print("     Procesando predios...")
        cur.execute(sql_pred)
        print(f"     OK {cur.rowcount} predios")

        cur.close()

    print("\n=== TRANSFERENCIA COMPLETADA ===")
# =====================================================
# COMANDO: todo
# =====================================================

@app.command()
def todo():
    """Ejecuta el flujo completo: staging → reparar → transferir."""
    console.print("\n[bold magenta]=======================================[/bold magenta]")
    console.print("[bold magenta]   IMPORTACION COMPLETA - AVALIX v2   [/bold magenta]")
    console.print("[bold magenta]=======================================[/bold magenta]")

    staging()
    reparar()
    transferir()

    console.print("\n[bold green]TODO LISTO - verifica en QGIS[/bold green]\n")


# =====================================================
# COMANDO: diagnostico
# =====================================================

@app.command()
def diagnostico():
    """Muestra diagnóstico completo de la BD."""
    console.print("\n[bold]═══ DIAGNÓSTICO DE LA BD ═══[/bold]\n")

    try:
        version = test_connection()
        console.print(f"  PostGIS: {version}")

        tablas = [
            'departamento', 'provincia', 'municipio', 'distrito',
            'zona', 'manzana', 'predio',
            'staging_predios', 'staging_manzanas',
            'staging_pendientes', 'staging_riesgos',
            'staging_zonas_homogeneas'
        ]

        table = Table(title="Estado de la BD")
        table.add_column("Tabla", style="cyan")
        table.add_column("Registros", style="green", justify="right")

        with sync_engine.connect() as conn:
            for t in tablas:
                try:
                    count = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
                    table.add_row(t, str(count))
                except Exception:
                    table.add_row(t, "[red]no existe[/red]")

        console.print(table)

        # Extent de capas
        console.print("\n  [bold]Extensión geográfica:[/bold]")
        with sync_engine.connect() as conn:
            for t, gcol in [('manzana', 'geom'), ('predio', 'geom'),
                             ('staging_predios', None), ('staging_manzanas', None)]:
                try:
                    if gcol is None:
                        r = conn.execute(text(
                            "SELECT f_geometry_column FROM geometry_columns "
                            "WHERE f_table_name = :t LIMIT 1"
                        ), {"t": t})
                        row = r.fetchone()
                        gcol = row[0] if row else 'geometry'

                    result = conn.execute(text(f"""
                        SELECT
                            ROUND(ST_XMin(ext)::NUMERIC, 0),
                            ROUND(ST_YMin(ext)::NUMERIC, 0),
                            ROUND(ST_XMax(ext)::NUMERIC, 0),
                            ROUND(ST_YMax(ext)::NUMERIC, 0)
                        FROM (SELECT ST_Extent({gcol}) as ext FROM {t}) s
                    """))
                    row = result.fetchone()
                    if row and row[0]:
                        console.print(f"    {t}: X[{row[0]}-{row[2]}] Y[{row[1]}-{row[3]}]")
                except Exception:
                    pass

    except Exception as e:
        console.print(f"[red]  ✗ Error: {e}[/red]")

    console.print()


# =====================================================
# COMANDO: contexto-espacial
# =====================================================

@app.command("contexto-espacial")
def contexto_espacial(
    batch_size: int = typer.Option(2000, help="Cantidad de predios por lote."),
    max_batches: int = typer.Option(
        0, help="Maximo de lotes a procesar; 0 procesa todos."
    ),
    modo: str = typer.Option(
        "rapido", help="Modo de clasificacion: rapido o exacto."
    ),
):
    """Resume pendientes y riesgos por predio usando la categoria dominante por area."""
    modo = modo.lower().strip()
    if modo not in {"rapido", "exacto"}:
        raise typer.BadParameter("modo debe ser 'rapido' o 'exacto'")

    console.print("\n[bold]=== CONTEXTO ESPACIAL POR PREDIO ===[/bold]\n")

    with sync_engine.connect() as conn:
        console.print("[cyan]  Creando tabla de resumen...[/cyan]")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS predio_contexto_espacial (
                id_predio UUID PRIMARY KEY REFERENCES predio(id_predio) ON DELETE CASCADE,
                pendiente_codigo INT,
                pendiente_area_m2 NUMERIC(14,2),
                pendiente_cobertura_pct NUMERIC(7,4),
                riesgo_codigo INT,
                riesgo_grado VARCHAR(50),
                riesgo_area_m2 NUMERIC(14,2),
                riesgo_cobertura_pct NUMERIC(7,4),
                fecha_calculo TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_predio_contexto_pendiente
            ON predio_contexto_espacial (pendiente_codigo)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_predio_contexto_riesgo
            ON predio_contexto_espacial (riesgo_codigo)
        """))
        conn.commit()

    with sync_engine.connect() as conn:
        total_predios = conn.execute(
            text("SELECT COUNT(*) FROM predio WHERE geom IS NOT NULL")
        ).scalar()

    console.print(
        f"[cyan]  Procesando {total_predios} predios en lotes de {batch_size} "
        f"(modo: {modo})...[/cyan]"
    )

    procesados = 0
    lote = 0

    while procesados < total_predios:
        if max_batches and lote >= max_batches:
            break

        with sync_engine.connect() as conn:
            result = conn.execute(
                text(build_contexto_espacial_sql(modo)),
                {"limit": batch_size, "offset": procesados},
            )
            conn.commit()

        lote += 1
        procesados += batch_size
        avance = min(procesados, total_predios)
        console.print(
            f"[green]  Lote {lote}: hasta {avance}/{total_predios} predios[/green]"
        )

        if result.rowcount == 0:
            break

    with sync_engine.connect() as conn:
        muestra = conn.execute(text("""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE pendiente_codigo IS NOT NULL) AS con_pendiente,
                COUNT(*) FILTER (WHERE riesgo_codigo IS NOT NULL) AS con_riesgo
            FROM predio_contexto_espacial
        """)).fetchone()

    console.print(
        f"[green]  Resumen: {muestra[0]} predios, "
        f"{muestra[1]} con pendiente, {muestra[2]} con riesgo[/green]"
    )

    console.print("\n[bold green]CONTEXTO ESPACIAL LISTO[/bold green]\n")


# =====================================================
# COMANDO: valoracion-base
# =====================================================

@app.command("valoracion-base")
def valoracion_base():
    """Asigna material de via, zona de valor y servicios al predio usando heuristicas del staging."""
    console.print("\n[bold]=== VALORACION BASE DE PREDIOS ===[/bold]\n")

    with sync_engine.connect() as conn:
        console.print("[cyan]  Actualizando material de via y zona de valor...[/cyan]")
        conn.execute(text(build_actualizar_valoracion_sql()))

        console.print("[cyan]  Refrescando predio_servicio...[/cyan]")
        conn.execute(text("TRUNCATE predio_servicio"))
        conn.execute(text(build_insert_predio_servicio_sql()))
        conn.commit()

        resumen = conn.execute(text("""
            SELECT
                COUNT(*) AS total_predios,
                COUNT(*) FILTER (WHERE id_material_via IS NOT NULL) AS con_material_via,
                COUNT(*) FILTER (WHERE id_zona_valor IS NOT NULL) AS con_zona_valor
            FROM predio
        """)).fetchone()

        servicios = conn.execute(text("""
            SELECT COUNT(*) AS total_predio_servicio
            FROM predio_servicio
        """)).fetchone()

    console.print(
        f"[green]  Predios: {resumen.total_predios}, "
        f"con material_via: {resumen.con_material_via}, "
        f"con zona_valor: {resumen.con_zona_valor}[/green]"
    )
    console.print(
        f"[green]  Registros predio_servicio: {servicios.total_predio_servicio}[/green]"
    )
    console.print("\n[bold green]VALORACION BASE LISTA[/bold green]\n")


# =====================================================
# COMANDO: construcciones-template
# =====================================================

@app.command("construcciones-template")
def construcciones_template(
    output: str = typer.Option(
        "db_init/construcciones_template.csv",
        help="Ruta de salida del CSV plantilla.",
    ),
    limit: int = typer.Option(
        500,
        help="Cantidad maxima de predios sugeridos para la plantilla.",
    ),
):
    """Genera un CSV base para empezar a cargar construcciones reales."""
    ruta = Path(output)
    if not ruta.is_absolute():
        ruta = Path(__file__).resolve().parent.parent.parent / ruta
    ruta.parent.mkdir(parents=True, exist_ok=True)

    sql = text(
        """
        SELECT
            p.id_predio,
            p.codigo_catastral,
            p.superficie_mensura,
            p.id_zona_valor,
            p.id_material_via
        FROM predio p
        LEFT JOIN construccion c
            ON c.id_predio = p.id_predio
        LEFT JOIN predio_contexto_espacial ctx
            ON ctx.id_predio = p.id_predio
        WHERE c.id_construccion IS NULL
          AND p.id_zona_valor IS NOT NULL
          AND p.id_material_via IS NOT NULL
          AND ctx.pendiente_codigo IS NOT NULL
        ORDER BY p.superficie_mensura DESC NULLS LAST, p.codigo_catastral
        LIMIT :limit
        """
    )

    with sync_engine.connect() as conn:
        rows = conn.execute(sql, {"limit": limit}).fetchall()

    with ruta.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "id_predio",
                "codigo_catastral",
                "superficie_terreno",
                "tipologia_codigo",
                "superficie_construida",
                "anio_construccion",
                "numero_bloques",
                "es_propiedad_horizontal",
                "observaciones",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row.id_predio,
                    row.codigo_catastral,
                    row.superficie_mensura,
                    "",
                    "",
                    "",
                    1,
                    "false",
                    "",
                ]
            )

    console.print(
        f"[green]  Plantilla generada: {ruta} ({len(rows)} filas sugeridas)[/green]"
    )
    console.print(
        "[cyan]  Usa tipologias como 30,31,32,33,34,35 o 40,41,42,43 segun la tabla.[/cyan]"
    )


# =====================================================
# COMANDO: importar-construcciones-csv
# =====================================================

@app.command("importar-construcciones-csv")
def importar_construcciones_csv(
    csv_path: str = typer.Argument(..., help="CSV con construcciones a cargar."),
    replace_existing: bool = typer.Option(
        False,
        help="Si es true, elimina construcciones previas del predio antes de insertar.",
    ),
    dry_run: bool = typer.Option(
        False, help="Solo valida y resume, sin insertar datos."
    ),
):
    """Importa construcciones desde un CSV manual para empezar la capa construida."""
    ruta = Path(csv_path)
    if not ruta.is_absolute():
        ruta = Path(__file__).resolve().parent.parent.parent / ruta
    if not ruta.exists():
        raise typer.BadParameter(f"No existe el archivo: {ruta}")

    with ruta.open("r", newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))

    if not rows:
        console.print("[yellow]  El CSV no tiene filas para importar.[/yellow]")
        return

    required = {"tipologia_codigo", "superficie_construida", "anio_construccion"}
    insert_sql = text(build_construccion_insert_sql())
    total_insertadas = 0
    predios_reemplazados = 0
    filas_omitidas = 0
    errores: list[str] = []
    predios_limpiados: set[str] = set()

    with sync_engine.connect() as conn:
        esquema_row = conn.execute(
            text(
                """
                SELECT id_esquema
                FROM esquema_valuacion
                ORDER BY fecha_inicio DESC
                LIMIT 1
                """
            )
        ).fetchone()
        id_esquema = esquema_row.id_esquema if esquema_row else None

        for idx, row in enumerate(rows, start=2):
            # Permite usar la plantilla como borrador: si la fila aun no fue llenada,
            # se omite silenciosamente en lugar de tratarla como error.
            if not any((row.get(field) or "").strip() for field in required):
                filas_omitidas += 1
                continue

            missing = [field for field in required if not row.get(field)]
            if missing:
                errores.append(f"Fila {idx}: faltan campos requeridos {missing}")
                continue

            id_predio = (row.get("id_predio") or "").strip()
            codigo_catastral = (row.get("codigo_catastral") or "").strip()

            if not id_predio and not codigo_catastral:
                errores.append(
                    f"Fila {idx}: se requiere id_predio o codigo_catastral para ubicar el predio"
                )
                continue

            predio_row = conn.execute(
                text(
                    """
                    SELECT id_predio, codigo_catastral
                    FROM predio
                    WHERE (:id_predio <> '' AND CAST(id_predio AS TEXT) = :id_predio)
                       OR (:codigo_catastral <> '' AND codigo_catastral = :codigo_catastral)
                    LIMIT 1
                    """
                ),
                {
                    "id_predio": id_predio,
                    "codigo_catastral": codigo_catastral,
                },
            ).fetchone()

            if not predio_row:
                errores.append(
                    f"Fila {idx}: no se encontro predio para id='{id_predio}' codigo='{codigo_catastral}'"
                )
                continue

            tipologia_row = conn.execute(
                text(
                    """
                    SELECT id_tipologia
                    FROM tipologia
                    WHERE codigo = :codigo
                      AND (:id_esquema IS NULL OR id_esquema = :id_esquema)
                    ORDER BY vigencia_desde DESC
                    LIMIT 1
                    """
                ),
                {
                    "codigo": row["tipologia_codigo"].strip(),
                    "id_esquema": id_esquema,
                },
            ).fetchone()

            if not tipologia_row:
                errores.append(
                    f"Fila {idx}: tipologia_codigo '{row['tipologia_codigo']}' no existe"
                )
                continue

            try:
                superficie_construida = float(row["superficie_construida"])
                anio_construccion = int(row["anio_construccion"])
                numero_bloques = int((row.get("numero_bloques") or "1").strip())
                es_propiedad_horizontal = (
                    (row.get("es_propiedad_horizontal") or "false").strip().lower()
                    in {"1", "true", "t", "si", "sí", "yes"}
                )
            except ValueError as exc:
                errores.append(f"Fila {idx}: valores numericos invalidos ({exc})")
                continue

            if replace_existing and predio_row.id_predio not in predios_limpiados and not dry_run:
                conn.execute(
                    text("DELETE FROM construccion WHERE id_predio = :id_predio"),
                    {"id_predio": predio_row.id_predio},
                )
                predios_limpiados.add(str(predio_row.id_predio))
                predios_reemplazados += 1

            if not dry_run:
                conn.execute(
                    insert_sql,
                    {
                        "id_predio": predio_row.id_predio,
                        "id_tipologia": tipologia_row.id_tipologia,
                        "anio_construccion": anio_construccion,
                        "superficie_construida": superficie_construida,
                        "numero_bloques": numero_bloques,
                        "es_propiedad_horizontal": es_propiedad_horizontal,
                    },
                )

            total_insertadas += 1

        if dry_run:
            conn.rollback()
        else:
            conn.commit()

    if errores:
        console.print(f"[yellow]  Validaciones con observaciones: {len(errores)}[/yellow]")
        for error in errores[:20]:
            console.print(f"[yellow]    - {error}[/yellow]")
        if len(errores) > 20:
            console.print("[yellow]    ... se omitieron errores adicionales[/yellow]")

    if dry_run:
        if filas_omitidas:
            console.print(
                f"[cyan]  Filas omitidas por estar vacias: {filas_omitidas}[/cyan]"
            )
        console.print(
            f"[cyan]  Dry-run completo: {total_insertadas} filas listas para insertar.[/cyan]"
        )
    else:
        console.print(
            f"[green]  Construcciones insertadas: {total_insertadas}. "
            f"Predios reemplazados: {predios_reemplazados}[/green]"
        )
        if filas_omitidas:
            console.print(
                f"[cyan]  Filas omitidas por estar vacias: {filas_omitidas}[/cyan]"
            )


# =====================================================
# COMANDO: limpiar
# =====================================================

@app.command()
def limpiar():
    """Elimina tablas staging."""
    if not typer.confirm("¿Eliminar todas las tablas staging?"):
        raise typer.Abort()

    with sync_engine.begin() as conn:
        for config in CAPAS.values():
            tabla = config["tabla_staging"]
            conn.execute(text(f"DROP TABLE IF EXISTS {tabla} CASCADE"))
            console.print(f"  ✓ {tabla} eliminada")

    console.print("\n[green]Staging limpiado[/green]\n")


if __name__ == "__main__":
    app()

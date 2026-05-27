ALTER TABLE normative_version
    ADD COLUMN IF NOT EXISTS resolucion_municipal VARCHAR(160),
    ADD COLUMN IF NOT EXISTS detalle_normativo TEXT;

ALTER TABLE appraisal_case
    ADD COLUMN IF NOT EXISTS appraisal_mode VARCHAR(20) NOT NULL DEFAULT 'FISCAL';

ALTER TABLE appraisal_building_block
    ADD COLUMN IF NOT EXISTS estado_conservacion VARCHAR(60),
    ADD COLUMN IF NOT EXISTS numero_pisos INTEGER,
    ADD COLUMN IF NOT EXISTS uso_construccion VARCHAR(80),
    ADD COLUMN IF NOT EXISTS material_estructural VARCHAR(80),
    ADD COLUMN IF NOT EXISTS tipo_cubierta VARCHAR(80),
    ADD COLUMN IF NOT EXISTS remodelaciones VARCHAR(80),
    ADD COLUMN IF NOT EXISTS factor_estado NUMERIC(10,4) NOT NULL DEFAULT 1.0000,
    ADD COLUMN IF NOT EXISTS factor_material NUMERIC(10,4) NOT NULL DEFAULT 1.0000,
    ADD COLUMN IF NOT EXISTS factor_cubierta NUMERIC(10,4) NOT NULL DEFAULT 1.0000,
    ADD COLUMN IF NOT EXISTS factor_remodelacion NUMERIC(10,4) NOT NULL DEFAULT 1.0000,
    ADD COLUMN IF NOT EXISTS valor_tipologia_ajustado_m2 NUMERIC(14,4);

CREATE TABLE IF NOT EXISTS tabla_matriz_calidad_material (
    matriz_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    normative_version_id UUID NOT NULL REFERENCES normative_version(normative_version_id),
    calidad VARCHAR(30) NOT NULL,
    material_estructural VARCHAR(80) NOT NULL DEFAULT 'GENERICA',
    tipo_cubierta VARCHAR(80) NOT NULL DEFAULT 'GENERICA',
    estado_conservacion VARCHAR(60) NOT NULL DEFAULT 'BUENO',
    remodelacion_codigo VARCHAR(10) NOT NULL DEFAULT 'NO',
    factor_material NUMERIC(10,4) NOT NULL DEFAULT 1.0000,
    factor_cubierta NUMERIC(10,4) NOT NULL DEFAULT 1.0000,
    factor_estado NUMERIC(10,4) NOT NULL DEFAULT 1.0000,
    factor_remodelacion NUMERIC(10,4) NOT NULL DEFAULT 1.0000,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (
        normative_version_id,
        calidad,
        material_estructural,
        tipo_cubierta,
        estado_conservacion,
        remodelacion_codigo
    )
);

INSERT INTO tabla_matriz_calidad_material (
    normative_version_id,
    calidad,
    material_estructural,
    tipo_cubierta,
    estado_conservacion,
    remodelacion_codigo,
    factor_material,
    factor_cubierta,
    factor_estado,
    factor_remodelacion,
    activo
)
SELECT
    nv.normative_version_id,
    calidad_base.calidad,
    'GENERICA',
    'GENERICA',
    estado_base.estado_conservacion,
    remodelacion_base.remodelacion_codigo,
    1.0000,
    1.0000,
    estado_base.factor_estado,
    remodelacion_base.factor_remodelacion,
    TRUE
FROM normative_version nv
CROSS JOIN (
    SELECT DISTINCT calidad
    FROM tabla_tipologias_constructivas
) AS calidad_base
CROSS JOIN (
    VALUES
        ('EXCELENTE', 1.0500),
        ('BUENO', 1.0000),
        ('REGULAR', 0.9300),
        ('MALO', 0.8500)
) AS estado_base(estado_conservacion, factor_estado)
CROSS JOIN (
    VALUES
        ('NO', 1.0000),
        ('SI', 1.0400)
) AS remodelacion_base(remodelacion_codigo, factor_remodelacion)
WHERE NOT EXISTS (
    SELECT 1
    FROM tabla_matriz_calidad_material dst
    WHERE dst.normative_version_id = nv.normative_version_id
      AND dst.calidad = calidad_base.calidad
      AND dst.material_estructural = 'GENERICA'
      AND dst.tipo_cubierta = 'GENERICA'
      AND dst.estado_conservacion = estado_base.estado_conservacion
      AND dst.remodelacion_codigo = remodelacion_base.remodelacion_codigo
);

CREATE MATERIALIZED VIEW IF NOT EXISTS mv_predio_superficie_diferencias AS
SELECT
    p.id_predio AS predio_id,
    p.codigo_catastral,
    p.superficie_mensura::NUMERIC(14,2) AS superficie_gis,
    p.superficie_titulo::NUMERIC(14,2) AS superficie_legal,
    ABS(COALESCE(p.superficie_mensura, 0) - COALESCE(p.superficie_titulo, 0))::NUMERIC(14,2) AS diferencia,
    CASE
        WHEN p.superficie_titulo IS NULL OR p.superficie_titulo = 0 THEN NULL
        ELSE ROUND((ABS(p.superficie_mensura - p.superficie_titulo) / p.superficie_titulo) * 100.0, 2)
    END AS porcentaje_diferencia,
    CASE
        WHEN p.superficie_titulo IS NULL OR p.superficie_titulo = 0 THEN 'SIN_BASE_LEGAL'
        WHEN ABS(p.superficie_mensura - p.superficie_titulo) / p.superficie_titulo < 0.05 THEN 'OK'
        WHEN ABS(p.superficie_mensura - p.superficie_titulo) / p.superficie_titulo <= 0.15 THEN 'REVISAR'
        ELSE 'CRITICO'
    END AS clasificacion,
    CASE
        WHEN p.superficie_titulo IS NULL OR p.superficie_titulo = 0 THEN 'gris'
        WHEN ABS(p.superficie_mensura - p.superficie_titulo) / p.superficie_titulo < 0.05 THEN 'verde'
        WHEN ABS(p.superficie_mensura - p.superficie_titulo) / p.superficie_titulo <= 0.15 THEN 'amarillo'
        ELSE 'rojo'
    END AS color,
    p.geom
FROM predio p
WITH NO DATA;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_predio_superficie_diferencias_predio
    ON mv_predio_superficie_diferencias(predio_id);

CREATE INDEX IF NOT EXISTS idx_mv_predio_superficie_diferencias_clasificacion
    ON mv_predio_superficie_diferencias(clasificacion);

CREATE INDEX IF NOT EXISTS idx_mv_predio_superficie_diferencias_codigo
    ON mv_predio_superficie_diferencias(codigo_catastral);

CREATE INDEX IF NOT EXISTS idx_mv_predio_superficie_diferencias_geom
    ON mv_predio_superficie_diferencias
    USING GIST (geom);

REFRESH MATERIALIZED VIEW mv_predio_superficie_diferencias;

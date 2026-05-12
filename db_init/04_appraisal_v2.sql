CREATE TABLE IF NOT EXISTS normative_version (
    normative_version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    gestion_anio INTEGER NOT NULL,
    nombre VARCHAR(120) NOT NULL,
    version_codigo VARCHAR(30) NOT NULL,
    vigente_desde DATE NOT NULL,
    vigente_hasta DATE,
    estado VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (gestion_anio, version_codigo)
);

CREATE TABLE IF NOT EXISTS tabla_zonas_valor (
    tabla_zona_valor_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    normative_version_id UUID NOT NULL REFERENCES normative_version(normative_version_id),
    zona_tributaria_codigo VARCHAR(120) NOT NULL,
    material_via_codigo VARCHAR(50) NOT NULL,
    valor_m2 NUMERIC(14,2) NOT NULL,
    vigencia_desde DATE NOT NULL,
    vigencia_hasta DATE,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (normative_version_id, zona_tributaria_codigo, material_via_codigo)
);

CREATE TABLE IF NOT EXISTS tabla_factores_pendiente (
    factor_pendiente_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    normative_version_id UUID NOT NULL REFERENCES normative_version(normative_version_id),
    rango_min NUMERIC(8,2) NOT NULL,
    rango_max NUMERIC(8,2) NOT NULL,
    factor NUMERIC(8,4) NOT NULL,
    activo BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS tabla_factores_servicios (
    factor_servicio_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    normative_version_id UUID NOT NULL REFERENCES normative_version(normative_version_id),
    servicio_codigo VARCHAR(30) NOT NULL,
    puntaje NUMERIC(8,4) NOT NULL,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (normative_version_id, servicio_codigo)
);

CREATE TABLE IF NOT EXISTS tabla_tipologias_constructivas (
    tipologia_constructiva_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    normative_version_id UUID NOT NULL REFERENCES normative_version(normative_version_id),
    calidad VARCHAR(30) NOT NULL,
    categoria VARCHAR(30) NOT NULL,
    estructura VARCHAR(50),
    valor_m2 NUMERIC(14,2) NOT NULL,
    tipologia_origen_codigo VARCHAR(10),
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (normative_version_id, calidad, categoria)
);

CREATE TABLE IF NOT EXISTS tabla_depreciacion_antiguedad (
    depreciacion_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    normative_version_id UUID NOT NULL REFERENCES normative_version(normative_version_id),
    edad_min INTEGER NOT NULL,
    edad_max INTEGER NOT NULL,
    factor NUMERIC(8,4) NOT NULL
);

CREATE TABLE IF NOT EXISTS tabla_alicuota_impuesto (
    alicuota_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    normative_version_id UUID NOT NULL REFERENCES normative_version(normative_version_id),
    codigo VARCHAR(30) NOT NULL DEFAULT 'PREDIAL_BASE',
    alicuota NUMERIC(10,6) NOT NULL,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (normative_version_id, codigo)
);

CREATE TABLE IF NOT EXISTS appraisal_case (
    appraisal_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    predio_id UUID NOT NULL REFERENCES predio(id_predio),
    gestion_id UUID REFERENCES gestion(id_gestion),
    normative_version_id UUID NOT NULL REFERENCES normative_version(normative_version_id),
    status VARCHAR(30) NOT NULL,
    initiated_by UUID NOT NULL REFERENCES usuario(id_usuario),
    reviewed_by UUID REFERENCES usuario(id_usuario),
    calculation_mode VARCHAR(20) NOT NULL DEFAULT 'INDIVIDUAL',
    superficie_gis NUMERIC(14,2),
    superficie_legal NUMERIC(14,2),
    superficie_manual NUMERIC(14,2),
    superficie_calculo NUMERIC(14,2) NOT NULL,
    superficie_override_reason TEXT,
    observaciones TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMP WITH TIME ZONE,
    finalized_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS appraisal_result (
    appraisal_id UUID PRIMARY KEY REFERENCES appraisal_case(appraisal_id) ON DELETE CASCADE,
    valor_terreno NUMERIC(16,2) NOT NULL,
    valor_construccion NUMERIC(16,2) NOT NULL,
    base_imponible NUMERIC(16,2) NOT NULL,
    impuesto_estimado NUMERIC(16,2) NOT NULL,
    alicuota NUMERIC(10,6) NOT NULL,
    formula_version VARCHAR(30) NOT NULL,
    calculated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS appraisal_building_block (
    block_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    appraisal_id UUID NOT NULL REFERENCES appraisal_case(appraisal_id) ON DELETE CASCADE,
    orden INTEGER NOT NULL,
    superficie NUMERIC(14,2) NOT NULL,
    calidad_constructiva VARCHAR(30) NOT NULL,
    anio_construccion INTEGER NOT NULL,
    tipologia_constructiva_id UUID REFERENCES tabla_tipologias_constructivas(tipologia_constructiva_id),
    valor_tipologia_m2 NUMERIC(14,2) NOT NULL,
    factor_antiguedad NUMERIC(8,4) NOT NULL,
    valor_bloque NUMERIC(16,2) NOT NULL
);

CREATE TABLE IF NOT EXISTS predio_superficie_override (
    override_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    predio_id UUID NOT NULL REFERENCES predio(id_predio) ON DELETE CASCADE,
    superficie_gis NUMERIC(14,2),
    superficie_legal NUMERIC(14,2),
    superficie_manual NUMERIC(14,2) NOT NULL,
    motivo TEXT NOT NULL,
    usuario_id UUID NOT NULL REFERENCES usuario(id_usuario),
    vigente BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS appraisal_trace (
    trace_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    appraisal_id UUID NOT NULL REFERENCES appraisal_case(appraisal_id) ON DELETE CASCADE,
    predio_id UUID NOT NULL REFERENCES predio(id_predio),
    gestion_anio INTEGER NOT NULL,
    normative_version VARCHAR(30) NOT NULL,
    input_payload JSONB NOT NULL,
    factores_aplicados JSONB NOT NULL,
    contexto_espacial JSONB NOT NULL,
    tablas_utilizadas JSONB NOT NULL,
    formulas_aplicadas JSONB NOT NULL,
    overrides_manuales JSONB NOT NULL,
    geometries_used JSONB NOT NULL,
    generated_by UUID NOT NULL REFERENCES usuario(id_usuario),
    generated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_appraisal_case_predio ON appraisal_case(predio_id);
CREATE INDEX IF NOT EXISTS idx_appraisal_trace_predio ON appraisal_trace(predio_id);
CREATE INDEX IF NOT EXISTS idx_predio_superficie_override_predio ON predio_superficie_override(predio_id, vigente);

INSERT INTO normative_version (gestion_anio, nombre, version_codigo, vigente_desde, vigente_hasta, estado)
SELECT g.anio, 'Normativa GAMLP ' || g.anio, 'v1', make_date(g.anio, 1, 1), make_date(g.anio, 12, 31), 'ACTIVE'
FROM gestion g
WHERE g.anio IN (2025, 2026, 2027)
  AND NOT EXISTS (
      SELECT 1
      FROM normative_version nv
      WHERE nv.gestion_anio = g.anio
        AND nv.version_codigo = 'v1'
  );

INSERT INTO tabla_factores_servicios (normative_version_id, servicio_codigo, puntaje, activo)
SELECT
    nv.normative_version_id,
    s.nombre,
    0.20,
    TRUE
FROM normative_version nv
CROSS JOIN (VALUES ('AGUA POTABLE'), ('ALCANTARILLADO'), ('ENERGIA ELECTRICA'), ('TELEFONO')) AS s(nombre)
WHERE NOT EXISTS (
    SELECT 1
    FROM tabla_factores_servicios tfs
    WHERE tfs.normative_version_id = nv.normative_version_id
      AND tfs.servicio_codigo = s.nombre
);

INSERT INTO tabla_alicuota_impuesto (normative_version_id, codigo, alicuota, activo)
SELECT nv.normative_version_id, 'PREDIAL_BASE', 0.0035, TRUE
FROM normative_version nv
WHERE NOT EXISTS (
    SELECT 1
    FROM tabla_alicuota_impuesto tai
    WHERE tai.normative_version_id = nv.normative_version_id
      AND tai.codigo = 'PREDIAL_BASE'
);

INSERT INTO tabla_factores_pendiente (normative_version_id, rango_min, rango_max, factor, activo)
SELECT
    nv.normative_version_id,
    fp.angulo_minimo,
    fp.angulo_maximo,
    fp.factor_ajuste,
    TRUE
FROM normative_version nv
JOIN factor_pendiente fp ON TRUE
LEFT JOIN tabla_factores_pendiente dst
    ON dst.normative_version_id = nv.normative_version_id
   AND dst.rango_min = fp.angulo_minimo
   AND dst.rango_max = fp.angulo_maximo
WHERE dst.factor_pendiente_id IS NULL;

INSERT INTO tabla_depreciacion_antiguedad (normative_version_id, edad_min, edad_max, factor)
SELECT
    nv.normative_version_id,
    fd.antiguedad_minima,
    fd.antiguedad_maxima,
    fd.factor_ajuste
FROM normative_version nv
JOIN factor_depreciacion fd ON TRUE
LEFT JOIN tabla_depreciacion_antiguedad dst
    ON dst.normative_version_id = nv.normative_version_id
   AND dst.edad_min = fd.antiguedad_minima
   AND dst.edad_max = fd.antiguedad_maxima
WHERE dst.depreciacion_id IS NULL;

INSERT INTO tabla_tipologias_constructivas (
    normative_version_id,
    calidad,
    categoria,
    estructura,
    valor_m2,
    tipologia_origen_codigo,
    activo
)
SELECT
    nv.normative_version_id,
    CASE
        WHEN t.codigo IN ('30', '40') THEN 'LUJO'
        WHEN t.codigo IN ('31', '41') THEN 'ALTA'
        WHEN t.codigo IN ('32', '42') THEN 'MEDIA'
        WHEN t.codigo IN ('33', '43') THEN 'BASICA'
        WHEN t.codigo = '34' THEN 'SOCIAL'
        ELSE 'MARGINAL'
    END AS calidad,
    CASE
        WHEN t.codigo BETWEEN '40' AND '49' THEN 'PROPIEDAD_HORIZONTAL'
        ELSE 'PREDIO'
    END AS categoria,
    NULL,
    t.valor_por_metro_cuadrado,
    t.codigo,
    TRUE
FROM normative_version nv
JOIN tipologia t ON TRUE
LEFT JOIN tabla_tipologias_constructivas dst
    ON dst.normative_version_id = nv.normative_version_id
   AND dst.tipologia_origen_codigo = t.codigo
WHERE dst.tipologia_constructiva_id IS NULL;

INSERT INTO tabla_zonas_valor (
    normative_version_id,
    zona_tributaria_codigo,
    material_via_codigo,
    valor_m2,
    vigencia_desde,
    vigencia_hasta,
    activo
)
SELECT
    nv.normative_version_id,
    COALESCE(zt.codigo, zv.nombre),
    mv.nombre,
    vs.valor_por_metro_cuadrado,
    nv.vigente_desde,
    nv.vigente_hasta,
    TRUE
FROM normative_version nv
JOIN valor_suelo vs ON TRUE
JOIN zona_valor zv ON zv.id_zona_valor = vs.id_zona_valor
LEFT JOIN zona_tributaria zt ON zt.id_zona_tributaria = zv.id_zona_tributaria
JOIN material_via mv ON mv.id_material_via = vs.id_material_via
LEFT JOIN tabla_zonas_valor dst
    ON dst.normative_version_id = nv.normative_version_id
   AND dst.zona_tributaria_codigo = COALESCE(zt.codigo, zv.nombre)
   AND dst.material_via_codigo = mv.nombre
WHERE dst.tabla_zona_valor_id IS NULL;

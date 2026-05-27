CREATE TABLE IF NOT EXISTS predio_manual_data (
    manual_data_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    predio_id UUID NOT NULL REFERENCES predio(id_predio) ON DELETE CASCADE,
    vigente BOOLEAN NOT NULL DEFAULT TRUE,
    usuario_id UUID NOT NULL REFERENCES usuario(id_usuario),
    motivo TEXT NOT NULL,
    es_temporal BOOLEAN NOT NULL DEFAULT FALSE,
    superficie_manual NUMERIC(14,2),
    frente NUMERIC(14,2),
    fondo NUMERIC(14,2),
    forma_lote VARCHAR(50),
    uso_suelo VARCHAR(80),
    tipo_via VARCHAR(80),
    acceso_vehicular BOOLEAN,
    pendiente_manual NUMERIC(10,4),
    zona_homogenea_manual VARCHAR(80),
    zona_tributaria_manual VARCHAR(80),
    coordenadas_manual VARCHAR(120),
    distrito_manual VARCHAR(120),
    macrodistrito_manual VARCHAR(120),
    agua BOOLEAN,
    alcantarillado BOOLEAN,
    electricidad BOOLEAN,
    telefono BOOLEAN,
    gas BOOLEAN,
    internet BOOLEAN,
    alumbrado_publico BOOLEAN,
    riesgo_territorial_manual VARCHAR(80),
    tipo_riesgo VARCHAR(120),
    afectacion_riesgo VARCHAR(30),
    valor_unitario_manual NUMERIC(14,2),
    usar_valor_unitario_manual BOOLEAN NOT NULL DEFAULT FALSE,
    coeficiente_manual NUMERIC(10,4),
    usar_coeficiente_manual BOOLEAN NOT NULL DEFAULT FALSE,
    depreciacion_manual NUMERIC(10,4),
    usar_depreciacion_manual BOOLEAN NOT NULL DEFAULT FALSE,
    ajuste_comercial NUMERIC(10,4),
    clasificacion_especial VARCHAR(120),
    observacion_tecnica TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_predio_manual_data_predio_vigente
    ON predio_manual_data(predio_id, vigente, created_at DESC);

CREATE TABLE IF NOT EXISTS avaluo_auditoria (
    auditoria_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    appraisal_id UUID REFERENCES appraisal_case(appraisal_id) ON DELETE CASCADE,
    predio_id UUID NOT NULL REFERENCES predio(id_predio) ON DELETE CASCADE,
    usuario_id UUID NOT NULL REFERENCES usuario(id_usuario),
    campo VARCHAR(80) NOT NULL,
    valor_anterior TEXT,
    valor_nuevo TEXT,
    fuente_anterior VARCHAR(40),
    fuente_nueva VARCHAR(40) NOT NULL,
    motivo TEXT,
    es_temporal BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_avaluo_auditoria_predio
    ON avaluo_auditoria(predio_id, created_at DESC);

CREATE TABLE IF NOT EXISTS tabla_factores_riesgo (
    factor_riesgo_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    normative_version_id UUID NOT NULL REFERENCES normative_version(normative_version_id),
    riesgo_codigo INTEGER NOT NULL,
    riesgo_grado VARCHAR(80),
    factor NUMERIC(10,4) NOT NULL,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (normative_version_id, riesgo_codigo)
);

CREATE TABLE IF NOT EXISTS tabla_coeficientes_terreno (
    coeficiente_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    normative_version_id UUID NOT NULL REFERENCES normative_version(normative_version_id),
    coefficient_type VARCHAR(40) NOT NULL,
    coefficient_code VARCHAR(80) NOT NULL,
    factor NUMERIC(10,4) NOT NULL,
    descripcion VARCHAR(160),
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (normative_version_id, coefficient_type, coefficient_code)
);

INSERT INTO tabla_factores_riesgo (normative_version_id, riesgo_codigo, riesgo_grado, factor, activo)
SELECT nv.normative_version_id, src.riesgo_codigo, src.riesgo_grado, src.factor, TRUE
FROM normative_version nv
CROSS JOIN (
    VALUES
        (51, 'MUY BAJO', 1.0000),
        (102, 'BAJO', 0.9700),
        (153, 'MODERADO', 0.9400),
        (204, 'ALTO', 0.9000),
        (255, 'MUY ALTO', 0.8500)
) AS src(riesgo_codigo, riesgo_grado, factor)
WHERE NOT EXISTS (
    SELECT 1
    FROM tabla_factores_riesgo dst
    WHERE dst.normative_version_id = nv.normative_version_id
      AND dst.riesgo_codigo = src.riesgo_codigo
);

INSERT INTO tabla_coeficientes_terreno (normative_version_id, coefficient_type, coefficient_code, factor, descripcion, activo)
SELECT nv.normative_version_id, src.coefficient_type, src.coefficient_code, src.factor, src.descripcion, TRUE
FROM normative_version nv
CROSS JOIN (
    VALUES
        ('COMERCIAL', 'DEFAULT', 1.0000, 'Coeficiente comercial por defecto'),
        ('ESQUINA', 'NO', 1.0000, 'Predio no esquina'),
        ('ESQUINA', 'SI', 1.0500, 'Predio esquina'),
        ('AVENIDA', 'NO', 1.0000, 'Predio no sobre avenida'),
        ('AVENIDA', 'SI', 1.0800, 'Predio sobre avenida'),
        ('FORMA', 'REGULAR', 1.0000, 'Lote regular'),
        ('FORMA', 'IRREGULAR', 0.9500, 'Lote irregular'),
        ('USO', 'RESIDENCIAL', 1.0000, 'Uso residencial'),
        ('USO', 'COMERCIAL', 1.1200, 'Uso comercial'),
        ('USO', 'MIXTO', 1.0600, 'Uso mixto')
) AS src(coefficient_type, coefficient_code, factor, descripcion)
WHERE NOT EXISTS (
    SELECT 1
    FROM tabla_coeficientes_terreno dst
    WHERE dst.normative_version_id = nv.normative_version_id
      AND dst.coefficient_type = src.coefficient_type
      AND dst.coefficient_code = src.coefficient_code
);

-- La RA GAMLP/ATM No. 14/2023 es una fuente municipal verificable para
-- formulas PH e IMPBI. Su vigencia para gestiones posteriores debe confirmarse.
ALTER TABLE appraisal_case
    ADD COLUMN IF NOT EXISTS regimen_inmueble VARCHAR(30) NOT NULL DEFAULT 'VIVIENDA_FAMILIAR';

ALTER TABLE appraisal_building_block
    ADD COLUMN IF NOT EXISTS factor_ubicacion_ph NUMERIC(10,4) NOT NULL DEFAULT 1.0000;

CREATE TABLE IF NOT EXISTS tabla_factores_ubicacion_ph (
    factor_ubicacion_ph_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    normative_version_id UUID NOT NULL REFERENCES normative_version(normative_version_id),
    zona_tributaria_codigo VARCHAR(120) NOT NULL,
    factor NUMERIC(10,4) NOT NULL,
    fuente_documental VARCHAR(180) NOT NULL,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (normative_version_id, zona_tributaria_codigo)
);

CREATE TABLE IF NOT EXISTS tabla_escala_impbi (
    escala_impbi_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    normative_version_id UUID NOT NULL REFERENCES normative_version(normative_version_id),
    tramo_codigo VARCHAR(30) NOT NULL,
    limite_inferior NUMERIC(16,2) NOT NULL,
    limite_superior NUMERIC(16,2),
    cuota_fija NUMERIC(16,2) NOT NULL,
    alicuota_excedente NUMERIC(12,8) NOT NULL,
    fuente_gestion_anio INTEGER NOT NULL,
    fuente_documental VARCHAR(180) NOT NULL,
    vigente_confirmada BOOLEAN NOT NULL DEFAULT FALSE,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (normative_version_id, tramo_codigo)
);

UPDATE normative_version
SET
    nombre = 'Parametros GAMLP contrastados con RA GAMLP/ATM No. 14/2023',
    resolucion_municipal = 'RA GAMLP/ATM No. 14/2023 (referencia oficial verificada)',
    detalle_normativo = (
        'Formulas, factores PH y escala IMPBI contrastados con el Anexo A de la '
        'RA GAMLP/ATM No. 14/2023. Vigencia para la gestion calculada pendiente '
        'de confirmacion documental municipal.'
    )
WHERE estado = 'ACTIVE'
  AND gestion_anio IN (2025, 2026, 2027);

INSERT INTO tabla_factores_ubicacion_ph (
    normative_version_id, zona_tributaria_codigo, factor, fuente_documental, activo
)
SELECT
    nv.normative_version_id,
    seed.zona_tributaria_codigo,
    seed.factor,
    'RA GAMLP/ATM No. 14/2023 - Anexo A - Propiedad Horizontal',
    TRUE
FROM normative_version nv
CROSS JOIN (
    VALUES
        ('1-10', 1.6250),
        ('1-20-28', 1.5600),
        ('1-30-38', 1.5000),
        ('1-40-47', 1.4380),
        ('1-50-58', 1.3750),
        ('2-10-18', 1.3130),
        ('2-20-29', 1.2810),
        ('2-30-34', 1.2500),
        ('2-40-45', 1.2190),
        ('2-50-58', 1.1880),
        ('2-60-68', 1.1560),
        ('2-70-76', 1.1250),
        ('2-80-82', 1.0940),
        ('3-10-16', 1.0620),
        ('3-20-21', 1.0310),
        ('3-30-36', 1.0000)
) AS seed(zona_tributaria_codigo, factor)
WHERE nv.estado = 'ACTIVE'
  AND nv.gestion_anio IN (2025, 2026, 2027)
  AND NOT EXISTS (
      SELECT 1
      FROM tabla_factores_ubicacion_ph dst
      WHERE dst.normative_version_id = nv.normative_version_id
        AND dst.zona_tributaria_codigo = seed.zona_tributaria_codigo
  );

INSERT INTO tabla_escala_impbi (
    normative_version_id, tramo_codigo, limite_inferior, limite_superior,
    cuota_fija, alicuota_excedente, fuente_gestion_anio, fuente_documental,
    vigente_confirmada, activo
)
SELECT
    nv.normative_version_id,
    seed.tramo_codigo,
    seed.limite_inferior,
    seed.limite_superior,
    seed.cuota_fija,
    seed.alicuota_excedente,
    2023,
    'RA GAMLP/ATM No. 14/2023 - Anexo A - Escala IMPBI',
    FALSE,
    TRUE
FROM normative_version nv
CROSS JOIN (
    VALUES
        ('TRAMO_1', 0.00, 1399668.00, 0.00, 0.00115369),
        ('TRAMO_2', 1399668.00, 2799326.00, 1615.00, 0.00173054),
        ('TRAMO_3', 2799326.00, 5598672.00, 4037.00, 0.00230738),
        ('TRAMO_4', 5598672.00, NULL::NUMERIC, 10496.00, 0.00288423)
) AS seed(tramo_codigo, limite_inferior, limite_superior, cuota_fija, alicuota_excedente)
WHERE nv.estado = 'ACTIVE'
  AND nv.gestion_anio IN (2025, 2026, 2027)
  AND NOT EXISTS (
      SELECT 1
      FROM tabla_escala_impbi dst
      WHERE dst.normative_version_id = nv.normative_version_id
        AND dst.tramo_codigo = seed.tramo_codigo
  );

-- =====================================================
-- RESUMEN ESPACIAL POR PREDIO
-- =====================================================

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
);

CREATE INDEX IF NOT EXISTS idx_predio_contexto_pendiente
ON predio_contexto_espacial (pendiente_codigo);

CREATE INDEX IF NOT EXISTS idx_predio_contexto_riesgo
ON predio_contexto_espacial (riesgo_codigo);

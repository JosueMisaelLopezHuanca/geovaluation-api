-- Registro voluntario de consultas publicas para aprendizaje durante la beta.
-- El contacto queda separado del resultado catastral y solo se registra con autorizacion.
CREATE TABLE IF NOT EXISTS public_beta_consulta (
    beta_submission_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    predio_id UUID NOT NULL REFERENCES predio(id_predio),
    gestion_anio INTEGER NOT NULL,
    avaluo_tipo VARCHAR(20) NOT NULL,
    regimen_inmueble VARCHAR(30) NOT NULL DEFAULT 'VIVIENDA_FAMILIAR',
    base_imponible NUMERIC(16,2) NOT NULL,
    impuesto_estimado NUMERIC(16,2) NOT NULL,
    calculation_input JSONB NOT NULL,
    calculation_result JSONB NOT NULL,
    utilidad_resultado VARCHAR(20),
    comentario TEXT,
    consentimiento_version VARCHAR(30) NOT NULL,
    consentimiento_registro BOOLEAN NOT NULL CHECK (consentimiento_registro = TRUE),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS public_beta_contacto (
    beta_contacto_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    beta_submission_id UUID NOT NULL UNIQUE REFERENCES public_beta_consulta(beta_submission_id) ON DELETE CASCADE,
    nombre_contacto VARCHAR(120),
    correo_contacto VARCHAR(254),
    telefono_contacto VARCHAR(30),
    consentimiento_contacto BOOLEAN NOT NULL CHECK (consentimiento_contacto = TRUE),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_public_beta_consulta_created_at
    ON public_beta_consulta(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_public_beta_consulta_predio
    ON public_beta_consulta(predio_id);

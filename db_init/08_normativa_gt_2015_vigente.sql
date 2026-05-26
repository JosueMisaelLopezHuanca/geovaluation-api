-- La tabla Catastro.xlsx entregada corresponde a la Gestion Tributaria 2015
-- y permanece vigente para los calculos actuales del proyecto.
UPDATE normative_version
SET
    nombre = 'Avaluo Catastral GAMLP - Gestion Tributaria 2015 Vigente',
    detalle_normativo = (
        'Valores unitarios, servicios, pendiente, tipologias y antiguedad '
        'provenientes de Catastro.xlsx, Gestion Tributaria 2015, vigente para el proyecto.'
    )
WHERE estado = 'ACTIVE'
  AND gestion_anio IN (2025, 2026, 2027);

INSERT INTO tabla_factores_servicios (normative_version_id, servicio_codigo, puntaje, activo)
SELECT
    nv.normative_version_id,
    'MINIMO',
    0.20,
    TRUE
FROM normative_version nv
WHERE nv.estado = 'ACTIVE'
  AND nv.gestion_anio IN (2025, 2026, 2027)
  AND NOT EXISTS (
      SELECT 1
      FROM tabla_factores_servicios tfs
      WHERE tfs.normative_version_id = nv.normative_version_id
        AND tfs.servicio_codigo = 'MINIMO'
  );

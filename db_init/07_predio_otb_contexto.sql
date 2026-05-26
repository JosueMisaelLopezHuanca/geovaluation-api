-- Cache territorial para acelerar busqueda de predios por OTB.
-- Se calcula con el punto interior del predio contra la capa staging_otbs.

CREATE TABLE IF NOT EXISTS predio_otb_contexto (
    predio_id UUID PRIMARY KEY REFERENCES predio(id_predio) ON DELETE CASCADE,
    otb_id BIGINT,
    otb_nombre TEXT NOT NULL,
    metodo TEXT NOT NULL DEFAULT 'point_on_surface',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_predio_otb_contexto_nombre
ON predio_otb_contexto (otb_nombre);

CREATE INDEX IF NOT EXISTS idx_predio_otb_contexto_nombre_lower
ON predio_otb_contexto (LOWER(otb_nombre));

CREATE OR REPLACE FUNCTION refresh_predio_otb_contexto()
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    affected_rows INTEGER := 0;
BEGIN
    IF to_regclass('public.staging_otbs') IS NULL THEN
        RETURN 0;
    END IF;

    TRUNCATE TABLE predio_otb_contexto;

    EXECUTE $sql$
        INSERT INTO predio_otb_contexto (
            predio_id,
            otb_id,
            otb_nombre,
            metodo,
            created_at,
            updated_at
        )
        SELECT
            p.id_predio,
            otb.id,
            NULLIF(TRIM(otb."NOM_OTB"), '') AS otb_nombre,
            'point_on_surface' AS metodo,
            now(),
            now()
        FROM predio p
        CROSS JOIN LATERAL (
            SELECT ST_PointOnSurface(p.geom) AS geom
        ) point_ref
        JOIN LATERAL (
            SELECT o.id, o."NOM_OTB"
            FROM staging_otbs o
            WHERE NULLIF(TRIM(o."NOM_OTB"), '') IS NOT NULL
              AND o.geometry && point_ref.geom
              AND ST_Intersects(o.geometry, point_ref.geom)
            ORDER BY NULLIF(TRIM(o."NOM_OTB"), '')
            LIMIT 1
        ) otb ON TRUE
    $sql$;

    GET DIAGNOSTICS affected_rows = ROW_COUNT;
    RETURN affected_rows;
END;
$$;

SELECT refresh_predio_otb_contexto();

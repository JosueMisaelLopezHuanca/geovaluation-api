-- =====================================================
-- SEMILLA MINIMA OPERATIVA - SISTEMA CATASTRAL
-- Base normativa inicial: gestion tributaria 2015
-- =====================================================

BEGIN;

-- -----------------------------------------------------
-- 1. USUARIO OPERATIVO MINIMO
-- -----------------------------------------------------

INSERT INTO persona (
    nombres,
    apellido_paterno,
    apellido_materno,
    ci,
    expedido_en,
    email,
    estado
)
SELECT
    'ADMIN',
    'CATASTRO',
    'SISTEMA',
    'CATASTRO-ADMIN',
    'LP',
    'admin@catastro.local',
    'ACTIVO'
WHERE NOT EXISTS (
    SELECT 1
    FROM persona
    WHERE ci = 'CATASTRO-ADMIN'
);

INSERT INTO usuario (
    id_persona,
    nombre_usuario,
    contrasena_hash,
    activo
)
SELECT
    p.id_persona,
    'admin',
    'seed-admin-sin-login',
    TRUE
FROM persona p
WHERE p.ci = 'CATASTRO-ADMIN'
  AND NOT EXISTS (
      SELECT 1
      FROM usuario u
      WHERE u.nombre_usuario = 'admin'
  );

INSERT INTO rol (nombre, descripcion)
SELECT
    'ADMINISTRADOR',
    'Rol operativo inicial para pruebas del modulo de avaluos'
WHERE NOT EXISTS (
    SELECT 1
    FROM rol
    WHERE nombre = 'ADMINISTRADOR'
);

INSERT INTO usuario_rol (id_usuario, id_rol)
SELECT
    u.id_usuario,
    r.id_rol
FROM usuario u
JOIN rol r ON r.nombre = 'ADMINISTRADOR'
WHERE u.nombre_usuario = 'admin'
  AND NOT EXISTS (
      SELECT 1
      FROM usuario_rol ur
      WHERE ur.id_usuario = u.id_usuario
        AND ur.id_rol = r.id_rol
  );

-- -----------------------------------------------------
-- 2. GESTIONES OPERATIVAS
-- -----------------------------------------------------

INSERT INTO gestion (anio, descripcion, estado)
SELECT *
FROM (
    VALUES
        (2015, 'Gestion tributaria 2015', 'CERRADA'),
        (2024, 'Gestion tributaria 2024', 'CERRADA'),
        (2025, 'Gestion tributaria 2025', 'CERRADA'),
        (2026, 'Gestion tributaria 2026', 'ABIERTA')
) AS g(anio, descripcion, estado)
WHERE NOT EXISTS (
    SELECT 1
    FROM gestion x
    WHERE x.anio = g.anio
);

-- -----------------------------------------------------
-- 3. ESQUEMA DE VALUACION 2015
-- -----------------------------------------------------

INSERT INTO esquema_valuacion (
    nombre,
    descripcion,
    fecha_inicio,
    fecha_fin
)
SELECT
    'LPZ 2015',
    'Tabla base 2015 para avaluo catastral urbano de La Paz',
    DATE '2015-01-01',
    NULL
WHERE NOT EXISTS (
    SELECT 1
    FROM esquema_valuacion
    WHERE nombre = 'LPZ 2015'
      AND fecha_inicio = DATE '2015-01-01'
);

-- -----------------------------------------------------
-- 4. CATALOGOS MAESTROS
-- -----------------------------------------------------

INSERT INTO material_via (nombre, orden)
SELECT *
FROM (
    VALUES
        ('ASFALTO', 20),
        ('ADOQUIN', 21),
        ('CEMENTO', 22),
        ('LOSETA', 23),
        ('PIEDRA', 24),
        ('RIPIO', 25),
        ('TIERRA', 26)
) AS v(nombre, orden)
WHERE NOT EXISTS (
    SELECT 1
    FROM material_via mv
    WHERE mv.nombre = v.nombre
);

INSERT INTO servicio (nombre, factor_incremento)
SELECT *
FROM (
    VALUES
        ('ENERGIA ELECTRICA', 0.20),
        ('AGUA POTABLE', 0.20),
        ('ALCANTARILLADO', 0.20),
        ('TELEFONO', 0.20)
) AS v(nombre, factor_incremento)
WHERE NOT EXISTS (
    SELECT 1
    FROM servicio s
    WHERE s.nombre = v.nombre
);

INSERT INTO tipo_conexion (nombre)
SELECT *
FROM (
    VALUES
        ('DIRECTA'),
        ('INDIRECTA'),
        ('SIN_DATO')
) AS v(nombre)
WHERE NOT EXISTS (
    SELECT 1
    FROM tipo_conexion tc
    WHERE tc.nombre = v.nombre
);

INSERT INTO tipo_tipologia (nombre, descripcion)
SELECT *
FROM (
    VALUES
        ('VIVIENDA_UNIFAMILIAR', 'Tipologias para vivienda unifamiliar'),
        ('PROPIEDAD_HORIZONTAL', 'Tipologias para propiedad horizontal')
) AS v(nombre, descripcion)
WHERE NOT EXISTS (
    SELECT 1
    FROM tipo_tipologia tt
    WHERE tt.nombre = v.nombre
);

-- -----------------------------------------------------
-- 5. TABLA DE ZONAS TRIBUTARIAS 2015
-- -----------------------------------------------------

INSERT INTO zona_tributaria (codigo, descripcion)
SELECT *
FROM (
    VALUES
        ('1-10', 'Macro zona 1 subzona 10 a 10'),
        ('1-20-28', 'Macro zona 1 subzona 20 a 28'),
        ('1-30-38', 'Macro zona 1 subzona 30 a 38'),
        ('1-40-47', 'Macro zona 1 subzona 40 a 47'),
        ('1-50-58', 'Macro zona 1 subzona 50 a 58'),
        ('2-10-18', 'Macro zona 2 subzona 10 a 18'),
        ('2-20-29', 'Macro zona 2 subzona 20 a 29'),
        ('2-30-34', 'Macro zona 2 subzona 30 a 34'),
        ('2-40-45', 'Macro zona 2 subzona 40 a 45'),
        ('2-50-58', 'Macro zona 2 subzona 50 a 58'),
        ('2-60-68', 'Macro zona 2 subzona 60 a 68'),
        ('2-70-76', 'Macro zona 2 subzona 70 a 76'),
        ('2-80-82', 'Macro zona 2 subzona 80 a 82'),
        ('3-10-16', 'Macro zona 3 subzona 10 a 16'),
        ('3-20-21', 'Macro zona 3 subzona 20 a 21'),
        ('3-30-36', 'Macro zona 3 subzona 30 a 36')
) AS v(codigo, descripcion)
WHERE NOT EXISTS (
    SELECT 1
    FROM zona_tributaria zt
    WHERE zt.codigo = v.codigo
);

-- -----------------------------------------------------
-- 6. ZONAS DE VALOR 2015 - MUNICIPIO LA PAZ
-- -----------------------------------------------------

WITH municipio_lpz AS (
    SELECT id_municipio
    FROM municipio
    WHERE UPPER(nombre) = 'LA PAZ'
    ORDER BY id_municipio
    LIMIT 1
),
zonas(codigo, macro_zona, subzona_inicio, subzona_fin, nombre) AS (
    VALUES
        ('1-10', 1, 10, 10, 'Zona tributaria 1-10'),
        ('1-20-28', 1, 20, 28, 'Zona tributaria 1-20 a 1-28'),
        ('1-30-38', 1, 30, 38, 'Zona tributaria 1-30 a 1-38'),
        ('1-40-47', 1, 40, 47, 'Zona tributaria 1-40 a 1-47'),
        ('1-50-58', 1, 50, 58, 'Zona tributaria 1-50 a 1-58'),
        ('2-10-18', 2, 10, 18, 'Zona tributaria 2-10 a 2-18'),
        ('2-20-29', 2, 20, 29, 'Zona tributaria 2-20 a 2-29'),
        ('2-30-34', 2, 30, 34, 'Zona tributaria 2-30 a 2-34'),
        ('2-40-45', 2, 40, 45, 'Zona tributaria 2-40 a 2-45'),
        ('2-50-58', 2, 50, 58, 'Zona tributaria 2-50 a 2-58'),
        ('2-60-68', 2, 60, 68, 'Zona tributaria 2-60 a 2-68'),
        ('2-70-76', 2, 70, 76, 'Zona tributaria 2-70 a 2-76'),
        ('2-80-82', 2, 80, 82, 'Zona tributaria 2-80 a 2-82'),
        ('3-10-16', 3, 10, 16, 'Zona tributaria 3-10 a 3-16'),
        ('3-20-21', 3, 20, 21, 'Zona tributaria 3-20 a 3-21'),
        ('3-30-36', 3, 30, 36, 'Zona tributaria 3-30 a 3-36')
)
INSERT INTO zona_valor (
    id_municipio,
    id_zona_tributaria,
    macro_zona,
    subzona_inicio,
    subzona_fin,
    nombre,
    descripcion,
    vigencia_desde,
    vigencia_hasta
)
SELECT
    m.id_municipio,
    zt.id_zona_tributaria,
    z.macro_zona,
    z.subzona_inicio,
    z.subzona_fin,
    z.nombre,
    'Semilla inicial basada en tabla 2015',
    DATE '2015-01-01',
    NULL
FROM zonas z
JOIN zona_tributaria zt ON zt.codigo = z.codigo
CROSS JOIN municipio_lpz m
WHERE NOT EXISTS (
    SELECT 1
    FROM zona_valor zv
    WHERE zv.id_municipio = m.id_municipio
      AND zv.macro_zona = z.macro_zona
      AND zv.subzona_inicio = z.subzona_inicio
      AND zv.subzona_fin = z.subzona_fin
      AND zv.vigencia_desde = DATE '2015-01-01'
);

-- -----------------------------------------------------
-- 7. VALOR DE SUELO 2015
-- -----------------------------------------------------

WITH esquema AS (
    SELECT id_esquema
    FROM esquema_valuacion
    WHERE nombre = 'LPZ 2015'
    ORDER BY fecha_inicio DESC
    LIMIT 1
),
municipio_lpz AS (
    SELECT id_municipio
    FROM municipio
    WHERE UPPER(nombre) = 'LA PAZ'
    ORDER BY id_municipio
    LIMIT 1
),
valores(codigo_zona, material, valor_m2) AS (
    VALUES
        ('1-10', 'ASFALTO', 7712.00),
        ('1-10', 'ADOQUIN', 7308.00),
        ('1-10', 'CEMENTO', 6899.00),
        ('1-10', 'LOSETA', 6362.00),
        ('1-10', 'PIEDRA', 5682.00),
        ('1-10', 'RIPIO', 5549.00),
        ('1-10', 'TIERRA', 5279.00),

        ('1-20-28', 'ASFALTO', 6125.00),
        ('1-20-28', 'ADOQUIN', 5512.00),
        ('1-20-28', 'CEMENTO', 5051.00),
        ('1-20-28', 'LOSETA', 4651.00),
        ('1-20-28', 'PIEDRA', 4472.00),
        ('1-20-28', 'RIPIO', 4126.00),
        ('1-20-28', 'TIERRA', 3828.00),

        ('1-30-38', 'ASFALTO', 4447.00),
        ('1-30-38', 'ADOQUIN', 4005.00),
        ('1-30-38', 'CEMENTO', 3707.00),
        ('1-30-38', 'LOSETA', 3416.00),
        ('1-30-38', 'PIEDRA', 3261.00),
        ('1-30-38', 'RIPIO', 2964.00),
        ('1-30-38', 'TIERRA', 2521.00),

        ('1-40-47', 'ASFALTO', 3531.00),
        ('1-40-47', 'ADOQUIN', 3028.00),
        ('1-40-47', 'CEMENTO', 2591.00),
        ('1-40-47', 'LOSETA', 2503.00),
        ('1-40-47', 'PIEDRA', 2209.00),
        ('1-40-47', 'RIPIO', 2030.00),
        ('1-40-47', 'TIERRA', 1911.00),

        ('1-50-58', 'ASFALTO', 2879.00),
        ('1-50-58', 'ADOQUIN', 2542.00),
        ('1-50-58', 'CEMENTO', 2315.00),
        ('1-50-58', 'LOSETA', 2172.00),
        ('1-50-58', 'PIEDRA', 1975.00),
        ('1-50-58', 'RIPIO', 1750.00),
        ('1-50-58', 'TIERRA', 1666.00),

        ('2-10-18', 'ASFALTO', 2324.00),
        ('2-10-18', 'ADOQUIN', 2218.00),
        ('2-10-18', 'CEMENTO', 2075.00),
        ('2-10-18', 'LOSETA', 1881.00),
        ('2-10-18', 'PIEDRA', 1772.00),
        ('2-10-18', 'RIPIO', 1608.00),
        ('2-10-18', 'TIERRA', 1493.00),

        ('2-20-29', 'ASFALTO', 1990.00),
        ('2-20-29', 'ADOQUIN', 1823.00),
        ('2-20-29', 'CEMENTO', 1720.00),
        ('2-20-29', 'LOSETA', 1556.00),
        ('2-20-29', 'PIEDRA', 1441.00),
        ('2-20-29', 'RIPIO', 1389.00),
        ('2-20-29', 'TIERRA', 1326.00),

        ('2-30-34', 'ASFALTO', 1823.00),
        ('2-30-34', 'ADOQUIN', 1662.00),
        ('2-30-34', 'CEMENTO', 1556.00),
        ('2-30-34', 'LOSETA', 1389.00),
        ('2-30-34', 'PIEDRA', 1326.00),
        ('2-30-34', 'RIPIO', 1217.00),
        ('2-30-34', 'TIERRA', 1165.00),

        ('2-40-45', 'ASFALTO', 1772.00),
        ('2-40-45', 'ADOQUIN', 1556.00),
        ('2-40-45', 'CEMENTO', 1441.00),
        ('2-40-45', 'LOSETA', 1305.00),
        ('2-40-45', 'PIEDRA', 998.00),
        ('2-40-45', 'RIPIO', 913.00),
        ('2-40-45', 'TIERRA', 825.00),

        ('2-50-58', 'ASFALTO', 1271.00),
        ('2-50-58', 'ADOQUIN', 1053.00),
        ('2-50-58', 'CEMENTO', 947.00),
        ('2-50-58', 'LOSETA', 774.00),
        ('2-50-58', 'PIEDRA', 664.00),
        ('2-50-58', 'RIPIO', 613.00),
        ('2-50-58', 'TIERRA', 555.00),

        ('2-60-68', 'ASFALTO', 1180.00),
        ('2-60-68', 'ADOQUIN', 886.00),
        ('2-60-68', 'CEMENTO', 737.00),
        ('2-60-68', 'LOSETA', 661.00),
        ('2-60-68', 'PIEDRA', 555.00),
        ('2-60-68', 'RIPIO', 446.00),
        ('2-60-68', 'TIERRA', 367.00),

        ('2-70-76', 'ASFALTO', 695.00),
        ('2-70-76', 'ADOQUIN', 604.00),
        ('2-70-76', 'CEMENTO', 555.00),
        ('2-70-76', 'LOSETA', 464.00),
        ('2-70-76', 'PIEDRA', 364.00),
        ('2-70-76', 'RIPIO', 325.00),
        ('2-70-76', 'TIERRA', 273.00),

        ('2-80-82', 'ASFALTO', 464.00),
        ('2-80-82', 'ADOQUIN', 413.00),
        ('2-80-82', 'CEMENTO', 364.00),
        ('2-80-82', 'LOSETA', 325.00),
        ('2-80-82', 'PIEDRA', 273.00),
        ('2-80-82', 'RIPIO', 224.00),
        ('2-80-82', 'TIERRA', 188.00),

        ('3-10-16', 'ASFALTO', 1080.00),
        ('3-10-16', 'ADOQUIN', 980.00),
        ('3-10-16', 'CEMENTO', 937.00),
        ('3-10-16', 'LOSETA', 886.00),
        ('3-10-16', 'PIEDRA', 846.00),
        ('3-10-16', 'RIPIO', 792.00),
        ('3-10-16', 'TIERRA', 746.00),

        ('3-20-21', 'ASFALTO', 746.00),
        ('3-20-21', 'ADOQUIN', 692.00),
        ('3-20-21', 'CEMENTO', 643.00),
        ('3-20-21', 'LOSETA', 589.00),
        ('3-20-21', 'PIEDRA', 546.00),
        ('3-20-21', 'RIPIO', 495.00),
        ('3-20-21', 'TIERRA', 449.00),

        ('3-30-36', 'ASFALTO', 449.00),
        ('3-30-36', 'ADOQUIN', 397.00),
        ('3-30-36', 'CEMENTO', 349.00),
        ('3-30-36', 'LOSETA', 297.00),
        ('3-30-36', 'PIEDRA', 252.00),
        ('3-30-36', 'RIPIO', 194.00),
        ('3-30-36', 'TIERRA', 152.00)
)
INSERT INTO valor_suelo (
    id_esquema,
    id_municipio,
    id_zona_valor,
    id_material_via,
    valor_por_metro_cuadrado,
    vigencia_desde,
    vigencia_hasta
)
SELECT
    e.id_esquema,
    m.id_municipio,
    zv.id_zona_valor,
    mv.id_material_via,
    v.valor_m2,
    DATE '2015-01-01',
    NULL
FROM valores v
CROSS JOIN esquema e
CROSS JOIN municipio_lpz m
JOIN zona_tributaria zt ON zt.codigo = v.codigo_zona
JOIN zona_valor zv
  ON zv.id_municipio = m.id_municipio
 AND zv.id_zona_tributaria = zt.id_zona_tributaria
 AND zv.vigencia_desde = DATE '2015-01-01'
JOIN material_via mv ON mv.nombre = v.material
WHERE NOT EXISTS (
    SELECT 1
    FROM valor_suelo vs
    WHERE vs.id_esquema = e.id_esquema
      AND vs.id_municipio = m.id_municipio
      AND vs.id_zona_valor = zv.id_zona_valor
      AND vs.id_material_via = mv.id_material_via
      AND vs.vigencia_desde = DATE '2015-01-01'
);

-- -----------------------------------------------------
-- 8. TIPOLOGIAS Y DEPRECIACION 2015
-- -----------------------------------------------------

WITH esquema AS (
    SELECT id_esquema
    FROM esquema_valuacion
    WHERE nombre = 'LPZ 2015'
    ORDER BY fecha_inicio DESC
    LIMIT 1
),
municipio_lpz AS (
    SELECT id_municipio
    FROM municipio
    WHERE UPPER(nombre) = 'LA PAZ'
    ORDER BY id_municipio
    LIMIT 1
),
tipologias(codigo, tipo_tipologia, descripcion, valor_m2) AS (
    VALUES
        ('30', 'VIVIENDA_UNIFAMILIAR', 'Lujosa Residencial', 5212.00),
        ('31', 'VIVIENDA_UNIFAMILIAR', 'Muy Bueno', 3471.00),
        ('32', 'VIVIENDA_UNIFAMILIAR', 'Bueno', 2309.00),
        ('33', 'VIVIENDA_UNIFAMILIAR', 'Economica', 1444.00),
        ('34', 'VIVIENDA_UNIFAMILIAR', 'De Interes Social', 859.00),
        ('35', 'VIVIENDA_UNIFAMILIAR', 'Muy Economica/Marginal', 140.00),
        ('40', 'PROPIEDAD_HORIZONTAL', 'De Lujo', 6371.00),
        ('41', 'PROPIEDAD_HORIZONTAL', 'Muy Bueno', 4633.00),
        ('42', 'PROPIEDAD_HORIZONTAL', 'Bueno', 3471.00),
        ('43', 'PROPIEDAD_HORIZONTAL', 'Economica', 2882.00)
)
INSERT INTO tipologia (
    id_esquema,
    id_tipo_tipologia,
    id_municipio,
    codigo,
    descripcion,
    valor_por_metro_cuadrado,
    vigencia_desde,
    vigencia_hasta
)
SELECT
    e.id_esquema,
    tt.id_tipo_tipologia,
    m.id_municipio,
    t.codigo,
    t.descripcion,
    t.valor_m2,
    DATE '2015-01-01',
    NULL
FROM tipologias t
CROSS JOIN esquema e
CROSS JOIN municipio_lpz m
JOIN tipo_tipologia tt ON tt.nombre = t.tipo_tipologia
WHERE NOT EXISTS (
    SELECT 1
    FROM tipologia x
    WHERE x.id_esquema = e.id_esquema
      AND x.id_municipio = m.id_municipio
      AND x.codigo = t.codigo
      AND x.vigencia_desde = DATE '2015-01-01'
);

WITH esquema AS (
    SELECT id_esquema
    FROM esquema_valuacion
    WHERE nombre = 'LPZ 2015'
    ORDER BY fecha_inicio DESC
    LIMIT 1
),
municipio_lpz AS (
    SELECT id_municipio
    FROM municipio
    WHERE UPPER(nombre) = 'LA PAZ'
    ORDER BY id_municipio
    LIMIT 1
),
factores(antiguedad_minima, antiguedad_maxima, factor_ajuste) AS (
    VALUES
        (0, 5, 1.000),
        (6, 10, 0.975),
        (11, 15, 0.925),
        (16, 20, 0.900),
        (21, 25, 0.850),
        (26, 30, 0.800),
        (31, 35, 0.750),
        (36, 40, 0.700),
        (41, 45, 0.650),
        (46, 50, 0.600),
        (51, 120, 0.550)
)
INSERT INTO factor_depreciacion (
    id_esquema,
    id_municipio,
    antiguedad_minima,
    antiguedad_maxima,
    factor_ajuste,
    vigencia_desde,
    vigencia_hasta
)
SELECT
    e.id_esquema,
    m.id_municipio,
    f.antiguedad_minima,
    f.antiguedad_maxima,
    f.factor_ajuste,
    DATE '2015-01-01',
    NULL
FROM factores f
CROSS JOIN esquema e
CROSS JOIN municipio_lpz m
WHERE NOT EXISTS (
    SELECT 1
    FROM factor_depreciacion fd
    WHERE fd.id_esquema = e.id_esquema
      AND fd.id_municipio = m.id_municipio
      AND fd.antiguedad_minima = f.antiguedad_minima
      AND fd.antiguedad_maxima = f.antiguedad_maxima
      AND fd.vigencia_desde = DATE '2015-01-01'
);

WITH esquema AS (
    SELECT id_esquema
    FROM esquema_valuacion
    WHERE nombre = 'LPZ 2015'
    ORDER BY fecha_inicio DESC
    LIMIT 1
),
municipio_lpz AS (
    SELECT id_municipio
    FROM municipio
    WHERE UPPER(nombre) = 'LA PAZ'
    ORDER BY id_municipio
    LIMIT 1
),
factores(descripcion, angulo_minimo, angulo_maximo, factor_ajuste) AS (
    VALUES
        ('PLANO', 0.00, 10.00, 1.000),
        ('INCLINADO', 10.00, 15.00, 0.900),
        ('MUY_INCLINADO', 15.00, 90.00, 0.800)
)
INSERT INTO factor_pendiente (
    id_esquema,
    id_municipio,
    descripcion,
    angulo_minimo,
    angulo_maximo,
    factor_ajuste,
    vigencia_desde,
    vigencia_hasta
)
SELECT
    e.id_esquema,
    m.id_municipio,
    f.descripcion,
    f.angulo_minimo,
    f.angulo_maximo,
    f.factor_ajuste,
    DATE '2015-01-01',
    NULL
FROM factores f
CROSS JOIN esquema e
CROSS JOIN municipio_lpz m
WHERE NOT EXISTS (
    SELECT 1
    FROM factor_pendiente fp
    WHERE fp.id_esquema = e.id_esquema
      AND fp.id_municipio = m.id_municipio
      AND fp.descripcion = f.descripcion
      AND fp.vigencia_desde = DATE '2015-01-01'
);

-- -----------------------------------------------------
-- 9. FACTOR PH POR ZONA 2015
-- -----------------------------------------------------

WITH esquema AS (
    SELECT id_esquema
    FROM esquema_valuacion
    WHERE nombre = 'LPZ 2015'
    ORDER BY fecha_inicio DESC
    LIMIT 1
),
municipio_lpz AS (
    SELECT id_municipio
    FROM municipio
    WHERE UPPER(nombre) = 'LA PAZ'
    ORDER BY id_municipio
    LIMIT 1
),
factores(codigo_zona, factor_ajuste) AS (
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
)
INSERT INTO factor_ph_zona (
    id_esquema,
    id_municipio,
    id_zona_valor,
    factor_ajuste,
    vigencia_desde,
    vigencia_hasta
)
SELECT
    e.id_esquema,
    m.id_municipio,
    zv.id_zona_valor,
    f.factor_ajuste,
    DATE '2015-01-01',
    NULL
FROM factores f
CROSS JOIN esquema e
CROSS JOIN municipio_lpz m
JOIN zona_tributaria zt ON zt.codigo = f.codigo_zona
JOIN zona_valor zv
  ON zv.id_municipio = m.id_municipio
 AND zv.id_zona_tributaria = zt.id_zona_tributaria
 AND zv.vigencia_desde = DATE '2015-01-01'
WHERE NOT EXISTS (
    SELECT 1
    FROM factor_ph_zona fpz
    WHERE fpz.id_municipio = m.id_municipio
      AND fpz.id_zona_valor = zv.id_zona_valor
      AND fpz.vigencia_desde = DATE '2015-01-01'
);

COMMIT;

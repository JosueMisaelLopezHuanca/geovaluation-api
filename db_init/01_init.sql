-- =====================================================
-- SISTEMA DE AVALÚO CATASTRAL - VERSIÓN 2.0
-- =====================================================
-- Cambios respecto a v1:
--   [FIX-1]  Eliminado índice único duplicado en predio.codigo_catastral
--   [FIX-2]  construccion.fecha_actualizacion ahora tiene DEFAULT CURRENT_TIMESTAMP
--   [MEJ-1]  Índices faltantes añadidos
--   [MEJ-2]  Triggers anti-solapamiento en factor_depreciacion y factor_pendiente
--   [DEC-1]  avaluo dividido en avaluo_predio / avaluo_construccion / avaluo_unidad_ph
--   [DEC-2]  PKs unificadas a UUID (gestion, historial, solicitud_cambio, auditoria)
--   [DEC-3]  id_esquema incluido en UNIQUE de valor_suelo y tipologia
--   [DEC-4]  Trigger de validación de fraccion_ideal_participacion
--   [DEC-5]  zona_tributaria.codigo cambiado a VARCHAR(10)
-- =====================================================

-- 1. EXTENSIONES
CREATE EXTENSION IF NOT EXISTS postgis;


-- =====================================================
-- FUNCIÓN UTILITARIA: ACTUALIZACIÓN DE TIMESTAMP
-- =====================================================

CREATE OR REPLACE FUNCTION update_fecha_actualizacion()
RETURNS TRIGGER AS $$
BEGIN
    NEW.fecha_actualizacion = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- =====================================================
-- MÓDULO SEGURIDAD
-- =====================================================

CREATE TABLE persona (
    id_persona            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    nombres               VARCHAR(100) NOT NULL,
    apellido_paterno      VARCHAR(100) NOT NULL,
    apellido_materno      VARCHAR(100),
    ci                    VARCHAR(20)  UNIQUE NOT NULL,
    expedido_en           CHAR(2),                          -- LP, CB, SC, etc.
    fecha_nacimiento      DATE,
    telefono              VARCHAR(20),
    email                 VARCHAR(100),
    estado                VARCHAR(20)  NOT NULL DEFAULT 'ACTIVO',
    fecha_registro        TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_persona_estado CHECK (estado IN ('ACTIVO', 'INACTIVO'))
);
CREATE UNIQUE INDEX idx_persona_email_lower ON persona (LOWER(email));


CREATE TABLE usuario (
    id_usuario            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    id_persona            UUID         UNIQUE NOT NULL,
    nombre_usuario        VARCHAR(50)  UNIQUE NOT NULL,
    contrasena_hash       TEXT         NOT NULL,
    activo                BOOLEAN      DEFAULT TRUE,
    fecha_ultimo_acceso   TIMESTAMP WITH TIME ZONE,
    CONSTRAINT chk_usuario_nombre CHECK (LENGTH(nombre_usuario) >= 4),
    FOREIGN KEY (id_persona) REFERENCES persona(id_persona)
);


CREATE TABLE rol (
    id_rol                UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre                VARCHAR(50)  UNIQUE NOT NULL,
    descripcion           TEXT
);


CREATE TABLE usuario_rol (
    id_usuario            UUID NOT NULL,
    id_rol                UUID NOT NULL,
    PRIMARY KEY (id_usuario, id_rol),
    FOREIGN KEY (id_usuario) REFERENCES usuario(id_usuario) ON DELETE CASCADE,
    FOREIGN KEY (id_rol)     REFERENCES rol(id_rol)         ON DELETE CASCADE
);


-- =====================================================
-- DIVISIÓN TERRITORIAL  (SRID: 32719)
-- =====================================================

CREATE TABLE departamento (
    id_departamento       UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre                VARCHAR(100) NOT NULL,
    codigo_departamento   CHAR(2)      UNIQUE NOT NULL,
    codigo_interno        CHAR(2)      NOT NULL UNIQUE,
    geom                  GEOMETRY(MULTIPOLYGON, 32719),
    CONSTRAINT chk_departamento_codigo   CHECK (codigo_departamento ~ '^[0-9]{2}$'),
    CONSTRAINT chk_departamento_interno  CHECK (codigo_interno       ~ '^[0-9]{2}$')
);
CREATE INDEX idx_departamento_geom ON departamento USING GIST (geom);


CREATE TABLE provincia (
    id_provincia          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    id_departamento       UUID         NOT NULL,
    nombre                VARCHAR(100) NOT NULL,
    codigo_provincia      CHAR(2)      NOT NULL,
    codigo_interno        CHAR(4)      NOT NULL,
    geom                  GEOMETRY(MULTIPOLYGON, 32719),
    FOREIGN KEY (id_departamento) REFERENCES departamento(id_departamento) ON DELETE RESTRICT,
    UNIQUE (codigo_provincia, id_departamento),
    UNIQUE (codigo_interno),
    CONSTRAINT chk_provincia_codigo   CHECK (codigo_provincia ~ '^[0-9]{2}$'),
    CONSTRAINT chk_provincia_interno  CHECK (codigo_interno   ~ '^[0-9]{4}$')
);
CREATE INDEX idx_provincia_geom         ON provincia USING GIST (geom);
CREATE INDEX idx_provincia_departamento ON provincia(id_departamento);


CREATE TABLE municipio (
    id_municipio          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    id_provincia          UUID         NOT NULL,
    nombre                VARCHAR(100) NOT NULL,
    codigo_municipio      CHAR(2)      NOT NULL,
    codigo_interno        CHAR(6)      NOT NULL,
    geom                  GEOMETRY(MULTIPOLYGON, 32719),
    FOREIGN KEY (id_provincia) REFERENCES provincia(id_provincia) ON DELETE RESTRICT,
    UNIQUE (codigo_municipio, id_provincia),
    UNIQUE (codigo_interno),
    CONSTRAINT chk_municipio_codigo   CHECK (codigo_municipio ~ '^[0-9]{2}$'),
    CONSTRAINT chk_municipio_interno  CHECK (codigo_interno   ~ '^[0-9]{6}$')
);
CREATE INDEX idx_municipio_geom     ON municipio USING GIST (geom);
CREATE INDEX idx_municipio_provincia ON municipio(id_provincia);


CREATE TABLE distrito (
    id_distrito           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    id_municipio          UUID         NOT NULL,
    nombre                VARCHAR(100) NOT NULL,
    codigo_distrito       CHAR(2)      NOT NULL,
    codigo_interno        CHAR(8)      NOT NULL,
    geom                  GEOMETRY(MULTIPOLYGON, 32719),
    FOREIGN KEY (id_municipio) REFERENCES municipio(id_municipio) ON DELETE RESTRICT,
    UNIQUE (codigo_distrito, id_municipio),
    UNIQUE (codigo_interno),
    CONSTRAINT chk_distrito_codigo   CHECK (codigo_distrito ~ '^[0-9]{2}$'),
    CONSTRAINT chk_distrito_interno  CHECK (codigo_interno  ~ '^[0-9]{8}$')
);
CREATE INDEX idx_distrito_geom     ON distrito USING GIST (geom);
CREATE INDEX idx_distrito_municipio ON distrito(id_municipio);


CREATE TABLE zona (
    id_zona               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    id_distrito           UUID         NOT NULL,
    nombre                VARCHAR(100) NOT NULL,
    tipo                  VARCHAR(10)  NOT NULL DEFAULT 'URBANO',
    planimetria_aprobada  BOOLEAN      DEFAULT FALSE,
    codigo_zona           CHAR(2)      NOT NULL,
    codigo_interno        CHAR(10)     NOT NULL,
    geom                  GEOMETRY(MULTIPOLYGON, 32719),
    CONSTRAINT chk_zona_tipo     CHECK (tipo         IN ('URBANO', 'RURAL')),
    CONSTRAINT chk_zona_codigo   CHECK (codigo_zona  ~ '^[0-9]{2}$'),
    CONSTRAINT chk_zona_interno  CHECK (codigo_interno ~ '^[0-9]{10}$'),
    FOREIGN KEY (id_distrito) REFERENCES distrito(id_distrito) ON DELETE RESTRICT,
    UNIQUE (codigo_zona, id_distrito),
    UNIQUE (codigo_interno)
);
CREATE INDEX idx_zona_geom    ON zona USING GIST (geom);
CREATE INDEX idx_zona_distrito ON zona(id_distrito);


CREATE TABLE manzana (
    id_manzana            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    id_zona               UUID         NOT NULL,
    codigo_manzana        CHAR(3)      NOT NULL,
    codigo_interno        CHAR(13)     NOT NULL,
    geom                  GEOMETRY(MULTIPOLYGON, 32719),
    CONSTRAINT chk_manzana_codigo   CHECK (codigo_manzana  ~ '^[0-9]{3}$'),
    CONSTRAINT chk_manzana_interno  CHECK (codigo_interno  ~ '^[0-9]{13}$'),
    UNIQUE (codigo_manzana, id_zona),
    UNIQUE (codigo_interno),
    FOREIGN KEY (id_zona) REFERENCES zona(id_zona) ON DELETE RESTRICT
);
CREATE INDEX idx_manzana_geom ON manzana USING GIST (geom);
CREATE INDEX idx_manzana_zona ON manzana(id_zona);


-- =====================================================
-- VALUACIÓN
-- =====================================================

CREATE TABLE esquema_valuacion (
    id_esquema            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre                VARCHAR(100) NOT NULL,
    descripcion           TEXT,
    fecha_inicio          DATE         NOT NULL,
    fecha_fin             DATE
);


CREATE TABLE zona_tributaria (
    id_zona_tributaria    UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    -- [DEC-5] Cambiado de INT a VARCHAR(10) para consistencia con el resto de códigos
    codigo                VARCHAR(10)  NOT NULL UNIQUE,
    descripcion           TEXT
);


CREATE TABLE zona_valor (
    id_zona_valor         UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    id_municipio          UUID         NOT NULL REFERENCES municipio(id_municipio),
    id_zona_tributaria    UUID         REFERENCES zona_tributaria(id_zona_tributaria),
    macro_zona            INT          NOT NULL,
    subzona_inicio        INT          NOT NULL,
    subzona_fin           INT          NOT NULL,
    nombre                VARCHAR(100),
    descripcion           TEXT,
    vigencia_desde        DATE         NOT NULL,
    vigencia_hasta        DATE,
    CHECK (subzona_inicio <= subzona_fin),
    UNIQUE (id_municipio, macro_zona, subzona_inicio, subzona_fin, vigencia_desde)
);


CREATE TABLE material_via (
    id_material_via       UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre                VARCHAR(50)  NOT NULL UNIQUE,
    orden                 INT          NOT NULL
);


CREATE TABLE tipo_via (
    id_tipo_via           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre                VARCHAR(100) NOT NULL UNIQUE,
    jerarquia_valor       INT
);


CREATE TABLE valor_suelo (
    id_valor_suelo        UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    id_esquema            UUID         NOT NULL REFERENCES esquema_valuacion(id_esquema),
    id_municipio          UUID         NOT NULL REFERENCES municipio(id_municipio),
    id_zona_valor         UUID         NOT NULL REFERENCES zona_valor(id_zona_valor),
    id_material_via       UUID         NOT NULL REFERENCES material_via(id_material_via),
    valor_por_metro_cuadrado NUMERIC(10,2) NOT NULL,
    vigencia_desde        DATE         NOT NULL,
    vigencia_hasta        DATE,
    -- [DEC-3] id_esquema incluido para permitir esquemas paralelos por municipio
    UNIQUE (id_esquema, id_municipio, id_zona_valor, id_material_via, vigencia_desde)
);


CREATE TABLE servicio (
    id_servicio           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre                VARCHAR(100) NOT NULL UNIQUE,
    factor_incremento     NUMERIC(5,3) NOT NULL CHECK (factor_incremento >= 0)
);


CREATE TABLE tipo_tipologia (
    id_tipo_tipologia     UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre                VARCHAR(100) NOT NULL UNIQUE,
    descripcion           TEXT
);


CREATE TABLE tipologia (
    id_tipologia          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    id_esquema            UUID         NOT NULL REFERENCES esquema_valuacion(id_esquema),
    id_tipo_tipologia     UUID         NOT NULL REFERENCES tipo_tipologia(id_tipo_tipologia),
    id_municipio          UUID         NOT NULL REFERENCES municipio(id_municipio),
    codigo                VARCHAR(10)  NOT NULL,
    descripcion           VARCHAR(150),
    valor_por_metro_cuadrado NUMERIC(10,2) NOT NULL,
    vigencia_desde        DATE         NOT NULL,
    vigencia_hasta        DATE,
    -- [DEC-3] id_esquema incluido para permitir esquemas paralelos por municipio
    UNIQUE (id_esquema, id_municipio, codigo, vigencia_desde)
);


CREATE TABLE factor_pendiente (
    id_factor_pendiente   UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    id_esquema            UUID         NOT NULL REFERENCES esquema_valuacion(id_esquema),
    id_municipio          UUID         NOT NULL REFERENCES municipio(id_municipio),
    descripcion           VARCHAR(50),
    angulo_minimo         NUMERIC(5,2) NOT NULL,
    angulo_maximo         NUMERIC(5,2) NOT NULL,
    factor_ajuste         NUMERIC(5,3) NOT NULL,
    vigencia_desde        DATE         NOT NULL,
    vigencia_hasta        DATE,
    CHECK (angulo_minimo < angulo_maximo)
);

-- [MEJ-2] Trigger anti-solapamiento de rangos para factor_pendiente
CREATE OR REPLACE FUNCTION check_solapamiento_factor_pendiente()
RETURNS TRIGGER AS $$
DECLARE
    conflictos INT;
BEGIN
    SELECT COUNT(*) INTO conflictos
    FROM factor_pendiente
    WHERE id_esquema   = NEW.id_esquema
      AND id_municipio = NEW.id_municipio
      AND id_factor_pendiente <> NEW.id_factor_pendiente
      AND NEW.angulo_minimo < angulo_maximo
      AND NEW.angulo_maximo > angulo_minimo;

    IF conflictos > 0 THEN
        RAISE EXCEPTION
            'El rango de ángulo [%, %] se solapa con un rango existente para el mismo esquema y municipio.',
            NEW.angulo_minimo, NEW.angulo_maximo;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_factor_pendiente_solapamiento
BEFORE INSERT OR UPDATE ON factor_pendiente
FOR EACH ROW EXECUTE FUNCTION check_solapamiento_factor_pendiente();


CREATE TABLE factor_depreciacion (
    id_factor_depreciacion UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    id_esquema            UUID         NOT NULL REFERENCES esquema_valuacion(id_esquema),
    id_municipio          UUID         NOT NULL REFERENCES municipio(id_municipio),
    antiguedad_minima     INT          NOT NULL,
    antiguedad_maxima     INT          NOT NULL,
    factor_ajuste         NUMERIC(5,3) NOT NULL,
    vigencia_desde        DATE         NOT NULL,
    vigencia_hasta        DATE,
    CHECK (antiguedad_minima < antiguedad_maxima)
);

-- [MEJ-2] Trigger anti-solapamiento de rangos para factor_depreciacion
CREATE OR REPLACE FUNCTION check_solapamiento_factor_depreciacion()
RETURNS TRIGGER AS $$
DECLARE
    conflictos INT;
BEGIN
    SELECT COUNT(*) INTO conflictos
    FROM factor_depreciacion
    WHERE id_esquema   = NEW.id_esquema
      AND id_municipio = NEW.id_municipio
      AND id_factor_depreciacion <> NEW.id_factor_depreciacion
      AND NEW.antiguedad_minima < antiguedad_maxima
      AND NEW.antiguedad_maxima > antiguedad_minima;

    IF conflictos > 0 THEN
        RAISE EXCEPTION
            'El rango de antigüedad [%, %] se solapa con un rango existente para el mismo esquema y municipio.',
            NEW.antiguedad_minima, NEW.antiguedad_maxima;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_factor_depreciacion_solapamiento
BEFORE INSERT OR UPDATE ON factor_depreciacion
FOR EACH ROW EXECUTE FUNCTION check_solapamiento_factor_depreciacion();


CREATE TABLE factor_ph_zona (
    id_factor_ph_zona     UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    id_esquema            UUID         NOT NULL REFERENCES esquema_valuacion(id_esquema),
    id_municipio          UUID         NOT NULL REFERENCES municipio(id_municipio),
    id_zona_valor         UUID         NOT NULL REFERENCES zona_valor(id_zona_valor),
    factor_ajuste         NUMERIC(5,4) NOT NULL,
    vigencia_desde        DATE         NOT NULL,
    vigencia_hasta        DATE,
    UNIQUE (id_municipio, id_zona_valor, vigencia_desde)
);


-- =====================================================
-- NÚCLEO CATASTRAL
-- =====================================================

CREATE TABLE estado_predio (
    id_estado_predio      UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre                VARCHAR(50)  NOT NULL UNIQUE,
    descripcion           TEXT
);


CREATE TABLE tipo_conexion (
    id_tipo_conexion      UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre                VARCHAR(20)  UNIQUE NOT NULL
);


CREATE TABLE estado_conservacion (
    id_estado_conservacion UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre                 VARCHAR(20) UNIQUE NOT NULL
);


CREATE TABLE material_construccion (
    id_material_construccion UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre                   VARCHAR(50) UNIQUE NOT NULL
);


CREATE TABLE predio (
    id_predio             UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    id_manzana            UUID         NOT NULL REFERENCES manzana(id_manzana),
    id_zona_valor         UUID         REFERENCES zona_valor(id_zona_valor)     ON DELETE SET NULL,
    id_material_via       UUID         REFERENCES material_via(id_material_via)  ON DELETE SET NULL,
    id_tipo_via           UUID         REFERENCES tipo_via(id_tipo_via)          ON DELETE SET NULL,
    id_estado_predio      UUID         NOT NULL REFERENCES estado_predio(id_estado_predio),
    codigo_catastral      VARCHAR(50)  NOT NULL,
    codigo_predio         VARCHAR(50),
    numero_folio_real     VARCHAR(50),
    superficie_titulo     NUMERIC(12,2),
    superficie_mensura    NUMERIC(12,2) NOT NULL CHECK (superficie_mensura > 0),
    frente                NUMERIC(10,2),
    fondo                 NUMERIC(10,2),
    forma                 VARCHAR(50),
    pendiente_grados      NUMERIC(5,2) CHECK (pendiente_grados >= 0 AND pendiente_grados <= 90),
    direccion             TEXT,
    geom                  GEOMETRY(MULTIPOLYGON, 32719),
    fecha_creacion        TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    fecha_actualizacion   TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    usuario_creador_id    UUID         REFERENCES usuario(id_usuario) ON DELETE SET NULL,
    usuario_actualizacion_id UUID      REFERENCES usuario(id_usuario) ON DELETE SET NULL,
    activo                BOOLEAN      DEFAULT TRUE,
    -- [FIX-1] UNIQUE aquí ya crea un índice; se eliminó el CREATE UNIQUE INDEX duplicado
    UNIQUE (codigo_catastral)
);
CREATE INDEX idx_predio_geom         ON predio USING GIST (geom);
CREATE INDEX idx_predio_manzana      ON predio(id_manzana);
CREATE INDEX idx_predio_zona_valor   ON predio(id_zona_valor);
CREATE INDEX idx_predio_material_via ON predio(id_material_via);
CREATE INDEX idx_predio_estado       ON predio(id_estado_predio);
CREATE INDEX idx_predio_activo       ON predio(activo);

CREATE TRIGGER trg_predio_update
BEFORE UPDATE ON predio
FOR EACH ROW EXECUTE FUNCTION update_fecha_actualizacion();


CREATE TABLE predio_servicio (
    id_predio             UUID         NOT NULL,
    id_servicio           UUID         NOT NULL,
    id_tipo_conexion      UUID         NOT NULL,
    fecha_registro        TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id_predio, id_servicio),
    FOREIGN KEY (id_predio)          REFERENCES predio(id_predio)               ON DELETE CASCADE,
    FOREIGN KEY (id_servicio)        REFERENCES servicio(id_servicio)            ON DELETE RESTRICT,
    FOREIGN KEY (id_tipo_conexion)   REFERENCES tipo_conexion(id_tipo_conexion)
);
CREATE INDEX idx_predio_servicio_predio ON predio_servicio(id_predio);


CREATE TABLE construccion (
    id_construccion       UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    id_predio             UUID         NOT NULL,
    id_tipologia          UUID         NOT NULL,
    anio_construccion     INT          CHECK (anio_construccion >= 1800
                                          AND anio_construccion <= EXTRACT(YEAR FROM CURRENT_DATE)),
    superficie_construida NUMERIC(12,2) NOT NULL CHECK (superficie_construida > 0),
    numero_bloques        INT          DEFAULT 1 CHECK (numero_bloques > 0),
    es_propiedad_horizontal BOOLEAN    DEFAULT FALSE,
    id_material_construccion UUID,
    id_estado_conservacion   UUID,
    fecha_creacion        TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    -- [FIX-2] Añadido DEFAULT para consistencia con predio
    fecha_actualizacion   TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_predio)               REFERENCES predio(id_predio)                                 ON DELETE CASCADE,
    FOREIGN KEY (id_tipologia)            REFERENCES tipologia(id_tipologia)                           ON DELETE RESTRICT,
    FOREIGN KEY (id_material_construccion) REFERENCES material_construccion(id_material_construccion),
    FOREIGN KEY (id_estado_conservacion)  REFERENCES estado_conservacion(id_estado_conservacion)
);
CREATE INDEX idx_construccion_predio    ON construccion(id_predio);
-- [MEJ-1] Índice faltante sobre tipología
CREATE INDEX idx_construccion_tipologia ON construccion(id_tipologia);

CREATE TRIGGER trg_construccion_update
BEFORE UPDATE ON construccion
FOR EACH ROW EXECUTE FUNCTION update_fecha_actualizacion();


-- =====================================================
-- UNIDAD DE PROPIEDAD HORIZONTAL
-- =====================================================

-- [DEC-4] Función de validación de fracción ideal
CREATE OR REPLACE FUNCTION check_fraccion_ideal_participacion()
RETURNS TRIGGER AS $$
DECLARE
    suma_actual NUMERIC;
BEGIN
    -- Suma de todas las fracciones de la misma construcción, excluyendo la fila actual
    SELECT COALESCE(SUM(fraccion_ideal_participacion), 0)
    INTO suma_actual
    FROM unidad_ph
    WHERE id_construccion = NEW.id_construccion
      AND id_unidad_ph   <> NEW.id_unidad_ph;

    suma_actual := suma_actual + NEW.fraccion_ideal_participacion;

    -- No permitir que la suma supere 1.0 (tolerancia mínima de redondeo)
    IF suma_actual > 1.000001 THEN
        RAISE EXCEPTION
            'La suma de fracciones ideales para la construcción % superaría 1.0 (suma resultante: %)',
            NEW.id_construccion, suma_actual;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Función auxiliar para verificar que la suma sea exactamente 1.0 (llamar al cerrar el expediente)
CREATE OR REPLACE FUNCTION validar_fracciones_construccion(p_id_construccion UUID)
RETURNS VOID AS $$
DECLARE
    suma_total NUMERIC;
BEGIN
    SELECT COALESCE(SUM(fraccion_ideal_participacion), 0)
    INTO suma_total
    FROM unidad_ph
    WHERE id_construccion = p_id_construccion;

    IF ABS(suma_total - 1.0) > 0.000001 THEN
        RAISE EXCEPTION
            'La suma de fracciones ideales para la construcción % es % (debe ser exactamente 1.0)',
            p_id_construccion, suma_total;
    END IF;
END;
$$ LANGUAGE plpgsql;


CREATE TABLE unidad_ph (
    id_unidad_ph                UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    id_construccion             UUID         NOT NULL,
    id_tipologia                UUID         NOT NULL,
    identificador_unidad        VARCHAR(50)  NOT NULL,
    superficie_privativa        NUMERIC(12,2) NOT NULL CHECK (superficie_privativa > 0),
    superficie_comun_asignada   NUMERIC(12,2) NOT NULL CHECK (superficie_comun_asignada >= 0),
    fraccion_ideal_participacion NUMERIC(8,6) NOT NULL CHECK (fraccion_ideal_participacion > 0),
    fecha_creacion              TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_construccion) REFERENCES construccion(id_construccion) ON DELETE CASCADE,
    FOREIGN KEY (id_tipologia)    REFERENCES tipologia(id_tipologia)        ON DELETE RESTRICT
);
CREATE INDEX idx_unidad_ph_construccion ON unidad_ph(id_construccion);

-- [DEC-4] Trigger que previene que la suma de fracciones supere 1.0
CREATE TRIGGER trg_unidad_ph_fraccion
BEFORE INSERT OR UPDATE ON unidad_ph
FOR EACH ROW EXECUTE FUNCTION check_fraccion_ideal_participacion();


CREATE TABLE historial_geometria_predio (
    -- [DEC-2] Cambiado de SERIAL a UUID
    id_historial_geometria  UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    id_predio               UUID         NOT NULL,
    geometria_anterior      GEOMETRY(MULTIPOLYGON, 32719) NOT NULL,
    motivo_cambio           TEXT         NOT NULL,
    fecha_cambio            TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_predio) REFERENCES predio(id_predio) ON DELETE CASCADE
);
CREATE INDEX idx_historial_predio ON historial_geometria_predio(id_predio);
CREATE INDEX idx_historial_geom   ON historial_geometria_predio USING GIST (geometria_anterior);


-- =====================================================
-- TRANSACCIONAL
-- =====================================================

CREATE TABLE gestion (
    -- [DEC-2] Cambiado de SERIAL a UUID
    id_gestion            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    anio                  INT          NOT NULL UNIQUE CHECK (anio >= 2000),
    descripcion           VARCHAR(200),
    estado                VARCHAR(20)  NOT NULL CHECK (estado IN ('ABIERTA', 'CERRADA'))
);


-- =====================================================
-- AVALÚOS  [DEC-1] — Tablas separadas con FK real
-- Reemplaza la tabla polimórfica `avaluo` de v1
-- =====================================================

CREATE TABLE avaluo_predio (
    id_avaluo             UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    id_gestion            UUID         NOT NULL REFERENCES gestion(id_gestion)   ON DELETE RESTRICT,
    id_predio             UUID         NOT NULL REFERENCES predio(id_predio)      ON DELETE RESTRICT,
    valor_terreno         NUMERIC(14,2)          CHECK (valor_terreno >= 0),
    valor_construccion    NUMERIC(14,2)          CHECK (valor_construccion >= 0),
    valor_total           NUMERIC(14,2) NOT NULL CHECK (valor_total >= 0),
    base_imponible        NUMERIC(14,2) NOT NULL CHECK (base_imponible >= 0),
    fecha_calculo         TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    parametros_utilizados JSONB        NOT NULL,
    usuario_creador_id    UUID         NOT NULL REFERENCES usuario(id_usuario)    ON DELETE RESTRICT,
    usuario_validador_id  UUID                  REFERENCES usuario(id_usuario)    ON DELETE SET NULL,
    estado                VARCHAR(20)  NOT NULL CHECK (estado IN ('PENDIENTE','APROBADO','RECHAZADO','HISTORICO'))
);
CREATE INDEX idx_avaluo_predio_gestion ON avaluo_predio(id_gestion);
CREATE INDEX idx_avaluo_predio_predio  ON avaluo_predio(id_predio);
-- [MEJ-1]
CREATE INDEX idx_avaluo_predio_estado  ON avaluo_predio(estado);


CREATE TABLE avaluo_construccion (
    id_avaluo             UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    id_gestion            UUID         NOT NULL REFERENCES gestion(id_gestion)          ON DELETE RESTRICT,
    id_construccion       UUID         NOT NULL REFERENCES construccion(id_construccion) ON DELETE RESTRICT,
    valor_construccion    NUMERIC(14,2)          CHECK (valor_construccion >= 0),
    valor_total           NUMERIC(14,2) NOT NULL CHECK (valor_total >= 0),
    base_imponible        NUMERIC(14,2) NOT NULL CHECK (base_imponible >= 0),
    fecha_calculo         TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    parametros_utilizados JSONB        NOT NULL,
    usuario_creador_id    UUID         NOT NULL REFERENCES usuario(id_usuario)           ON DELETE RESTRICT,
    usuario_validador_id  UUID                  REFERENCES usuario(id_usuario)           ON DELETE SET NULL,
    estado                VARCHAR(20)  NOT NULL CHECK (estado IN ('PENDIENTE','APROBADO','RECHAZADO','HISTORICO'))
);
CREATE INDEX idx_avaluo_construccion_gestion       ON avaluo_construccion(id_gestion);
CREATE INDEX idx_avaluo_construccion_construccion  ON avaluo_construccion(id_construccion);
-- [MEJ-1]
CREATE INDEX idx_avaluo_construccion_estado        ON avaluo_construccion(estado);


CREATE TABLE avaluo_unidad_ph (
    id_avaluo             UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    id_gestion            UUID         NOT NULL REFERENCES gestion(id_gestion)      ON DELETE RESTRICT,
    id_unidad_ph          UUID         NOT NULL REFERENCES unidad_ph(id_unidad_ph)  ON DELETE RESTRICT,
    valor_construccion    NUMERIC(14,2)          CHECK (valor_construccion >= 0),
    valor_total           NUMERIC(14,2) NOT NULL CHECK (valor_total >= 0),
    base_imponible        NUMERIC(14,2) NOT NULL CHECK (base_imponible >= 0),
    fecha_calculo         TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    parametros_utilizados JSONB        NOT NULL,
    usuario_creador_id    UUID         NOT NULL REFERENCES usuario(id_usuario)      ON DELETE RESTRICT,
    usuario_validador_id  UUID                  REFERENCES usuario(id_usuario)      ON DELETE SET NULL,
    estado                VARCHAR(20)  NOT NULL CHECK (estado IN ('PENDIENTE','APROBADO','RECHAZADO','HISTORICO'))
);
CREATE INDEX idx_avaluo_unidad_ph_gestion    ON avaluo_unidad_ph(id_gestion);
CREATE INDEX idx_avaluo_unidad_ph_unidad     ON avaluo_unidad_ph(id_unidad_ph);
-- [MEJ-1]
CREATE INDEX idx_avaluo_unidad_ph_estado     ON avaluo_unidad_ph(estado);


-- =====================================================
-- FLUJO DE TRABAJO
-- =====================================================

CREATE TABLE solicitud_cambio (
    -- [DEC-2] Cambiado de SERIAL a UUID
    id_solicitud          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    id_usuario_creador    UUID         NOT NULL,
    id_usuario_revisor    UUID,
    entidad_afectada      VARCHAR(50)  NOT NULL,
    entidad_id            UUID         NOT NULL,
    tipo_accion           VARCHAR(10)  NOT NULL CHECK (tipo_accion IN ('INSERT', 'UPDATE', 'DELETE')),
    datos_json            JSONB        NOT NULL,
    geom_borrador         GEOMETRY(MULTIPOLYGON, 32719),
    estado                VARCHAR(20)  NOT NULL CHECK (estado IN ('PENDIENTE','APROBADO','RECHAZADO','OBSERVADO')),
    observaciones         TEXT,
    fecha_creacion        TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    fecha_revision        TIMESTAMP,
    FOREIGN KEY (id_usuario_creador) REFERENCES usuario(id_usuario) ON DELETE RESTRICT,
    FOREIGN KEY (id_usuario_revisor) REFERENCES usuario(id_usuario) ON DELETE SET NULL
);
CREATE INDEX idx_solicitud_estado           ON solicitud_cambio(estado);
CREATE INDEX idx_solicitud_entidad          ON solicitud_cambio(entidad_afectada, entidad_id);
-- [MEJ-1]
CREATE INDEX idx_solicitud_usuario_creador  ON solicitud_cambio(id_usuario_creador);


-- =====================================================
-- AUDITORÍA
-- =====================================================

CREATE TABLE auditoria (
    -- [DEC-2] Cambiado de SERIAL a UUID
    id_auditoria          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    id_usuario            UUID         NOT NULL,
    accion_realizada      VARCHAR(10)  NOT NULL CHECK (accion_realizada IN ('INSERT', 'UPDATE', 'DELETE')),
    nombre_tabla          VARCHAR(50)  NOT NULL,
    identificador_registro VARCHAR(50) NOT NULL,   -- UUID del registro afectado, almacenado como texto
    datos_anteriores      JSONB,
    datos_nuevos          JSONB,
    fecha_hora            TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    direccion_ip_origen   VARCHAR(45),
    FOREIGN KEY (id_usuario) REFERENCES usuario(id_usuario) ON DELETE RESTRICT
);
CREATE INDEX idx_auditoria_tabla  ON auditoria(nombre_tabla);
CREATE INDEX idx_auditoria_fecha  ON auditoria(fecha_hora);
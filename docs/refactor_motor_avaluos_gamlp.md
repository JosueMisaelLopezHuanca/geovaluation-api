# Refactorización Enterprise del Motor de Avalúos Catastrales GIS

## Contexto

Documento de arquitectura objetivo para transformar el módulo actual de avalúos del sistema Avalix en un motor profesional de valuación catastral orientado a GIS, auditoría tributaria y operación municipal para el GAMLP.

Fecha base de diseño: 2026-05-11  
Ámbito: backend geoespacial, modelos PostGIS, trazabilidad tributaria, frontend React operacional, cálculo masivo y cálculo individual auditable.

---

## 1. Diagnóstico del estado actual

El sistema actual ya resuelve una parte importante del contexto territorial:

- `predio`
- `manzana`
- `staging_pendientes`
- `staging_riesgos`
- `staging_zonas_homogeneas`
- `predio_contexto_espacial`
- asignación automática de `material_via`
- asignación automática de `zona_valor`
- `predio_servicio`
- cálculo preliminar de `avaluo_predio`

Sin embargo, desde una perspectiva municipal enterprise, el módulo todavía presenta cuatro debilidades estructurales:

1. La lógica normativa no está encapsulada como motor.
2. La trazabilidad tributaria es parcial y no normalizada.
3. El cálculo individual y el cálculo masivo no comparten una capa formal de reglas.
4. El frontend aún participa de decisiones económicas que deben vivir únicamente en backend.

---

## 2. Objetivo arquitectónico

Construir un **Motor de Valuación Catastral GIS-first** con estas propiedades:

- backend como única fuente normativa
- frontend solo para captura, visualización y auditoría
- cálculos reproducibles por gestión tributaria
- versionado histórico de tablas maestras
- desacople entre overlays GIS y reglas económicas
- soporte individual, masivo y batch
- trazabilidad por predio, cálculo, usuario, fórmula y geometrías utilizadas

---

## 3. Decisiones normativas obligatorias

### 3.1 Riesgo territorial

El riesgo territorial **no participa como factor económico**.

Se elimina de:

- valor del terreno
- base imponible
- impuesto

Se conserva en:

- contexto GIS
- auditoría técnica
- trazabilidad espacial
- filtros operativos y de inspección

### 3.2 Servicios válidos GAMLP

Servicios permitidos para el factor de servicios:

- agua
- alcantarillado
- electricidad
- teléfono

Regla:

- cada servicio suma `0.20`
- máximo total `0.80`
- gas e internet se mantienen como contexto urbano, pero no como factor tributario del terreno

### 3.3 Superficie de cálculo

La superficie de cálculo queda formalizada:

```text
superficie_calculo = superficie_manual ?? superficie_gis
```

Donde:

- `superficie_gis`: superficie espacial derivada del polígono o superficie catastral georreferenciada vigente
- `superficie_legal`: superficie declarada o registral documentada
- `superficie_manual`: ajuste técnico explícito, auditado
- `superficie_calculo`: superficie usada por el motor

### 3.4 Valor unitario de terreno

El valor unitario oficial se obtiene por combinación de:

- `gestion`
- `zona_tributaria`
- `material_via`

Nunca desde frontend.

### 3.5 Construcciones

Cada construcción debe modelarse por bloques.

Fórmula:

```text
valor_bloque = superficie * valor_tipologia * factor_antiguedad
valor_construccion = SUM(valor_bloque)
base_imponible = valor_terreno + valor_construccion
```

---

## 4. Modelo de dominio objetivo

### 4.1 Bounded Contexts

#### 4.1.1 Cadastral Core

Responsable de:

- predios
- manzanas
- geometrías oficiales
- superficies oficiales
- identificadores catastrales

#### 4.1.2 GIS Overlay Context

Responsable de:

- overlays espaciales
- intersecciones PostGIS
- cache territorial
- contexto físico y urbano

#### 4.1.3 Valuation Context

Responsable de:

- reglas tributarias
- tablas maestras
- fórmulas
- cálculo de terreno
- cálculo de construcción
- base imponible
- impuesto

#### 4.1.4 Audit & Compliance Context

Responsable de:

- trazabilidad completa
- cambios manuales
- fórmula usada
- tablas y overlays utilizados
- firma técnica del cálculo

#### 4.1.5 Batch Appraisal Context

Responsable de:

- colas
- procesos masivos
- recalculación anual
- actualización de contexto espacial
- reprocesamiento normativo

---

## 5. Arquitectura objetivo

### 5.1 Estilo

- DDD
- Hexagonal Architecture
- Event Driven para procesos masivos y trazabilidad
- CQRS ligero para separar lectura analítica de cálculo transaccional

### 5.2 Módulos backend propuestos

```text
app/
  modules/
    appraisal_engine/
      application/
      domain/
      infrastructure/
      api/
    gis_overlay/
      application/
      domain/
      infrastructure/
      api/
    master_data/
      application/
      domain/
      infrastructure/
      api/
    audit_trace/
      application/
      domain/
      infrastructure/
      api/
    batch_jobs/
      application/
      domain/
      infrastructure/
      api/
```

### 5.3 Servicios principales

#### AppraisalEngine

Orquesta todo el cálculo.

Responsabilidades:

- cargar predio
- resolver contexto GIS consolidado
- resolver tablas maestras vigentes
- calcular terreno
- calcular construcciones
- calcular base imponible
- calcular impuesto
- persistir resultado
- emitir traza

#### FactorResolver

Obtiene factores y determinantes normativos.

Resuelve:

- factor de pendiente
- puntaje de servicios
- tipología constructiva
- factor de antigüedad
- zona tributaria efectiva
- superficie de cálculo

#### GISOverlayService

Responsable de:

- intersecciones espaciales
- contexto por predio
- materialized views GIS
- composición de overlays

Devuelve:

- zona homogénea
- zona tributaria GIS
- pendiente dominante
- riesgo dominante
- material de vía
- servicios detectados

#### ValuationService

Implementa las fórmulas oficiales:

- `calculate_land_value`
- `calculate_building_block_value`
- `calculate_building_total`
- `calculate_taxable_base`
- `calculate_tax`

#### AuditTraceService

Genera trazabilidad formal:

- input funcional
- contexto GIS
- tablas maestras usadas
- fórmula aplicada
- versión normativa
- usuario
- fecha
- overrides manuales

---

## 6. Modelo relacional objetivo

### 6.1 Cálculo transaccional

#### `appraisal_case`

Representa una corrida de cálculo.

```sql
create table appraisal_case (
    appraisal_id uuid primary key default gen_random_uuid(),
    predio_id uuid not null,
    gestion_id uuid not null,
    normative_version_id uuid not null,
    status varchar(30) not null,
    initiated_by uuid not null,
    reviewed_by uuid null,
    calculation_mode varchar(20) not null, -- INDIVIDUAL | MASSIVE | RECALCULATION
    superficie_gis numeric(14,2) null,
    superficie_legal numeric(14,2) null,
    superficie_manual numeric(14,2) null,
    superficie_calculo numeric(14,2) not null,
    superficie_override_reason text null,
    created_at timestamptz not null default now(),
    reviewed_at timestamptz null,
    finalized_at timestamptz null
);
```

#### `appraisal_result`

```sql
create table appraisal_result (
    appraisal_id uuid primary key references appraisal_case(appraisal_id),
    valor_terreno numeric(16,2) not null,
    valor_construccion numeric(16,2) not null,
    base_imponible numeric(16,2) not null,
    impuesto_estimado numeric(16,2) not null,
    alicuota numeric(10,6) not null,
    formula_version varchar(30) not null,
    calculated_at timestamptz not null default now()
);
```

#### `appraisal_building_block`

```sql
create table appraisal_building_block (
    block_id uuid primary key default gen_random_uuid(),
    appraisal_id uuid not null references appraisal_case(appraisal_id) on delete cascade,
    orden integer not null,
    superficie numeric(14,2) not null,
    calidad_constructiva varchar(30) not null,
    anio_construccion integer not null,
    tipologia_id uuid not null,
    valor_tipologia_m2 numeric(14,2) not null,
    factor_antiguedad numeric(8,4) not null,
    valor_bloque numeric(16,2) not null
);
```

### 6.2 Master data versionado

#### `normative_version`

```sql
create table normative_version (
    normative_version_id uuid primary key default gen_random_uuid(),
    gestion_anio integer not null,
    nombre varchar(120) not null,
    version_codigo varchar(30) not null,
    vigente_desde date not null,
    vigente_hasta date null,
    estado varchar(20) not null, -- DRAFT | ACTIVE | CLOSED
    created_at timestamptz not null default now(),
    unique (gestion_anio, version_codigo)
);
```

#### `tabla_zonas_valor`

```sql
create table tabla_zonas_valor (
    tabla_zona_valor_id uuid primary key default gen_random_uuid(),
    normative_version_id uuid not null references normative_version(normative_version_id),
    zona_tributaria_codigo varchar(20) not null,
    material_via_codigo varchar(20) not null,
    valor_m2 numeric(14,2) not null,
    vigencia_desde date not null,
    vigencia_hasta date null,
    activo boolean not null default true,
    unique (normative_version_id, zona_tributaria_codigo, material_via_codigo)
);
```

#### `tabla_factores_pendiente`

```sql
create table tabla_factores_pendiente (
    factor_pendiente_id uuid primary key default gen_random_uuid(),
    normative_version_id uuid not null references normative_version(normative_version_id),
    rango_min numeric(8,2) not null,
    rango_max numeric(8,2) not null,
    factor numeric(8,4) not null,
    activo boolean not null default true
);
```

#### `tabla_factores_servicios`

```sql
create table tabla_factores_servicios (
    factor_servicio_id uuid primary key default gen_random_uuid(),
    normative_version_id uuid not null references normative_version(normative_version_id),
    servicio_codigo varchar(30) not null, -- AGUA, ALCANTARILLADO, ELECTRICIDAD, TELEFONO
    puntaje numeric(8,4) not null,
    activo boolean not null default true,
    unique (normative_version_id, servicio_codigo)
);
```

#### `tabla_tipologias_constructivas`

```sql
create table tabla_tipologias_constructivas (
    tipologia_id uuid primary key default gen_random_uuid(),
    normative_version_id uuid not null references normative_version(normative_version_id),
    calidad varchar(30) not null,
    categoria varchar(30) not null,
    estructura varchar(50) null,
    valor_m2 numeric(14,2) not null,
    activo boolean not null default true
);
```

#### `tabla_depreciacion_antiguedad`

```sql
create table tabla_depreciacion_antiguedad (
    depreciacion_id uuid primary key default gen_random_uuid(),
    normative_version_id uuid not null references normative_version(normative_version_id),
    edad_min integer not null,
    edad_max integer not null,
    factor numeric(8,4) not null
);
```

### 6.3 Contexto GIS persistido

#### `predio_gis_context`

```sql
create table predio_gis_context (
    predio_id uuid primary key,
    context_version bigint not null,
    zona_homogenea_codigo varchar(20) null,
    zona_homogenea_grupo varchar(20) null,
    zona_tributaria_codigo varchar(20) null,
    material_via_codigo varchar(20) null,
    pendiente_codigo integer null,
    pendiente_grados numeric(8,2) null,
    pendiente_cobertura_pct numeric(8,4) null,
    riesgo_codigo integer null,
    riesgo_grado varchar(50) null,
    riesgo_cobertura_pct numeric(8,4) null,
    servicios jsonb not null default '[]'::jsonb,
    overlays_hash varchar(64) null,
    calculated_at timestamptz not null default now()
);
```

### 6.4 Auditoría y trazabilidad

#### `appraisal_trace`

```sql
create table appraisal_trace (
    trace_id uuid primary key default gen_random_uuid(),
    appraisal_id uuid not null references appraisal_case(appraisal_id) on delete cascade,
    predio_id uuid not null,
    gestion_anio integer not null,
    normative_version varchar(30) not null,
    input_payload jsonb not null,
    factores_aplicados jsonb not null,
    contexto_espacial jsonb not null,
    tablas_utilizadas jsonb not null,
    formulas_aplicadas jsonb not null,
    overrides_manuales jsonb not null,
    geometries_used jsonb not null,
    generated_by uuid not null,
    generated_at timestamptz not null default now()
);
```

---

## 7. Fórmulas oficiales del motor

### 7.1 Valor terreno

```text
puntaje_servicios = min(0.80, suma(servicios_validos * 0.20))
factor_pendiente = resolver_tabla_pendiente(pendiente_codigo o pendiente_grados)
valor_unitario = resolver_valor_unitario(gestion, zona_tributaria, material_via)

valor_terreno =
  superficie_calculo
  * valor_unitario
  * puntaje_servicios
  * factor_pendiente
```

Notas:

- `factor_riesgo` no existe en la fórmula
- si no existen servicios válidos, debe aplicarse la regla normativa definida por el GAMLP; si se conserva la lógica mínima histórica, se usa piso de 0.20 solo si la norma efectivamente lo exige. Este punto debe quedar cerrado por versión normativa, no por heurística genérica.

### 7.2 Valor construcción

```text
edad = gestion_anio - anio_construccion
factor_antiguedad = resolver_depreciacion(edad)
valor_tipologia = resolver_tipologia(calidad_constructiva, categoria, estructura)

valor_bloque = superficie * valor_tipologia * factor_antiguedad
valor_construccion = sum(valor_bloque)
```

### 7.3 Base imponible e impuesto

```text
base_imponible = valor_terreno + valor_construccion
impuesto_estimado = base_imponible * alicuota_vigente
```

---

## 8. DTOs profesionales

### 8.1 Input DTO

```json
{
  "predio_id": "uuid",
  "gestion_anio": 2026,
  "superficie_manual": 450,
  "superficie_override_reason": "Regularización técnica con respaldo topográfico",
  "bloques": [
    {
      "superficie": 120,
      "calidad_constructiva": "MEDIA",
      "anio_construccion": 2010
    },
    {
      "superficie": 45,
      "calidad_constructiva": "ALTA",
      "anio_construccion": 2020
    }
  ],
  "estado_conservacion": "BUENO",
  "observaciones": "Regularización técnica"
}
```

### 8.2 Output DTO

```json
{
  "appraisal_id": "uuid",
  "predio_id": "uuid",
  "valor_terreno": 350000,
  "valor_construccion": 180000,
  "base_imponible": 530000,
  "impuesto_estimado": 7420,
  "factores_aplicados": {
    "factor_pendiente": 0.9,
    "puntaje_servicios": 0.8,
    "alicuota": 0.014
  },
  "contexto_espacial": {
    "zona_homogenea_codigo": "2-50",
    "zona_tributaria_codigo": "2-50 a 2-58",
    "material_via_codigo": "ASFALTO",
    "riesgo_codigo": 102,
    "riesgo_grado": "BAJO",
    "pendiente_codigo": 2
  },
  "tablas_utilizadas": [
    "tabla_zonas_valor:2026:v1",
    "tabla_factores_pendiente:2026:v1",
    "tabla_tipologias_constructivas:2026:v1",
    "tabla_depreciacion_antiguedad:2026:v1"
  ],
  "formula_aplicada": {
    "terreno": "superficie_calculo * valor_unitario * puntaje_servicios * factor_pendiente",
    "construccion": "sum(superficie * valor_tipologia * factor_antiguedad)"
  },
  "auditoria": {
    "superficie_gis": 438.17,
    "superficie_manual": 450,
    "superficie_calculo": 450,
    "usuario": "uuid",
    "timestamp": "2026-05-11T12:00:00Z",
    "normative_version": "2026-v1"
  }
}
```

---

## 9. API objetivo

### 9.1 Avalúos

- `POST /api/v2/avaluos/calcular`
- `GET /api/v2/avaluos/{id}`
- `GET /api/v2/avaluos/{id}/traza`
- `POST /api/v2/avaluos/recalcular`
- `POST /api/v2/avaluos/recalcular-masivo`

### 9.2 Contexto GIS

- `GET /api/v2/predios/{id}/contexto-gis`
- `GET /api/v2/predios/{id}/superficies`
- `GET /api/v2/predios/{id}/overlays`

### 9.3 Master data

- `GET /api/v2/tablas-maestras/zonas-valor?gestion=2026`
- `GET /api/v2/tablas-maestras/factores-pendiente?gestion=2026`
- `GET /api/v2/tablas-maestras/servicios?gestion=2026`
- `GET /api/v2/tablas-maestras/tipologias?gestion=2026`
- `GET /api/v2/tablas-maestras/depreciacion?gestion=2026`

### 9.4 Construcciones

- `POST /api/v2/construcciones`
- `PUT /api/v2/construcciones/{id}`
- `GET /api/v2/predios/{id}/construcciones`

### 9.5 Auditoría

- `GET /api/v2/auditoria/avaluos/{id}`
- `GET /api/v2/auditoria/predios/{id}/cambios-superficie`

---

## 10. Diseño de backend

### 10.1 Application layer

Casos de uso:

- `CalculateAppraisalUseCase`
- `GetPredioGisContextUseCase`
- `ResolveMasterTablesUseCase`
- `RebuildPredioGisContextUseCase`
- `RegisterManualSurfaceOverrideUseCase`
- `CreateBuildingBlocksUseCase`
- `GetAppraisalTraceUseCase`

### 10.2 Domain layer

Entidades:

- `PredioSnapshot`
- `SurfaceDecision`
- `GisContext`
- `LandValuation`
- `BuildingBlockValuation`
- `AppraisalResult`
- `NormativeVersion`

Value Objects:

- `GestionTributaria`
- `ZonaTributariaCode`
- `MaterialViaCode`
- `ServiceSet`
- `SurfaceSource`
- `AppraisalFormulaVersion`

### 10.3 Ports

Inbound:

- REST API
- batch jobs
- admin tools

Outbound:

- `PredioRepositoryPort`
- `GisOverlayPort`
- `MasterTableRepositoryPort`
- `AuditTracePort`
- `AppraisalRepositoryPort`
- `BuildingBlockRepositoryPort`
- `EventPublisherPort`
- `CachePort`

### 10.4 Infrastructure adapters

- PostGIS adapter
- SQLAlchemy repositories
- Redis cache adapter
- Celery/RQ/Kafka batch adapter
- materialized view refresh jobs

---

## 11. GIS strategy

### 11.1 Principio

El GIS no calcula economía.  
El GIS resuelve **contexto territorial estructurado** para que la capa tributaria aplique la norma.

### 11.2 Overlays necesarios

- zona homogénea
- material de vía
- pendiente
- riesgo
- servicios
- jurisdicción tributaria

### 11.3 Resolución recomendada

#### Predio context pipeline

1. tomar geometría oficial del predio
2. calcular `ST_PointOnSurface` para joins rápidos categóricos
3. calcular intersección por área para overlays con dominancia espacial
4. persistir resultado resumido en `predio_gis_context`
5. generar `overlays_hash` para invalidación

### 11.4 Materialized views

#### `mv_predio_overlay_context`

Contiene:

- predio_id
- zona_homogenea_codigo
- zona_tributaria_codigo
- material_via_codigo
- pendiente_codigo
- riesgo_codigo
- servicios
- updated_at

### 11.5 Índices geoespaciales

Requeridos:

```sql
create index idx_predio_geom on predio using gist (geom);
create index idx_manzana_geom on manzana using gist (geom);
create index idx_staging_pendientes_geom on staging_pendientes using gist (geometry);
create index idx_staging_riesgos_geom on staging_riesgos using gist (geometry);
create index idx_staging_zonas_homogeneas_geom on staging_zonas_homogeneas using gist (geometry);
```

### 11.6 Cache GIS

Cache por predio:

- key: `predio:gctx:{predio_id}:{context_version}`
- TTL corto para lectura operativa
- invalidación por:
  - cambio de geometría del predio
  - cambio de overlay
  - cambio de gestión normativa

---

## 12. Auditoría tributaria

### 12.1 Qué debe quedar auditado siempre

- predio calculado
- gestión
- usuario
- timestamp
- superficie_gis
- superficie_manual
- superficie_calculo
- causa del override manual
- zona homogénea usada
- material de vía usado
- servicios oficiales usados
- tabla de valor unitario
- tabla de depreciación
- fórmula exacta
- resultado final

### 12.2 Nivel de detalle

Debe ser suficiente para que un auditor municipal pueda reconstruir el cálculo sin abrir el código fuente.

---

## 13. Frontend React recomendado

### 13.1 El frontend no debe decidir economía

Eliminar del frontend como input del cálculo:

- `valor_base_m2`
- `factor_riesgo`
- `factor_servicios`

### 13.2 El frontend sí debe capturar

- superficie manual
- motivo del override
- bloques de construcción
- observaciones técnicas
- validación humana de servicios
- comparación entre superficie GIS y superficie manual

### 13.3 UX recomendada

#### Sección “Superficies”

- superficie GIS
- superficie legal
- superficie manual
- superficie de cálculo
- badge: `manual sobreescribe GIS`

#### Sección “Contexto GIS”

- zona homogénea
- zona tributaria
- material de vía
- pendiente
- riesgo
- overlays usados

#### Sección “Servicios oficiales”

Checkboxes solo para:

- agua
- alcantarillado
- electricidad
- teléfono

Gas e internet solo como visualización contextual, no como factor tributario.

#### Sección “Construcciones”

Lista dinámica de bloques:

- superficie
- calidad
- año
- subtotal por bloque

#### Sección “Trazabilidad”

- tablas maestras utilizadas
- factores aplicados
- fórmulas
- fecha
- versión normativa

---

## 14. Validaciones

### 14.1 Backend

- predio existente
- gestión válida
- geometría vigente
- superficie manual > 0
- motivo obligatorio cuando existe superficie manual
- bloques con superficie > 0
- año de construcción razonable
- calidad existente en master data

### 14.2 GIS

- SRID consistente
- geometría no nula
- geometría válida
- predio con contexto GIS resoluble o estado explícito de faltante

### 14.3 Tributarias

- existencia de valor unitario oficial
- existencia de tipología
- existencia de depreciación
- existencia de alícuota vigente

Si falta una tabla oficial, el cálculo debe fallar de forma explícita y auditable, no sustituirse por defaults invisibles.

---

## 15. Estrategia multi-gestión

### 15.1 Principio

Cada cálculo debe quedar ligado a una `normative_version`.

No se debe recalcular históricamente con la tabla vigente actual salvo que el usuario ejecute un reproceso formal.

### 15.2 Patrón

- `gestion_anio`
- `normative_version_id`
- tablas maestras versionadas
- trazabilidad por versión

### 15.3 Beneficios

- cálculos 2025 no cambian al cargar 2026
- cálculos 2026 no cambian al cargar 2027
- auditoría histórica estable

---

## 16. Escalabilidad municipal

### 16.1 Cálculo individual

Uso en:

- inspección técnica
- atención tributaria
- simulación

### 16.2 Cálculo masivo

Uso en:

- actualización anual
- campañas tributarias
- recálculo de barrios o macrodistritos

### 16.3 Recomendaciones

- batch queue con partición por distrito o macrodistrito
- snapshots de master data
- chunks de 2k a 10k predios según peso GIS
- tablas staging separadas de tablas productivas
- materialized views refrescables
- cache Redis para lecturas repetitivas
- jobs idempotentes

---

## 17. Estrategia de implementación incremental sobre el sistema actual

### Fase 1. Normalización normativa

1. eliminar `factor_riesgo` del cálculo económico
2. limitar `factor_servicios` a 4 servicios oficiales
3. mover todo cálculo económico a backend
4. congelar parámetros económicos enviados por frontend

### Fase 2. Versionado de tablas

1. introducir `normative_version`
2. migrar `zona_valor`, `factor_pendiente`, `tipologia`, `depreciacion`
3. ligar cálculo a gestión y versión normativa

### Fase 3. Superficies y auditoría

1. separar `superficie_gis`, `superficie_legal`, `superficie_manual`, `superficie_calculo`
2. registrar overrides con usuario, fecha y motivo
3. exponer traza completa

### Fase 4. Construcciones enterprise

1. soportar bloques múltiples
2. resolver tipologías y depreciación desde tablas maestras
3. agregar cálculo integral

### Fase 5. GIS Context formal

1. reemplazar lecturas ad hoc por `predio_gis_context`
2. materializar overlays
3. desacoplar cálculo de queries espaciales pesadas on-demand

### Fase 6. Batch and audit

1. jobs masivos
2. cola de recálculo
3. panel de auditoría

---

## 18. Recomendaciones DevOps

- contenedor PostGIS dedicado
- parámetros de conexión robustos (`pool_pre_ping`, `pool_recycle`, timeouts)
- workers separados para batch GIS
- observabilidad:
  - Prometheus
  - métricas de pool
  - métricas de consultas GIS
  - tiempos de cálculo por predio
- backups por gestión tributaria
- migraciones con Alembic
- ambientes:
  - dev
  - qa normativo
  - preproducción cartográfica
  - producción tributaria

---

## 19. Diagrama textual de arquitectura

```text
[React Frontend]
    |
    v
[API Appraisal Controller]
    |
    v
[CalculateAppraisalUseCase]
    |
    +--> [PredioRepository]
    |
    +--> [GISOverlayService]
    |         |
    |         +--> [PostGIS overlays]
    |         +--> [predio_gis_context]
    |
    +--> [FactorResolver]
    |         |
    |         +--> [tabla_zonas_valor]
    |         +--> [tabla_factores_pendiente]
    |         +--> [tabla_factores_servicios]
    |         +--> [tabla_tipologias_constructivas]
    |         +--> [tabla_depreciacion_antiguedad]
    |
    +--> [ValuationService]
    |         |
    |         +--> valor terreno
    |         +--> valor construccion
    |         +--> base imponible
    |         +--> impuesto
    |
    +--> [AuditTraceService]
    |         |
    |         +--> appraisal_trace
    |
    +--> [AppraisalRepository]
              |
              +--> appraisal_case
              +--> appraisal_result
              +--> appraisal_building_block
```

---

## 20. Recomendación directa para este repositorio

El siguiente movimiento correcto sobre `avalix_backend_v2` es:

1. crear `app/modules/appraisal_engine`
2. mantener el módulo actual `app/domain/avaluos` como fachada legacy temporal
3. introducir `v2` de endpoints sin romper `v1`
4. migrar primero:
   - eliminación de `factor_riesgo`
   - corrección de servicios oficiales
   - `superficie_terreno_override` con auditoría formal
5. luego migrar bloques de construcción y trazabilidad completa

En otras palabras: el sistema actual ya tiene un buen esqueleto GIS. Lo que falta no es “otro CRUD”, sino convertir ese esqueleto en un motor normativo auditable y versionado.


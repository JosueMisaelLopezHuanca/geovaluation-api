# Despliegue beta gratuito

Este documento deja una ruta simple para publicar una beta de prueba. No es una recomendacion de produccion: los planes gratuitos cambian, tienen limites y pueden dormir servicios.

## Arquitectura recomendada

- Base de datos: Supabase Postgres con PostGIS habilitado.
- Backend: Render Web Service con Docker.
- Frontend: Vercel o Netlify como sitio estatico.

Motivo: el frontend es estatico y barato de servir; el backend queda como API FastAPI; la base necesita PostGIS real para consultas espaciales.

## 1. Base de datos PostGIS

Opcion practica:

1. Crear proyecto en Supabase.
2. Habilitar extension `postgis` desde Database > Extensions y anotar el esquema elegido, por ejemplo `extensions` o `gis`.
3. Ejecutar scripts SQL en orden:
   - `db_init/01_init.sql`
   - `db_init/02_seed_min_operativa_2015.sql`
   - `db_init/03_predio_contexto_espacial.sql`
   - `db_init/04_appraisal_v2.sql`
   - `db_init/05_appraisal_v2_precision.sql`
   - `db_init/06_appraisal_v2_consolidation.sql`
   - `db_init/07_predio_otb_contexto.sql`
   - `db_init/08_normativa_gt_2015_vigente.sql`
   - `db_init/09_propiedad_horizontal_impbi_referencia.sql`
   - `db_init/10_consultas_beta_publicas.sql`
4. Configurar `DATABASE_SEARCH_PATH=public,extensions` si PostGIS se creo en `extensions`, o `public,gis` si se creo en `gis`.
5. Cargar datos reales desde un respaldo autorizado o restaurar un dump controlado; los shapefiles no forman parte del repositorio publico.
6. Confirmar:

```sql
SELECT PostGIS_Version();
SELECT COUNT(*) FROM predio;
SELECT COUNT(*) FROM predio_otb_contexto;
```

## 2. Backend en Render

Archivos preparados:

- `Dockerfile`
- `.dockerignore`
- `requirements-api.txt`
- `render.yaml`

Variables obligatorias:

```env
DATABASE_URL=postgresql+asyncpg://USUARIO:PASSWORD@HOST:5432/DB
DATABASE_SEARCH_PATH=public,extensions
CATASTRO_ADMIN_USER=admin
CATASTRO_ADMIN_PASSWORD=CAMBIAR_EN_BETA
CATASTRO_AUTH_SECRET=GENERAR_VALOR_LARGO
CATASTRO_AUTH_TTL_MINUTES=240
CORS_ALLOWED_ORIGINS=https://URL-DEL-FRONTEND.vercel.app
CORS_ALLOW_LAN=false
```

Pasos:

1. Subir repositorio backend a GitHub.
2. En Render, crear Web Service.
3. Elegir Docker y usar el `Dockerfile` del repo.
4. Configurar variables.
5. Health check: `/api/v2/health`.
6. Verificar:

```bash
curl https://URL-BACKEND.onrender.com/api/v2/health
```

Notas:

- En free tier, Render puede dormir el servicio por inactividad.
- El primer request despues de dormir puede tardar cerca de un minuto.
- El filesystem de Render es efimero; no guardar archivos subidos ni datos SQLite ahi.
- La base local actual ocupa aproximadamente 415 MB; Supabase Free alcanza modo solo lectura al superar 500 MB. Para una beta estable, eliminar staging innecesario tras validar la importacion o usar un plan con margen.
- Los shapefiles existentes en el historial remoto deben evaluarse segun su autorizacion de publicacion; retirarlos del ultimo commit no borra versiones historicas.

## 3. Frontend en Vercel

Archivos preparados:

- `vercel.json`

Variables:

```env
VITE_API_BASE_URL=https://URL-BACKEND.onrender.com
VITE_MAPTILER_TOKEN=token_publico_si_corresponde
VITE_DEFAULT_CENTER_LAT=-16.4897
VITE_DEFAULT_CENTER_LNG=-68.1193
VITE_DEFAULT_ZOOM=15
```

Build:

```bash
npm install
npm run build
```

Configuracion:

- Framework: Vite.
- Build command: `npm run build`.
- Output directory: `dist`.

Despues de publicar, copiar la URL de Vercel al backend en `CORS_ALLOWED_ORIGINS`.

## 4. Frontend en Netlify

Archivo preparado:

- `public/_redirects`

Configuracion:

- Build command: `npm run build`.
- Publish directory: `dist`.
- Variables iguales a Vercel.

## 5. Checklist post-deploy

1. Abrir `/api/v2/health`.
2. Probar login administrador.
3. Probar busqueda por codigo.
4. Probar busqueda por OTB.
5. Probar seleccion de predio en mapa.
6. Probar preview de avaluo.
7. Probar calcular con `persistir_override=false`.
8. Revisar consola del navegador sin errores CORS.
9. Probar en celular.

## Fuentes oficiales consultadas

- Render Free: https://render.com/docs/free
- Render Web Services: https://render.com/docs/web-services
- Render Docker: https://render.com/docs/docker
- Supabase PostGIS: https://supabase.com/docs/guides/database/extensions/postgis
- Vercel rewrites: https://vercel.com/docs/rewrites
- Netlify redirects: https://docs.netlify.com/routing/redirects/

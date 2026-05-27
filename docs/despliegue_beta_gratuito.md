# Despliegue beta gratuito

Este documento deja una ruta simple para publicar una beta de prueba. No es una recomendacion de produccion: los planes gratuitos cambian, tienen limites y pueden dormir servicios.

## Arquitectura recomendada

- Base de datos: Supabase Postgres con PostGIS habilitado.
- Backend: Render Web Service con Docker.
- Frontend: Vercel o Netlify como sitio estatico.

Motivo: el frontend es estatico y barato de servir; el backend queda como API FastAPI; la base necesita PostGIS real para consultas espaciales.

## 1. Base de datos PostGIS

Opcion practica:

1. Crear el proyecto Supabase con la cuenta propietaria del despliegue.
2. Como el frontend consume FastAPI y no `supabase-js`, deshabilitar **Data API** en Supabase antes de cargar tablas catastrales.
3. Habilitar `postgis` en el esquema `public` para esta beta. La base heredada usa columnas `public.geometry`; mover PostGIS a `extensions` requiere una migracion de esquema separada.
4. Con la base local validada en Docker, generar un respaldo reducido y limpio:

```powershell
.\scripts\export_supabase_beta.ps1 -Tag beta_inicial
```

5. Restaurar los dos archivos generados (`.backup` y `.restore.list`) en Supabase usando herramientas PostgreSQL 15 compatibles con la base origen.
6. Despues de restaurar, refrescar la vista administrativa:

```sql
REFRESH MATERIALIZED VIEW mv_predio_superficie_diferencias;
```

7. Configurar en Render:

```env
DATABASE_SEARCH_PATH=public
```

8. Confirmar:

```sql
SELECT PostGIS_Version();
SELECT COUNT(*) FROM predio;
SELECT COUNT(*) FROM predio_otb_contexto;
SELECT COUNT(*) FROM public_beta_consulta;
SELECT pg_size_pretty(pg_database_size(current_database()));
```

### Contenido del respaldo beta

El script conserva predios, manzanas, OTBs, pendientes, riesgos, zonas, contexto espacial, normativa y construcciones registradas. Omite la carga temporal `staging_predios`, porque los predios productivos ya estan consolidados, y omite datos generados durante pruebas locales: avaluos calculados, overrides manuales, auditorias y consultas/contactos beta.

La restauracion local validada el 26 de mayo de 2026 ocupo `277.36 MB`, con `118950` predios y `118269` relaciones predio-OTB, frente al limite de `500 MB` de Supabase Free.

## 2. Backend en Render

Archivos preparados:

- `Dockerfile`
- `.dockerignore`
- `requirements-api.txt`
- `render.yaml`

Variables obligatorias:

```env
DATABASE_URL=postgresql+asyncpg://USUARIO:PASSWORD@HOST:5432/DB
DATABASE_SEARCH_PATH=public
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
- La base local completa ocupa aproximadamente 415 MB; el respaldo beta reducido fue validado en aproximadamente 277 MB. Supabase Free alcanza modo solo lectura al superar 500 MB.
- La Data API de Supabase debe permanecer deshabilitada mientras las tablas catastrales residan en `public`; toda consulta publica pasa por la API FastAPI.
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
- Supabase seguridad de datos: https://supabase.com/docs/guides/database/secure-data/
- Supabase seguridad de Data API: https://supabase.com/docs/guides/api/securing-your-api
- Vercel rewrites: https://vercel.com/docs/rewrites
- Netlify redirects: https://docs.netlify.com/routing/redirects/

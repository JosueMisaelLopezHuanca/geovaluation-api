# Fases para publicar la beta

Este documento separa lo que debe ir a GitHub, lo que debe ir a la base de datos y lo que debe configurarse en los servicios gratuitos. La meta es subir una beta funcional sin mezclar codigo, datos pesados y secretos.

## Decision de despliegue

- Backend: usar Docker en Render. Ya existe `Dockerfile`, `.dockerignore`, `requirements-api.txt` y `render.yaml`.
- Frontend: no necesita Docker. Se publica como sitio estatico en Vercel o Netlify con `npm run build`.
- Base de datos: no se sube dentro del repo. Se restaura o migra a Supabase/Postgres con PostGIS.
- Datos GIS crudos: no subir `shapefiles/` al repo principal por defecto. Guardarlos como respaldo controlado, release privado, Drive institucional o repositorio de datos separado.

## Fase 0 - Limpieza pre-Git

- Quitar nombres temporales visibles del sistema.
- Dejar `.env.example` con valores de ejemplo, sin credenciales reales.
- Mantener `.env` fuera de Git.
- Mantener `shapefiles/`, dumps y backups fuera de Git.
- Si un repositorio ya publico datos crudos, eliminar los archivos de la rama nueva no los retira del historial; confirmar autorizacion o reescribir/migrar el repositorio antes del lanzamiento.
- Ejecutar:

```powershell
.\venv\Scripts\python.exe -m compileall -q app test
.\venv\Scripts\python.exe -m pytest test -q
.\venv\Scripts\python.exe -m app.scripts.verify_beta
```

En frontend:

```powershell
npm run lint
npm run build
```

## Fase 1 - GitHub

Subir dos repositorios o un monorepo con carpetas claras:

- `catastro-backend`: API FastAPI, scripts SQL, Dockerfile y documentacion.
- `catastro-frontend`: React/Vite, geovisor, documentacion de usuario y configuracion Vercel/Netlify.

Recomendacion para este avance: dos repositorios, porque Render y Vercel detectan mejor cada proyecto por separado.

## Fase 2 - Base de datos beta

- Crear proyecto Supabase.
- Activar extension PostGIS.
- Configurar `DATABASE_SEARCH_PATH=public,extensions` o `public,gis`, segun el esquema elegido al activar PostGIS.
- Restaurar un dump de la base local o ejecutar scripts `db_init` y cargar datos.
- Verificar tablas criticas:

```sql
SELECT COUNT(*) FROM predio;
SELECT COUNT(*) FROM predio_otb_contexto;
SELECT COUNT(*) FROM staging_otbs;
SELECT pg_size_pretty(pg_database_size(current_database()));
```

La base local medida para esta beta pesa aproximadamente 415 MB, por lo que entra ajustada en planes gratuitos con limite de 500 MB. Antes de abrir la beta, considerar limpiar tablas staging duplicadas despues de generar los contextos necesarios o usar un plan pagado.

## Fase 3 - Backend beta

- Crear Web Service en Render.
- Modo: Docker.
- Health check: `/api/v2/health`.
- Variables:

```env
DATABASE_URL=postgresql+asyncpg://...
DATABASE_SEARCH_PATH=public,extensions
CATASTRO_ADMIN_USER=admin
CATASTRO_ADMIN_PASSWORD=valor-fuerte
CATASTRO_AUTH_SECRET=valor-largo-aleatorio
CATASTRO_AUTH_TTL_MINUTES=240
CORS_ALLOWED_ORIGINS=https://URL-FRONTEND
CORS_ALLOW_LAN=false
```

Docker no es obligatorio para FastAPI, pero aqui conviene usarlo porque reduce diferencias entre la PC local y Render.

## Fase 4 - Frontend beta

- Publicar en Vercel o Netlify.
- Build command: `npm run build`.
- Output: `dist`.
- Variables:

```env
VITE_API_BASE_URL=https://URL-BACKEND.onrender.com
VITE_MAPTILER_TOKEN=token-publico-si-corresponde
VITE_DEFAULT_CENTER_LAT=-16.4897
VITE_DEFAULT_CENTER_LNG=-68.1193
VITE_DEFAULT_ZOOM=15
```

Despues de publicar, copiar la URL final del frontend en `CORS_ALLOWED_ORIGINS` del backend.

## Fase 5 - QA final

- Health backend.
- Login administrador.
- Busqueda por codigo.
- Busqueda por OTB.
- Busqueda por zona.
- Seleccion de predio en mapa.
- Contexto GIS.
- Preview de avaluo.
- Calcular con `persistir_override=false`.
- Prueba desde celular.
- Revisar consola del navegador sin errores CORS.

## Pendientes por modulo

Backend:

- Migraciones Alembic formales.
- Usuarios y roles en tabla real.
- Mensajes de validacion mas amigables ante errores 422.
- CI con pytest.

Base de datos:

- Dump reproducible para beta.
- Politica de respaldo.
- Simplificacion o vector tiles si crecen las capas.
- Indices revisados tras restaurar en Supabase.

Frontend:

- Nombre final y logo institucional definitivo.
- Busqueda por direccion/calle cuando exista fuente de vias.
- Mejor reporte PDF institucional.
- Prueba visual en mas tamanos de celular.

Seguridad:

- Cambiar credenciales antes de publicar.
- Usar `CATASTRO_AUTH_SECRET` fuerte.
- Evitar exponer endpoints administrativos sin sesion.
- Evaluar HTTPS y dominios institucionales para una fase posterior.

# Backend catastral GIS

Backend FastAPI para consulta catastral, capas GIS, busqueda de predios, autenticacion administrativa y calculo de avaluos.

## Requisitos

- Python 3.13 o compatible con el entorno actual.
- PostgreSQL 15+ con PostGIS.
- Dependencias de `requirements.txt`.

## Configuracion local

1. Copiar variables de entorno:

```powershell
Copy-Item .env.example .env
```

2. Levantar la base de datos:

```powershell
docker compose up -d db
```

3. Instalar dependencias:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

4. Ejecutar API:

```powershell
.\venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Para beta publica, configurar `CORS_ALLOWED_ORIGINS` con la URL del frontend publicado. Si PostGIS se habilita en un esquema de Supabase distinto de `public`, configurar tambien `DATABASE_SEARCH_PATH`, por ejemplo `public,extensions`.

## Endpoints principales

- `GET /api/v2/health`: verifica estado del servicio.
- `POST /api/v2/auth/login`: acceso administrador.
- `GET /api/v1/predios/buscar`: busqueda por codigo, zona u OTB.
- `GET /api/v2/gis/capas/{capa}/bbox`: capas GIS por ventana del mapa.
- `POST /api/v2/avaluos/preview`: calcula sin persistir.
- `POST /api/v2/avaluos/calcular`: calcula y puede persistir segun `persistir_override`.
- `POST /api/v2/beta/consultas`: registra participacion publica consentida.
- `GET /api/v2/beta/consultas/resumen`: resumen beta protegido para administracion.
- `GET /api/v2/beta/consultas`: listado beta protegido, incluidos contactos autorizados.
- `GET /api/v2/beta/consultas/export/csv`: descarga administrativa protegida para seguimiento beta.
- `DELETE /api/v2/beta/consultas/{id}/contacto`: elimina contacto autorizado conservando estadistica de la consulta.

## Pruebas

```powershell
.\venv\Scripts\python.exe -m pytest test -q
```

Verificacion integral de beta local sin guardar avaluos:

```powershell
.\venv\Scripts\python.exe -m app.scripts.verify_beta
```

## Notas de beta

- La consulta publica debe usar `persistir_override=false` para no ensuciar la base de datos.
- El usuario administrador se configura con `CATASTRO_ADMIN_USER` y `CATASTRO_ADMIN_PASSWORD`; no publicar una beta con credenciales de desarrollo.
- El panel beta muestra contactos unicamente cuando el visitante autorizo seguimiento.
- Las capas OTB se importan localmente desde `shapefiles/otb_lapaz.*`; la API desplegada consume las tablas PostGIS ya cargadas.
- `predio_otb_contexto` cachea la OTB dominante por predio para acelerar busquedas publicas.
- Los archivos `__pycache__`, `.pytest_cache`, `venv`, `.env`, dumps y shapefiles crudos quedan fuera de Git por defecto.
- Guia de despliegue gratuito: `docs/despliegue_beta_gratuito.md`.
- Fases y pendientes antes de publicar: `docs/fases_publicacion_beta.md`.

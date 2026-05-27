# Plan de cierre beta

Este plan ordena el trabajo pendiente para convertir el avance actual en una beta presentable, estable y facil de continuar.

## 1. Estabilizacion tecnica

- Mantener backend y frontend en la rama `codex/beta-iigeo-estabilizacion`.
- Ejecutar antes de cada entrega:
  - Backend: `.\venv\Scripts\python.exe -m pytest test -q`
  - Backend beta API: `.\venv\Scripts\python.exe -m app.scripts.verify_beta`
  - Frontend: `npm run lint`
  - Frontend: `npm run build`
- Evitar guardar datos de prueba usando `persistir_override=false` en consulta publica y pruebas de preview/calculo.

## 2. Base de datos y GIS

- Confirmar que PostGIS este activo en la base local.
- Verificar carga de capas:
  - predios
  - manzanas
  - zonas homogeneas
  - pendientes
  - riesgos
  - OTBs
- Prioridad siguiente: asociar OTB dominante por predio para busquedas mas rapidas y reportes territoriales.
- Cache agregada: `predio_otb_contexto`, refrescable con `SELECT refresh_predio_otb_contexto();`.

## 3. Backend

- Mantener endpoints publicos separados de endpoints administrativos.
- Revisar errores de validacion 422 para devolver mensajes comprensibles al frontend.
- Agregar migraciones o scripts idempotentes para columnas nuevas antes de cualquier demo en otra PC.
- Documentar payloads reales de `preview` y `calcular`.

## 4. Frontend

- Priorizar mapa como vista principal, especialmente en celular.
- Mantener panel lateral colapsable en escritorio y bandeja inferior en movil.
- Revisar que botones flotantes no tapen inputs, login ni resultado.
- Dejar busqueda publica simple:
  - codigo catastral
  - OTB
  - zona
  - opcion de ubicacion actual
- Mantener selector de mapa con opcion MapTiler y fallback OSM/CARTO.

## 5. Despliegue beta gratuita

Opcion recomendada para prueba:

- Backend y base: Render, Railway, Fly.io o Supabase/Postgres + servicio FastAPI.
- Frontend: Vercel, Netlify o Cloudflare Pages.

Para beta institucional simple:

- Frontend en Vercel/Netlify.
- Base Postgres/PostGIS en Supabase; la base local ocupa aproximadamente 415 MB y deja poco margen en el limite gratuito de 500 MB.
- Backend FastAPI en Render/Railway con variables de entorno.

## 6. Criterios de beta lista

- Login administrador funcional.
- Consulta publica funcional sin iniciar sesion.
- Busqueda de predio por codigo, zona y OTB.
- Mapa responsive en escritorio y celular.
- Calculo de avaluo sin error 422/500 para datos de ejemplo.
- Documentacion tecnica y guia de usuario final actualizadas.

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from sqlalchemy import text
from app.core.database import get_db
from app.models.predios import schemas, service

router = APIRouter(prefix="/api/v1/predios", tags=["Predios"])


@router.get("/", response_model=List[schemas.PredioResponse])
async def listar_predios(limite: int = 10, db: AsyncSession = Depends(get_db)):
    return await service.obtener_predios(db, limite=limite)


@router.post("/", response_model=schemas.PredioResponse, status_code=201)
async def crear_predio(predio: schemas.PredioCreate, db: AsyncSession = Depends(get_db)):
    """Crea un nuevo predio vinculándolo a una manzana y estado"""
    return await service.crear_predio(db, predio)


@router.get("/capa-mapa")
async def obtener_capa_mapa(
    limite: int = Query(500, ge=1, le=5000),
    db: AsyncSession = Depends(get_db)
):
    """
    Retorna predios desde staging como GeoJSON para el mapa.
    Compatible con la columna 'geometry' (geopandas) o 'geom' (ogr2ogr).
    """
    try:
        # Detectar nombre de columna geométrica
        detect_sql = text("""
            SELECT f_geometry_column 
            FROM geometry_columns 
            WHERE f_table_name = 'staging_predios' 
            LIMIT 1
        """)
        geom_result = await db.execute(detect_sql)
        geom_col = geom_result.scalar() or 'geometry'

        # Detectar si existe la columna COD_SIFCA o alguna similar
        cols_sql = text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'staging_predios'
            AND column_name IN ('COD_SIFCA', 'cod_sifca', 'cod_cat', 'codigo_catastral', 'codigo')
            LIMIT 1
        """)
        cod_result = await db.execute(cols_sql)
        cod_col = cod_result.scalar() or 'id'

        sql = text(f"""
            SELECT 
                id as id_predio, 
                "{cod_col}" as codigo_catastral,
                ST_AsGeoJSON(
                    ST_Transform(ST_SetSRID({geom_col}, 32719), 4326)
                ) as geojson 
            FROM staging_predios 
            WHERE {geom_col} IS NOT NULL
            LIMIT :limite
        """)

        result = await db.execute(sql, {"limite": limite})

        capa = []
        for row in result.fetchall():
            capa.append({
                "id_predio": str(row.id_predio),
                "codigo_catastral": row.codigo_catastral,
                "geojson": row.geojson
            })

        return capa

    except Exception as e:
        print(f"🔥 ERROR EN SQL: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/capa-mapa-oficial")
async def obtener_capa_oficial(
    limite: int = Query(500, ge=1, le=5000),
    db: AsyncSession = Depends(get_db)
):
    """
    Retorna predios desde la tabla OFICIAL (después de transferir).
    Usa esta en producción en lugar de capa-mapa.
    """
    try:
        sql = text("""
            SELECT 
                p.id_predio,
                p.codigo_catastral,
                p.superficie_mensura,
                p.direccion,
                ST_AsGeoJSON(ST_Transform(p.geom, 4326)) as geojson
            FROM predio p
            WHERE p.geom IS NOT NULL AND p.activo = true
            LIMIT :limite
        """)

        result = await db.execute(sql, {"limite": limite})

        capa = []
        for row in result.fetchall():
            capa.append({
                "id_predio": str(row.id_predio),
                "codigo_catastral": row.codigo_catastral,
                "superficie_mensura": float(row.superficie_mensura),
                "direccion": row.direccion,
                "geojson": row.geojson
            })

        return capa

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

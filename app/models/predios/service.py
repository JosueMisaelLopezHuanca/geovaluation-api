import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.models.predios.models import Predio
from app.models.predios import schemas

async def obtener_predios(db: AsyncSession, limite: int = 10):
    query = select(Predio).limit(limite)
    resultado = await db.execute(query)
    return resultado.scalars().all()

async def crear_predio(db: AsyncSession, predio_in: schemas.PredioCreate):
    geojson_str = json.dumps(predio_in.geom)
    
    nuevo_predio = Predio(
        id_manzana=predio_in.id_manzana,
        id_estado_predio=predio_in.id_estado_predio,
        codigo_catastral=predio_in.codigo_catastral,
        superficie_mensura=predio_in.superficie_mensura,
        direccion=predio_in.direccion,
        
        # LA MAGIA DEFINITIVA: 
        # 1. Lee el GeoJSON
        # 2. Le asigna el SRID 4326 (GPS)
        # 3. Lo transforma a SRID 32719 (Metros - La Paz)
        # 4. Lo convierte a MultiPolygon para que encaje perfecto en la tabla.
        geom=func.ST_Multi(
            func.ST_Transform(
                func.ST_SetSRID(func.ST_GeomFromGeoJSON(geojson_str), 4326), 
                32719
            )
        )
    )
    
    db.add(nuevo_predio)
    await db.commit()
    await db.refresh(nuevo_predio)
    return nuevo_predio
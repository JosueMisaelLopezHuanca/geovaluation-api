from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.models.avaluos.models import AvaluoPredio
from app.models.avaluos import schemas


async def calcular_y_guardar_avaluo(db: AsyncSession, avaluo_in: schemas.AvaluoCreate):
    # 1. Obtenemos IDs reales de tu BD
    gestion = await db.execute(text("SELECT id_gestion FROM gestion WHERE anio = 2026 LIMIT 1"))
    id_gestion = gestion.scalar()

    usuario = await db.execute(text("SELECT id_usuario FROM usuario WHERE nombre_usuario = 'admin' LIMIT 1"))
    id_usuario = usuario.scalar()

    # 2. Detectar columna geométrica de staging
    detect_geom = await db.execute(text("""
        SELECT f_geometry_column FROM geometry_columns
        WHERE f_table_name = :tabla LIMIT 1
    """), {"tabla": "staging_riesgos"})
    gcol_r = detect_geom.scalar() or 'geometry'

    detect_geom2 = await db.execute(text("""
        SELECT f_geometry_column FROM geometry_columns
        WHERE f_table_name = :tabla LIMIT 1
    """), {"tabla": "staging_pendientes"})
    gcol_p = detect_geom2.scalar() or 'geometry'

    # 3. CONSULTA ESPACIAL AVANZADA
    sql_consulta = text(f"""
        SELECT 
            p.superficie_mensura,
            COALESCE(r."DN", 1) as riesgo_dn,
            COALESCE(pen."DN", 1) as pendiente_dn,
            ST_AsGeoJSON(ST_Transform(p.geom, 4326)) as geojson
        FROM predio p
        LEFT JOIN staging_riesgos r ON ST_Intersects(p.geom, r.{gcol_r})
        LEFT JOIN staging_pendientes pen ON ST_Intersects(p.geom, pen.{gcol_p})
        WHERE p.id_predio = :id_predio
        LIMIT 1
    """)

    result = await db.execute(sql_consulta, {"id_predio": avaluo_in.id_predio})
    datos = result.fetchone()

    if not datos:
        raise Exception("El predio no existe en la base de datos oficial")
    superficie, riesgo_dn, pendiente_dn, geojson = datos

    # 4. LÓGICA DE NEGOCIO
    f_riesgo = 1.0 - (riesgo_dn * 0.1)
    f_pendiente = 1.0 - (pendiente_dn * 0.1)

    valor_m2 = avaluo_in.valor_base_m2 * f_riesgo * f_pendiente
    monto_final = float(superficie) * valor_m2

    # 5. GUARDADO
    nuevo_avaluo = AvaluoPredio(
        id_gestion=id_gestion,
        id_predio=avaluo_in.id_predio,
        valor_terreno=monto_final,
        valor_total=monto_final,
        base_imponible=monto_final,
        usuario_creador_id=id_usuario,
        estado="PENDIENTE",
        parametros_utilizados={
            "valor_base": avaluo_in.valor_base_m2,
            "riesgo_dn": riesgo_dn,
            "pendiente_dn": pendiente_dn,
            "fuente_espacial": "staging_layers_v2"
        }
    )

    db.add(nuevo_avaluo)
    await db.commit()
    await db.refresh(nuevo_avaluo)

    # Datos extra para el frontend
    nuevo_avaluo.riesgo_dn = riesgo_dn
    nuevo_avaluo.pendiente_dn = pendiente_dn
    nuevo_avaluo.superficie = float(superficie)
    nuevo_avaluo.geojson = geojson

    return nuevo_avaluo

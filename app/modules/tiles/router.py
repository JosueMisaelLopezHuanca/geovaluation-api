from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.tiles.service import get_tile

router = APIRouter(prefix="/tiles", tags=["Tiles"])


@router.get("/{z}/{x}/{y}.pbf")
async def tile(z: int, x: int, y: int, db: AsyncSession = Depends(get_db)):
    tile_data = await get_tile(db, z, x, y)

    return Response(
        content=tile_data,
        media_type="application/x-protobuf"
    )
"""Building/meter directory + raw readings lookup."""
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Building, Meter, Reading
from ..schemas import BuildingOut, ReadingOut

router = APIRouter(prefix="/api", tags=["meters"])


@router.get("/buildings", response_model=list[BuildingOut])
async def list_buildings(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Building))
    return result.scalars().all()


@router.get("/buildings/{building_id}/meters")
async def list_meters(building_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Meter).where(Meter.building_id == building_id))
    meters = result.scalars().all()
    return [{"id": m.id, "label": m.label, "circuit_type": m.circuit_type, "external_id": m.external_id} for m in meters]


@router.get("/meters/{meter_id}/readings", response_model=list[ReadingOut])
async def get_readings(
    meter_id: int,
    hours: float = Query(24, gt=0, le=24 * 30),
    db: AsyncSession = Depends(get_db),
):
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    result = await db.execute(
        select(Reading).where(Reading.meter_id == meter_id, Reading.ts >= since).order_by(Reading.ts)
    )
    return result.scalars().all()

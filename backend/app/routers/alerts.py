"""Alert feed + acknowledgement workflow."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Alert
from ..schemas import AlertOut

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertOut])
async def list_alerts(
    unacknowledged_only: bool = Query(False),
    limit: int = Query(50, le=500),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Alert).order_by(Alert.ts.desc()).limit(limit)
    if unacknowledged_only:
        stmt = stmt.where(Alert.acknowledged == False)  # noqa: E712
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/{alert_id}/ack", response_model=AlertOut)
async def acknowledge(alert_id: int, db: AsyncSession = Depends(get_db)):
    await db.execute(update(Alert).where(Alert.id == alert_id).values(acknowledged=True))
    await db.commit()
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    return result.scalar_one()

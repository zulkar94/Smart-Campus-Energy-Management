"""Aggregate KPIs, leaderboard, digital-twin heatmap, live websocket feed,
and a lightweight peak-demand forecast."""
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Building, Meter, Reading
from ..schemas import KPISummary, LeaderboardEntry, HeatmapCell
from ..kpi import integrate_kwh, cost_usd, co2_kg, peak_demand
from ..websocket_manager import manager

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


async def _readings_for_building(db: AsyncSession, building_id: int, since: datetime) -> list[tuple[datetime, float]]:
    result = await db.execute(
        select(Reading.ts, Reading.power_kw)
        .join(Meter, Meter.id == Reading.meter_id)
        .where(Meter.building_id == building_id, Reading.ts >= since)
        .order_by(Reading.ts)
    )
    return [(r.ts, r.power_kw) for r in result.all()]


async def _readings_campus_wide(db: AsyncSession, since: datetime) -> list[tuple[datetime, float]]:
    result = await db.execute(select(Reading.ts, Reading.power_kw).where(Reading.ts >= since).order_by(Reading.ts))
    return [(r.ts, r.power_kw) for r in result.all()]


@router.get("/summary", response_model=KPISummary)
async def summary(hours: float = Query(24, gt=0, le=720), db: AsyncSession = Depends(get_db)):
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    readings = await _readings_campus_wide(db, since)
    kw, ts = peak_demand(readings)
    return KPISummary(
        window_hours=hours,
        total_kwh=round(integrate_kwh(readings), 2),
        total_cost_usd=round(cost_usd(readings), 2),
        total_co2_kg=round(co2_kg(readings), 2),
        peak_demand_kw=round(kw, 2),
        peak_demand_ts=ts,
    )


@router.get("/leaderboard", response_model=list[LeaderboardEntry])
async def leaderboard(hours: float = Query(24, gt=0, le=720), db: AsyncSession = Depends(get_db)):
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    buildings = (await db.execute(select(Building))).scalars().all()
    days = hours / 24.0

    entries = []
    for b in buildings:
        readings = await _readings_for_building(db, b.id, since)
        kwh = integrate_kwh(readings)
        kwh_per_m2 = kwh / b.floor_area_m2 if b.floor_area_m2 else 0.0
        baseline = b.baseline_kwh_per_m2_day * days
        perf_pct = ((kwh_per_m2 - baseline) / baseline * 100) if baseline else 0.0
        entries.append(LeaderboardEntry(
            building_id=b.id,
            building_name=b.name,
            kwh_per_m2=round(kwh_per_m2, 3),
            baseline_kwh_per_m2=round(baseline, 3),
            performance_pct=round(perf_pct, 1),
            co2_kg=round(co2_kg(readings), 2),
        ))
    # best performers (most negative = biggest savings vs baseline) first
    entries.sort(key=lambda e: e.performance_pct)
    return entries


@router.get("/heatmap", response_model=list[HeatmapCell])
async def heatmap(db: AsyncSession = Depends(get_db)):
    """Current per-building load intensity — feeds the digital-twin campus map."""
    since = datetime.now(timezone.utc) - timedelta(minutes=15)
    buildings = (await db.execute(select(Building))).scalars().all()

    cells = []
    for b in buildings:
        readings = await _readings_for_building(db, b.id, since)
        current_kw = readings[-1][1] if readings else 0.0
        intensity = current_kw / b.floor_area_m2 if b.floor_area_m2 else 0.0
        baseline_kw_per_m2 = b.baseline_kwh_per_m2_day / 24.0
        if intensity > baseline_kw_per_m2 * 1.5:
            status = "critical"
        elif intensity > baseline_kw_per_m2 * 1.15:
            status = "elevated"
        else:
            status = "normal"
        cells.append(HeatmapCell(
            building_id=b.id, building_name=b.name,
            intensity_kw_per_m2=round(intensity, 4), status=status,
        ))
    return cells


@router.get("/forecast/{building_id}")
async def forecast(building_id: int, db: AsyncSession = Depends(get_db)):
    """Naive linear-trend forecast of the next hour's peak demand from the last
    2 hours of samples. Good enough to flag 'you're about to blow past your
    demand-charge threshold' — swap in Prophet/ARIMA for production accuracy."""
    since = datetime.now(timezone.utc) - timedelta(hours=2)
    readings = await _readings_for_building(db, building_id, since)
    if len(readings) < 5:
        return {"forecast_kw": None, "warning": False, "reason": "insufficient recent data"}

    xs = [(t - readings[0][0]).total_seconds() for t, _ in readings]
    ys = [p for _, p in readings]
    n = len(xs)
    mean_x, mean_y = sum(xs) / n, sum(ys) / n
    denom = sum((x - mean_x) ** 2 for x in xs) or 1e-6
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denom
    intercept = mean_y - slope * mean_x

    next_hour_x = xs[-1] + 3600
    forecast_kw = max(0.0, slope * next_hour_x + intercept)

    hist_since = datetime.now(timezone.utc) - timedelta(days=30)
    hist_readings = await _readings_for_building(db, building_id, hist_since)
    hist_peak, _ = peak_demand(hist_readings) if hist_readings else (0.0, None)

    from ..config import get_settings
    margin = get_settings().peak_demand_forecast_margin
    return {
        "forecast_kw": round(forecast_kw, 2),
        "historical_peak_kw": round(hist_peak, 2),
        "warning": hist_peak > 0 and forecast_kw >= hist_peak * margin,
    }


@router.websocket("/ws/live")
async def ws_live(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()  # client doesn't need to send anything; keeps connection alive
    except WebSocketDisconnect:
        manager.disconnect(ws)

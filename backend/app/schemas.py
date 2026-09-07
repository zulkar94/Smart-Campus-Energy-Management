"""Pydantic response/request models — kept separate from ORM models so API
contracts don't silently change when the DB schema does."""
from pydantic import BaseModel
from datetime import datetime


class ReadingOut(BaseModel):
    meter_id: int
    ts: datetime
    power_kw: float
    is_anomaly: bool

    class Config:
        from_attributes = True


class BuildingOut(BaseModel):
    id: int
    name: str
    building_type: str
    floor_area_m2: float

    class Config:
        from_attributes = True


class KPISummary(BaseModel):
    window_hours: float
    total_kwh: float
    total_cost_usd: float
    total_co2_kg: float
    peak_demand_kw: float
    peak_demand_ts: datetime | None = None


class LeaderboardEntry(BaseModel):
    building_id: int
    building_name: str
    kwh_per_m2: float
    baseline_kwh_per_m2: float
    performance_pct: float   # negative = better than baseline
    co2_kg: float


class HeatmapCell(BaseModel):
    building_id: int
    building_name: str
    intensity_kw_per_m2: float
    status: str  # normal, elevated, critical


class AlertOut(BaseModel):
    id: int
    meter_id: int
    ts: datetime
    severity: str
    kind: str
    message: str
    recommendation: str
    acknowledged: bool

    class Config:
        from_attributes = True


class MQTTReading(BaseModel):
    """Payload shape expected on campus/{building}/{meter}/power"""
    power_kw: float
    ts: datetime | None = None

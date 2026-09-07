"""KPI math. Pure functions — no DB/IO — so they're trivially unit-testable
and reusable in both the API and the offline simulator/reports.

kWh from a power (kW) time series: trapezoidal integration over elapsed
seconds between consecutive samples. This is correct for irregular sampling
intervals, which real IoT meters produce (dropped packets, jitter, etc).
"""
from datetime import datetime, timezone
from .config import get_settings

settings = get_settings()


def integrate_kwh(readings: list[tuple[datetime, float]]) -> float:
    """readings: sorted list of (timestamp, power_kw). Returns energy in kWh."""
    if len(readings) < 2:
        return 0.0
    total = 0.0
    for (t0, p0), (t1, p1) in zip(readings, readings[1:]):
        dt_hours = (t1 - t0).total_seconds() / 3600.0
        if dt_hours <= 0 or dt_hours > 1.0:
            # gap too large (meter offline) — skip rather than fabricate energy
            continue
        total += dt_hours * (p0 + p1) / 2.0
    return total


def _is_peak_hour(ts: datetime) -> bool:
    hour = ts.astimezone(timezone.utc).hour
    return settings.peak_hours_start <= hour < settings.peak_hours_end


def cost_usd(readings: list[tuple[datetime, float]]) -> float:
    """Time-of-use billing: integrate separately for peak vs off-peak windows."""
    if len(readings) < 2:
        return 0.0
    total = 0.0
    for (t0, p0), (t1, p1) in zip(readings, readings[1:]):
        dt_hours = (t1 - t0).total_seconds() / 3600.0
        if dt_hours <= 0 or dt_hours > 1.0:
            continue
        kwh = dt_hours * (p0 + p1) / 2.0
        rate = settings.rate_peak_per_kwh if _is_peak_hour(t0) else settings.rate_offpeak_per_kwh
        total += kwh * rate
    return total


def co2_kg(readings: list[tuple[datetime, float]]) -> float:
    """Grid carbon intensity varies with time of day (peaker plants during the day)."""
    if len(readings) < 2:
        return 0.0
    total = 0.0
    for (t0, p0), (t1, p1) in zip(readings, readings[1:]):
        dt_hours = (t1 - t0).total_seconds() / 3600.0
        if dt_hours <= 0 or dt_hours > 1.0:
            continue
        kwh = dt_hours * (p0 + p1) / 2.0
        intensity = (
            settings.grid_carbon_intensity_day_kg_per_kwh
            if _is_peak_hour(t0)
            else settings.grid_carbon_intensity_night_kg_per_kwh
        )
        total += kwh * intensity
    return total


def peak_demand(readings: list[tuple[datetime, float]]) -> tuple[float, datetime | None]:
    if not readings:
        return 0.0, None
    ts, kw = max(readings, key=lambda r: r[1])
    return kw, ts

"""Pure-function tests for kpi.py — no DB needed, runs anywhere."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timedelta, timezone
from backend.app.kpi import integrate_kwh, peak_demand


def _series(start, points):
    """points: list of (minutes_offset, kw)"""
    return [(start + timedelta(minutes=m), kw) for m, kw in points]


def test_integrate_kwh_constant_load():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    # 10 kW constant for 60 minutes = 10 kWh
    readings = _series(start, [(0, 10), (60, 10)])
    assert abs(integrate_kwh(readings) - 10.0) < 1e-6


def test_integrate_kwh_ramp():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    # ramp 0 -> 20 kW over 60 min: trapezoid = avg(0,20) * 1h = 10 kWh
    readings = _series(start, [(0, 0), (60, 20)])
    assert abs(integrate_kwh(readings) - 10.0) < 1e-6


def test_integrate_kwh_skips_large_gaps():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    # a 2-hour gap (meter offline) must not be integrated as energy
    readings = _series(start, [(0, 10), (150, 10)])  # 150 min gap > 60 min cap
    assert integrate_kwh(readings) == 0.0


def test_peak_demand_finds_max():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    readings = _series(start, [(0, 5), (10, 42), (20, 8)])
    kw, ts = peak_demand(readings)
    assert kw == 42
    assert ts == start + timedelta(minutes=10)


def test_peak_demand_empty():
    assert peak_demand([]) == (0.0, None)

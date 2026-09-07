import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timezone
from backend.app.recommender import recommend


def test_phantom_load_flagged_at_night():
    ts = datetime(2026, 1, 1, 2, 0, tzinfo=timezone.utc)  # 2am
    rec = recommend("Dorm A Room Outlets", "plug_load", ts, power_kw=3.0, baseline_kw=1.0)
    assert rec.kind == "phantom_load"
    assert rec.severity == "warning"


def test_daytime_spike_is_critical_when_extreme():
    ts = datetime(2026, 1, 1, 14, 0, tzinfo=timezone.utc)
    rec = recommend("Science Hall Main", "mains", ts, power_kw=100.0, baseline_kw=30.0)
    assert rec.kind == "spike"
    assert rec.severity == "critical"


def test_low_load_is_informational():
    ts = datetime(2026, 1, 1, 14, 0, tzinfo=timezone.utc)
    rec = recommend("Admin HVAC", "hvac", ts, power_kw=5.0, baseline_kw=10.0)
    assert rec.kind == "low_load"
    assert rec.severity == "info"

"""Turns a raw anomaly flag into a specific, actionable recommendation.

Hybrid rule + heuristic engine, not a black box — facilities staff need to
trust and act on this, so every recommendation states *why*. Rules run in
priority order; first match wins.
"""
from datetime import datetime, time
from dataclasses import dataclass


@dataclass
class Recommendation:
    severity: str   # info, warning, critical
    kind: str
    message: str
    action: str


NIGHT_START = time(22, 0)
NIGHT_END = time(6, 0)


def _is_night(ts: datetime) -> bool:
    t = ts.time()
    return t >= NIGHT_START or t <= NIGHT_END


def recommend(
    meter_label: str,
    circuit_type: str,
    ts: datetime,
    power_kw: float,
    baseline_kw: float,
) -> Recommendation:
    delta_pct = ((power_kw - baseline_kw) / baseline_kw * 100) if baseline_kw > 0 else 0.0

    # 1. Phantom / unattended load: meaningful power draw on a plug/lighting
    #    circuit during unoccupied hours.
    if _is_night(ts) and circuit_type in ("plug_load", "lighting") and power_kw > max(baseline_kw * 2, 0.5):
        return Recommendation(
            severity="warning",
            kind="phantom_load",
            message=f"{meter_label}: {power_kw:.2f} kW draw at {ts.strftime('%H:%M')} "
                    f"on a {circuit_type.replace('_',' ')} circuit, building should be unoccupied.",
            action="Send a facilities check: equipment likely left on. "
                   "If recurring nightly, add to an auto-shutoff schedule.",
        )

    # 2. HVAC running hard outside occupancy hours.
    if _is_night(ts) and circuit_type == "hvac" and delta_pct > 40:
        return Recommendation(
            severity="warning",
            kind="hvac_schedule",
            message=f"{meter_label}: HVAC load {delta_pct:.0f}% above baseline overnight.",
            action="Check the BMS setback schedule — likely running an occupied setpoint "
                   "overnight. Confirm setback triggers correctly at building close.",
        )

    # 3. Sharp spike during the day — could be legitimate (event) or a fault.
    if delta_pct > 80:
        return Recommendation(
            severity="critical" if delta_pct > 150 else "warning",
            kind="spike",
            message=f"{meter_label}: {delta_pct:.0f}% above expected load for this time of day.",
            action="If no scheduled event explains this, inspect for equipment fault "
                   "(stuck damper, compressor short-cycling) — cheaper to fix now than after a demand-charge hit.",
        )

    # 4. Sustained load below baseline could indicate a stuck-off sensor
    #    or a genuinely successful conservation effort — flagged as info, not action.
    if delta_pct < -40:
        return Recommendation(
            severity="info",
            kind="low_load",
            message=f"{meter_label}: running {abs(delta_pct):.0f}% below baseline.",
            action="Verify meter is reporting correctly. If confirmed real, "
                   "document the cause — good candidate for the savings leaderboard.",
        )

    return Recommendation(
        severity="info",
        kind="anomaly",
        message=f"{meter_label}: reading flagged as statistically unusual ({power_kw:.2f} kW).",
        action="No rule matched a specific cause — review manually if this repeats.",
    )

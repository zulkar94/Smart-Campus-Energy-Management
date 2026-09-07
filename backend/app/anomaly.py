"""Per-meter anomaly detection, streaming-friendly.

Design: one IsolationForest per meter, retrained periodically (not on every
sample — too expensive) from a rolling in-memory window. Below the minimum
sample count, falls back to a z-score rule so new meters aren't blind on day 1.

Features per sample: [power_kw, hour_of_day_sin, hour_of_day_cos, is_weekend]
— cyclical hour encoding lets the model learn "3am load is normally near-zero"
without treating hour 23 and hour 0 as far apart.
"""
import math
import statistics
from collections import deque
from datetime import datetime
from sklearn.ensemble import IsolationForest
from .config import get_settings

settings = get_settings()


def _features(ts: datetime, power_kw: float) -> list[float]:
    hour = ts.hour + ts.minute / 60.0
    return [
        power_kw,
        math.sin(2 * math.pi * hour / 24),
        math.cos(2 * math.pi * hour / 24),
        1.0 if ts.weekday() >= 5 else 0.0,
    ]


class MeterAnomalyDetector:
    def __init__(self, meter_id: int):
        self.meter_id = meter_id
        self.window: deque[tuple[datetime, float]] = deque(maxlen=settings.anomaly_window)
        self.model: IsolationForest | None = None
        self._samples_since_fit = 0
        self._retrain_every = 20

    def _zscore_check(self, power_kw: float) -> bool:
        vals = [p for _, p in self.window]
        if len(vals) < 5:
            return False
        mean = statistics.mean(vals)
        stdev = statistics.pstdev(vals) or 1e-6
        z = abs(power_kw - mean) / stdev
        return z > settings.zscore_fallback_threshold

    def update(self, ts: datetime, power_kw: float) -> bool:
        """Feed one reading, return True if it's flagged anomalous."""
        is_anomaly = False

        if len(self.window) >= settings.anomaly_min_samples:
            if self.model is None or self._samples_since_fit >= self._retrain_every:
                X = [_features(t, p) for t, p in self.window]
                self.model = IsolationForest(
                    n_estimators=100,
                    contamination=settings.anomaly_contamination,
                    random_state=42,
                )
                self.model.fit(X)
                self._samples_since_fit = 0
            pred = self.model.predict([_features(ts, power_kw)])[0]
            is_anomaly = pred == -1
            self._samples_since_fit += 1
        else:
            is_anomaly = self._zscore_check(power_kw)

        self.window.append((ts, power_kw))
        return is_anomaly


class AnomalyRegistry:
    """Keeps one detector per meter alive for the lifetime of the process."""

    def __init__(self):
        self._detectors: dict[int, MeterAnomalyDetector] = {}

    def check(self, meter_id: int, ts: datetime, power_kw: float) -> bool:
        det = self._detectors.setdefault(meter_id, MeterAnomalyDetector(meter_id))
        return det.update(ts, power_kw)


registry = AnomalyRegistry()

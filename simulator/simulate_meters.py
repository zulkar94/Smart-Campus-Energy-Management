"""IoT meter simulator — stands in for real smart meters until you wire up
actual hardware (see README "Going to real hardware").

Publishes realistic per-circuit power curves (diurnal occupancy patterns,
weekday/weekend differences, HVAC thermal lag) over MQTT, matching exactly
the meters seeded by scripts/init_db.py.

SIM_SPEEDUP compresses simulated time so a full day of TOU billing / anomaly
patterns is visible in minutes instead of 24 hours — set to 1 for real-time.
"""
import asyncio
import json
import math
import os
import random
from datetime import datetime, timedelta, timezone

import aiomqtt

MQTT_BROKER = os.environ.get("MQTT_BROKER", "mqtt")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
PUBLISH_INTERVAL_SEC = float(os.environ.get("PUBLISH_INTERVAL_SEC", "5"))
SIM_SPEEDUP = float(os.environ.get("SIM_SPEEDUP", "60"))   # 60x: 1 real sec = 1 sim min
ANOMALY_PROBABILITY = float(os.environ.get("ANOMALY_PROBABILITY", "0.015"))

# (building_slug, meter_ext_id, circuit_type, base_kw, occupancy-driven amplitude)
METERS = [
    ("lib", "lib-mains", "mains", 30, 40), ("lib", "lib-hvac", "hvac", 20, 35), ("lib", "lib-lighting", "lighting", 5, 10),
    ("sci", "sci-mains", "mains", 55, 60), ("sci", "sci-hvac", "hvac", 35, 45), ("sci", "sci-lab-equip", "plug_load", 15, 25),
    ("dorma", "dorma-mains", "mains", 20, 15), ("dorma", "dorma-plug", "plug_load", 12, 18),
    ("dormb", "dormb-mains", "mains", 20, 15), ("dormb", "dormb-plug", "plug_load", 12, 18),
    ("ath", "ath-mains", "mains", 25, 30), ("ath", "ath-hvac", "hvac", 30, 20), ("ath", "ath-lighting", "lighting", 8, 20),
    ("admin", "admin-mains", "mains", 15, 12), ("admin", "admin-hvac", "hvac", 10, 15),
]


def building_curve(building_slug: str, hour: float, is_weekend: bool) -> float:
    if building_slug in ("dorma", "dormb"):
        # dorms: low midday (classes), high evening/night, small weekend shift right
        peak_hour = 21 if not is_weekend else 23
        return 0.35 + 0.65 * math.exp(-((hour - peak_hour) % 24 - 0) ** 2 / 40)
    if building_slug == "ath":
        # athletics: two peaks — morning and evening workouts
        return 0.25 + 0.5 * math.exp(-((hour - 7) % 24) ** 2 / 8) + 0.5 * math.exp(-((hour - 18) % 24) ** 2 / 8)
    # academic / lab / admin: weekday 8-18 occupancy bell curve, quiet on weekends
    weekday_factor = 0.3 if is_weekend else 1.0
    return (0.15 + 0.85 * math.exp(-((hour - 13) % 24 - 0) ** 2 / 18)) * weekday_factor


async def publish_loop():
    sim_start = datetime.now(timezone.utc)
    wall_start = asyncio.get_event_loop().time()

    async with aiomqtt.Client(MQTT_BROKER, port=MQTT_PORT) as client:
        print(f"[simulator] connected to {MQTT_BROKER}:{MQTT_PORT}, speedup={SIM_SPEEDUP}x")
        while True:
            elapsed_wall = asyncio.get_event_loop().time() - wall_start
            sim_now = sim_start + timedelta(seconds=elapsed_wall * SIM_SPEEDUP)
            hour = sim_now.hour + sim_now.minute / 60.0
            is_weekend = sim_now.weekday() >= 5

            for building_slug, meter_ext_id, circuit_type, base_kw, amplitude in METERS:
                factor = building_curve(building_slug, hour, is_weekend)
                power = base_kw * 0.2 + amplitude * factor
                power *= random.uniform(0.94, 1.06)  # sensor noise

                if random.random() < ANOMALY_PROBABILITY:
                    kind = random.choice(["spike", "phantom_night", "drop"])
                    if kind == "spike":
                        power *= random.uniform(1.8, 2.6)
                    elif kind == "phantom_night":
                        power = max(power, amplitude * random.uniform(0.6, 1.0))
                    else:
                        power *= random.uniform(0.1, 0.3)

                power = max(0.0, round(power, 3))
                topic = f"campus/{building_slug}/{meter_ext_id}/power"
                payload = json.dumps({"power_kw": power, "ts": sim_now.isoformat()})
                await client.publish(topic, payload.encode())

            await asyncio.sleep(PUBLISH_INTERVAL_SEC)


if __name__ == "__main__":
    asyncio.run(publish_loop())

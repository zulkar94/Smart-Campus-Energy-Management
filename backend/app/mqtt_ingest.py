"""MQTT -> DB -> anomaly check -> alert -> websocket broadcast, in one pipeline.

Topic contract: campus/{building_external_id}/{meter_external_id}/power
Payload: {"power_kw": float, "ts": iso8601 (optional, defaults to now)}
"""
import asyncio
import json
import logging
import statistics
from datetime import datetime, timezone

import aiomqtt
from sqlalchemy import select

from .config import get_settings
from .database import AsyncSessionLocal
from .models import Meter, Building, Reading, Alert
from .anomaly import registry
from .recommender import recommend
from .websocket_manager import manager

log = logging.getLogger("mqtt_ingest")
settings = get_settings()

# meter external_id -> {id, label, circuit_type, building_id, building_name, baseline_kw}
_meter_cache: dict[str, dict] = {}


async def refresh_meter_cache():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Meter, Building).join(Building))
        for meter, building in result.all():
            hourly_baseline_kw = (building.baseline_kwh_per_m2_day * building.floor_area_m2) / 24.0
            _meter_cache[meter.external_id] = {
                "id": meter.id,
                "label": meter.label,
                "circuit_type": meter.circuit_type,
                "building_id": building.id,
                "building_name": building.name,
                "baseline_kw": hourly_baseline_kw / max(len(building.meters), 1),
            }
    log.info("meter cache loaded: %d meters", len(_meter_cache))


async def _handle_reading(building_ext_id: str, meter_ext_id: str, power_kw: float, ts: datetime):
    meta = _meter_cache.get(meter_ext_id)
    if meta is None:
        log.warning("unknown meter %s — run scripts/init_db.py or check simulator config", meter_ext_id)
        return

    async with AsyncSessionLocal() as db:
        is_anomaly = registry.check(meta["id"], ts, power_kw)

        db.add(Reading(meter_id=meta["id"], ts=ts, power_kw=power_kw, is_anomaly=is_anomaly))

        alert_payload = None
        if is_anomaly:
            det = registry._detectors[meta["id"]]
            window_vals = [p for _, p in det.window]
            baseline = statistics.mean(window_vals) if len(window_vals) >= 5 else meta["baseline_kw"]

            rec = recommend(meta["label"], meta["circuit_type"], ts, power_kw, baseline)
            alert = Alert(
                meter_id=meta["id"],
                ts=ts,
                severity=rec.severity,
                kind=rec.kind,
                message=rec.message,
                recommendation=rec.action,
            )
            db.add(alert)
            alert_payload = {
                "severity": rec.severity,
                "kind": rec.kind,
                "message": rec.message,
                "recommendation": rec.action,
                "building": meta["building_name"],
                "meter": meta["label"],
            }

        await db.commit()

    await manager.broadcast({
        "type": "reading",
        "building_id": meta["building_id"],
        "building_name": meta["building_name"],
        "meter_id": meta["id"],
        "meter_label": meta["label"],
        "ts": ts.isoformat(),
        "power_kw": power_kw,
        "is_anomaly": is_anomaly,
    })
    if alert_payload:
        await manager.broadcast({"type": "alert", **alert_payload})


async def run_mqtt_listener():
    await refresh_meter_cache()
    refresh_counter = 0

    while True:  # reconnect loop — IoT brokers drop connections, this must not die
        try:
            async with aiomqtt.Client(settings.mqtt_broker, port=settings.mqtt_port) as client:
                await client.subscribe(f"{settings.mqtt_topic_root}/+/+/power")
                log.info("subscribed to %s/+/+/power on %s:%s", settings.mqtt_topic_root, settings.mqtt_broker, settings.mqtt_port)
                async for message in client.messages:
                    parts = str(message.topic).split("/")
                    if len(parts) != 4:
                        continue
                    _, building_ext_id, meter_ext_id, _ = parts
                    try:
                        payload = json.loads(message.payload)
                        power_kw = float(payload["power_kw"])
                        ts = datetime.fromisoformat(payload["ts"]) if payload.get("ts") else datetime.now(timezone.utc)
                    except (json.JSONDecodeError, KeyError, ValueError) as e:
                        log.warning("bad payload on %s: %s", message.topic, e)
                        continue

                    await _handle_reading(building_ext_id, meter_ext_id, power_kw, ts)

                    refresh_counter += 1
                    if refresh_counter % 500 == 0:  # cheap periodic resync for new meters
                        await refresh_meter_cache()

        except aiomqtt.MqttError as e:
            log.error("MQTT connection lost (%s), retrying in 5s", e)
            await asyncio.sleep(5)

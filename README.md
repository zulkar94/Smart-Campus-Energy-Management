# Smart Campus Energy Management

Real-time IoT energy dashboard for a campus: live meter ingestion, anomaly
detection, actionable recommendations, cost/CO₂ tracking, building
leaderboard, digital-twin heatmap, and peak-demand forecasting.

![status](https://img.shields.io/badge/status-demo--ready-6FCF97)
![python](https://img.shields.io/badge/python-3.12-blue)
![license](https://img.shields.io/badge/license-MIT-lightgrey)

## Why this architecture

| Decision | Reasoning |
|---|---|
| **FastAPI + async SQLAlchemy** | Native WebSocket support for the live dashboard; async DB driver so MQTT ingestion never blocks HTTP requests. |
| **TimescaleDB (Postgres extension)** | `readings` is a hypertable — same SQL you already know, but time-range queries stay fast at millions of rows. Falls back to plain Postgres if the extension isn't available. |
| **MQTT (Mosquitto)** | The de facto protocol for real IoT meters (Shelly, ESP32 energy monitors, most commercial submeters speak MQTT or bridge to it easily). Swapping the simulator for real hardware means pointing real devices at the same broker/topic scheme — zero backend changes. |
| **IsolationForest per meter** | Unsupervised — no labeled "this was an anomaly" training data needed, which real campuses never have on day one. One model per meter (not global) because a library and a dorm have completely different normal patterns. |
| **Rule-based recommender on top of ML** | The ML model says *"this is unusual"*; it can't say *why* or *what to do*. A hybrid layer maps anomaly context (circuit type, time of day, magnitude) to a specific, trustable action — facilities staff act on recommendations, not anomaly scores. |
| **kWh/cost/CO₂ computed from raw power, never stored** | If your utility changes rates or you correct a TOU schedule, historical costs update correctly rather than being frozen at ingest time. |

## Architecture

```
IoT meters / simulator
        │  MQTT  (campus/{building}/{meter}/power)
        ▼
  Mosquitto broker
        │
        ▼
 mqtt_ingest.py  ──►  TimescaleDB (readings, alerts)
        │                    ▲
        │  anomaly.py        │  REST (FastAPI)
        │  recommender.py    │
        ▼                    │
  websocket_manager  ────────┴──► Dashboard (HTML/JS/Chart.js)
   (broadcasts live readings + alerts)
```

## Quick start (Docker — recommended)

```bash
git clone <your-fork-url> smart-campus-energy
cd smart-campus-energy
docker compose up --build
```

Open **http://localhost:8000** — the simulator starts publishing immediately
(`SIM_SPEEDUP=60` in `docker-compose.yml` compresses a day into ~24 real
minutes so you see the full diurnal pattern, TOU billing shift, and injected
anomalies without waiting).

Stop with `docker compose down`. Add `-v` to also wipe the database volume.

## Running locally without Docker

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# needs a local Postgres (TimescaleDB image recommended) and Mosquitto broker running
cp .env.example .env   # edit DATABASE_URL / MQTT_BROKER to point at localhost

python -m scripts.init_db
uvicorn backend.app.main:app --reload &
python simulator/simulate_meters.py
```

## Going to real hardware

Nothing in the backend needs to change. Point real meters (or a Node-RED /
Home Assistant bridge) at the same broker and publish to:

```
campus/{building_external_id}/{meter_external_id}/power
{"power_kw": 12.4, "ts": "2026-09-04T14:03:00Z"}
```

Register the building/meter in the DB (see `scripts/init_db.py` for the
shape) with matching `external_id` values, then turn off `simulator` in
`docker-compose.yml`.

Recommended real hardware for a pilot: **Shelly Pro EM / 3EM** (native MQTT,
CT clamps, no rewiring) or any submeter behind a **Node-RED** MQTT bridge.

## KPI formulas

- **kWh** — trapezoidal integration of power (kW) over time, gap-aware (skips
  integration across meter-offline gaps >1h so downtime isn't billed as usage).
- **Cost** — time-of-use: `kWh_peak × rate_peak + kWh_offpeak × rate_offpeak`,
  configurable window/rates in `.env`.
- **CO₂e** — `kWh × grid_carbon_intensity(hour)`, higher during the day
  (peaker plants), lower overnight (baseload) — edit factors for your grid
  region ([electricityMaps](https://app.electricitymaps.com/map) has real
  regional numbers if you want to swap in accurate figures).
- **Peak demand** — max instantaneous kW in the window; this is what utility
  demand charges bill on, separately from total kWh.
- **Leaderboard performance** — `(actual kWh/m² − baseline kWh/m²) / baseline`,
  ranked best-to-worst; baseline is per-building and editable per your own
  historical data in `scripts/init_db.py`.

## Repository layout

```
backend/app/
  config.py          all tunables (tariffs, carbon factors, ML thresholds)
  models.py          SQLAlchemy: Building, Meter, Reading, Alert
  kpi.py             pure-function energy/cost/CO2 math (unit tested)
  anomaly.py         per-meter IsolationForest + z-score fallback
  recommender.py     anomaly context -> actionable recommendation
  mqtt_ingest.py      MQTT -> DB -> anomaly -> alert -> websocket pipeline
  websocket_manager.py
  routers/           REST + WebSocket endpoints
simulator/           synthetic IoT meter publisher (realistic diurnal curves)
frontend/            single-page dashboard (HTML/CSS/vanilla JS + Chart.js)
scripts/init_db.py   schema + hypertable setup + seed campus data
tests/               pytest, no DB required (kpi.py and recommender.py are pure functions)
```

## Testing

```bash
pip install -r requirements.txt
pytest tests/ -v
```

## Publishing to GitHub

```bash
cd smart-campus-energy
git init
git add .
git commit -m "Initial commit: Smart Campus Energy Management"
git branch -M main
git remote add origin https://github.com/<your-username>/smart-campus-energy.git
git push -u origin main
```

`.env` is gitignored — don't commit real utility rates or credentials if
they're sensitive; `.env.example` documents the shape instead.

## Extending

- **Weather normalization**: pull outdoor temp (e.g. Open-Meteo, no API key
  needed) and add degree-days as an `anomaly.py` feature — separates "hot day
  drove HVAC load" from a genuine fault.
- **Solar/battery**: add a `Meter.circuit_type == "generation"` and subtract
  from `mains` in `kpi.py` for net-metering support.
- **Notifications**: `recommender.Recommendation` is already structured for a
  Slack/email webhook — wire one into `mqtt_ingest._handle_reading`.
- **Multi-campus**: add a `Campus` parent to `Building` and scope queries;
  the schema was kept flat deliberately so this is a small, additive change.

## License

MIT — see [LICENSE](LICENSE).

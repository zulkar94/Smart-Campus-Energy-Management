"""Creates tables, converts `readings` to a TimescaleDB hypertable, and seeds
a realistic campus: 6 buildings x 2-4 meters each. Run once per environment:

    python -m scripts.init_db
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text
from backend.app.database import engine, Base, AsyncSessionLocal
from backend.app.models import Building, Meter

CAMPUS = [
    # (name, type, area_m2, baseline_kwh/m2/day, meters: [(external_id, label, circuit_type)])
    ("Library", "academic", 4200, 0.85, [
        ("lib-mains", "Main Feed", "mains"),
        ("lib-hvac", "HVAC Plant", "hvac"),
        ("lib-lighting", "Lighting", "lighting"),
    ]),
    ("Science Hall", "lab", 6100, 1.6, [
        ("sci-mains", "Main Feed", "mains"),
        ("sci-hvac", "HVAC Plant", "hvac"),
        ("sci-lab-equip", "Lab Equipment", "plug_load"),
    ]),
    ("Dorm A", "dorm", 3800, 0.55, [
        ("dorma-mains", "Main Feed", "mains"),
        ("dorma-plug", "Room Outlets", "plug_load"),
    ]),
    ("Dorm B", "dorm", 3800, 0.55, [
        ("dormb-mains", "Main Feed", "mains"),
        ("dormb-plug", "Room Outlets", "plug_load"),
    ]),
    ("Athletics Center", "athletic", 5200, 1.1, [
        ("ath-mains", "Main Feed", "mains"),
        ("ath-hvac", "HVAC/Pool Plant", "hvac"),
        ("ath-lighting", "Arena Lighting", "lighting"),
    ]),
    ("Admin Building", "admin", 2100, 0.6, [
        ("admin-mains", "Main Feed", "mains"),
        ("admin-hvac", "HVAC Plant", "hvac"),
    ]),
]


async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # TimescaleDB hypertable — safe no-op if extension/table already converted.
        try:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb"))
            await conn.execute(text(
                "SELECT create_hypertable('readings', 'ts', if_not_exists => TRUE, migrate_data => TRUE)"
            ))
        except Exception as e:
            print(f"[init_db] TimescaleDB hypertable setup skipped ({e}) — plain Postgres table still works fine.")

    async with AsyncSessionLocal() as db:
        for name, btype, area, baseline, meters in CAMPUS:
            building = Building(name=name, building_type=btype, floor_area_m2=area, baseline_kwh_per_m2_day=baseline)
            db.add(building)
            await db.flush()  # get building.id
            for ext_id, label, circuit in meters:
                db.add(Meter(external_id=ext_id, label=label, building_id=building.id, circuit_type=circuit))
        await db.commit()

    print(f"[init_db] seeded {len(CAMPUS)} buildings.")


if __name__ == "__main__":
    asyncio.run(main())

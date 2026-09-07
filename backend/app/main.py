"""Entrypoint. Boots the API, serves the dashboard, and runs the MQTT
ingestion pipeline as a background task inside the same event loop."""
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .routers import meters, dashboard, alerts
from .mqtt_ingest import run_mqtt_listener

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(run_mqtt_listener())
    yield
    task.cancel()


app = FastAPI(title="Smart Campus Energy Management", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(meters.router)
app.include_router(dashboard.router)
app.include_router(alerts.router)
app.mount("/", StaticFiles(directory="/app/frontend", html=True), name="frontend")

"""Central config. All tunables live here — edit for your campus, no code changes needed."""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # --- Database ---
    database_url: str = "postgresql+asyncpg://campus:campus@db:5432/campus_energy"

    # --- MQTT (IoT ingestion) ---
    mqtt_broker: str = "mqtt"
    mqtt_port: int = 1883
    mqtt_topic_root: str = "campus"  # campus/{building_id}/{meter_id}/power

    # --- Tariff (edit to match your utility contract) ---
    rate_offpeak_per_kwh: float = 0.11   # $/kWh, 22:00-07:00
    rate_peak_per_kwh: float = 0.27      # $/kWh, 07:00-22:00
    peak_hours_start: int = 7
    peak_hours_end: int = 22
    demand_charge_per_kw: float = 14.5   # $/kW of monthly peak demand (common utility structure)

    # --- Carbon ---
    grid_carbon_intensity_day_kg_per_kwh: float = 0.38   # higher: gas/coal peaker plants online
    grid_carbon_intensity_night_kg_per_kwh: float = 0.21  # lower: baseload/nuclear/wind

    # --- Anomaly detection ---
    anomaly_min_samples: int = 30        # samples needed before IsolationForest trains
    anomaly_window: int = 288            # rolling window per meter (288 = 24h at 5-min intervals)
    anomaly_contamination: float = 0.05  # expected fraction of outliers
    zscore_fallback_threshold: float = 3.0

    # --- Alerts ---
    peak_demand_forecast_margin: float = 0.9  # warn at 90% of building's historical peak

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()

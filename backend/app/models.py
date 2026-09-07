"""ORM models.

Building -> Meter -> Reading (1:N:N). Reading stores instantaneous power (kW);
kWh/cost/CO2 are derived at query time in kpi.py, never stored — keeps the
hypertable append-only and avoids drift if tariffs change retroactively.
"""
from sqlalchemy import String, Float, ForeignKey, DateTime, Integer, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime, timezone
from .database import Base


class Building(Base):
    __tablename__ = "buildings"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    building_type: Mapped[str] = mapped_column(String(60), default="academic")  # academic, dorm, lab, athletic, admin
    floor_area_m2: Mapped[float] = mapped_column(Float, default=1000.0)
    baseline_kwh_per_m2_day: Mapped[float] = mapped_column(Float, default=0.9)  # for leaderboard normalization

    meters: Mapped[list["Meter"]] = relationship(back_populates="building", cascade="all, delete-orphan")


class Meter(Base):
    __tablename__ = "meters"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(80), unique=True)  # matches MQTT topic segment
    label: Mapped[str] = mapped_column(String(120))
    building_id: Mapped[int] = mapped_column(ForeignKey("buildings.id"))
    circuit_type: Mapped[str] = mapped_column(String(40), default="mains")  # mains, hvac, lighting, plug_load

    building: Mapped["Building"] = relationship(back_populates="meters")


class Reading(Base):
    """Hypertable candidate — see scripts/init_db.py for create_hypertable() call."""
    __tablename__ = "readings"

    id: Mapped[int] = mapped_column(primary_key=True)
    meter_id: Mapped[int] = mapped_column(ForeignKey("meters.id"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, default=lambda: datetime.now(timezone.utc))
    power_kw: Mapped[float] = mapped_column(Float)
    is_anomaly: Mapped[bool] = mapped_column(Boolean, default=False)


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    meter_id: Mapped[int] = mapped_column(ForeignKey("meters.id"))
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    severity: Mapped[str] = mapped_column(String(20))       # info, warning, critical
    kind: Mapped[str] = mapped_column(String(40))            # anomaly, peak_forecast, phantom_load
    message: Mapped[str] = mapped_column(Text)
    recommendation: Mapped[str] = mapped_column(Text)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Activity(Base):
    __tablename__ = "activities"

    id = Column(Integer, primary_key=True)
    activity_type = Column(String, nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    duration_seconds = Column(Integer, nullable=False)
    distance_meters = Column(Float, nullable=False)
    avg_hr = Column(Float, nullable=True)
    max_hr = Column(Float, nullable=True)
    elevation_gain_meters = Column(Float, nullable=True)
    source = Column(String, nullable=False)
    source_id = Column(String, nullable=True)
    dedup_key = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    source_device = Column(String, nullable=True)

    streams = relationship(
        "ActivityStream", backref="activity", cascade="all, delete-orphan"
    )
    best_efforts = relationship(
        "BestEffort", backref="activity", cascade="all, delete-orphan"
    )


class ActivityStream(Base):
    __tablename__ = "activity_streams"

    id = Column(Integer, primary_key=True)
    activity_id = Column(
        Integer, ForeignKey("activities.id", ondelete="CASCADE"), nullable=False
    )
    stream_data = Column(JSON, nullable=False)


class BestEffort(Base):
    __tablename__ = "best_efforts"

    id = Column(Integer, primary_key=True)
    distance_label = Column(String, nullable=False)
    distance_meters = Column(Float, nullable=False)
    activity_id = Column(
        Integer, ForeignKey("activities.id", ondelete="CASCADE"), nullable=False
    )
    duration_seconds = Column(Float, nullable=False)
    pace_per_km_seconds = Column(Float, nullable=False)
    achieved_at = Column(DateTime, nullable=False)


class HRZone(Base):
    __tablename__ = "hr_zones"

    id = Column(Integer, primary_key=True)
    zone_number = Column(Integer, nullable=False)
    label = Column(String, nullable=False)
    min_bpm = Column(Integer, nullable=False)
    max_bpm = Column(Integer, nullable=False)


class Exercise(Base):
    __tablename__ = "exercises"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    muscle_group = Column(String, nullable=True)
    category = Column(String, nullable=True)


class UserSettings(Base):
    __tablename__ = "user_settings"

    id = Column(Integer, primary_key=True)
    resting_hr = Column(Integer, nullable=True)
    max_hr = Column(Integer, nullable=True)
    birth_year = Column(Integer, nullable=True)
    weight_kg = Column(Float, nullable=True)
    units = Column(String, nullable=True)

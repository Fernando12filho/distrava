from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
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


# Coach tables all carry the coach_ prefix: drop_coach_tables() relies on it to
# migrate down without touching a single pre-coach table. The unused legacy
# `exercises` table is left alone for the same reason.

SESSION_STATUSES = ("planned", "done", "partial", "skipped", "moved")
SESSION_KINDS = ("run", "ride", "gym", "mobility", "rest")


def _utc_now():
    return datetime.now(timezone.utc)


class CoachExercise(Base):
    __tablename__ = "coach_exercises"

    id = Column(Integer, primary_key=True)
    # Catalog entries have a stable slug the LLM maps names onto; custom
    # exercises have none, and SQLite lets any number of NULLs share a unique column.
    slug = Column(String, unique=True, nullable=True)
    name = Column(String, nullable=False)
    category = Column(String, nullable=False)
    muscle_group = Column(String, nullable=True)
    equipment = Column(String, nullable=True)
    intensity = Column(String, nullable=False)
    activity_type = Column(String, nullable=True)
    is_custom = Column(Boolean, nullable=False, default=False)


class CoachWeek(Base):
    __tablename__ = "coach_weeks"
    __table_args__ = (CheckConstraint("strftime('%w', week_start) = '1'", name="week_starts_monday"),)

    id = Column(Integer, primary_key=True)
    week_start = Column(Date, unique=True, nullable=False)
    goal = Column(String, nullable=True)
    created_at = Column(DateTime, default=_utc_now)

    sessions = relationship(
        "CoachSession",
        back_populates="week",
        cascade="all, delete-orphan",
        order_by="(CoachSession.day_index, CoachSession.position)",
    )


# What the week shows is the session ("Chest & Triceps", "Running day"); the
# exercises live inside it. Check-ins attach to the session as a whole.
class CoachSession(Base):
    __tablename__ = "coach_sessions"
    __table_args__ = (
        CheckConstraint("day_index BETWEEN 0 AND 6", name="day_inside_week"),
        CheckConstraint(f"status IN {SESSION_STATUSES}", name="known_status"),
        CheckConstraint(f"kind IN {SESSION_KINDS}", name="known_kind"),
    )

    id = Column(Integer, primary_key=True)
    week_id = Column(Integer, ForeignKey("coach_weeks.id", ondelete="CASCADE"), nullable=False)
    day_index = Column(Integer, nullable=False)
    position = Column(Integer, nullable=False, default=0)
    kind = Column(String, nullable=False)
    focus = Column(String, nullable=False)
    status = Column(String, nullable=False, default="planned")

    week = relationship("CoachWeek", back_populates="sessions")
    items = relationship(
        "CoachSessionItem",
        backref="session",
        cascade="all, delete-orphan",
        order_by="CoachSessionItem.position",
    )
    checkins = relationship("CoachCheckin", backref="session", cascade="all, delete-orphan")


class CoachSessionItem(Base):
    __tablename__ = "coach_session_items"

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("coach_sessions.id", ondelete="CASCADE"), nullable=False)
    position = Column(Integer, nullable=False, default=0)
    exercise_id = Column(Integer, ForeignKey("coach_exercises.id"), nullable=False)
    sets = Column(Integer, nullable=True)
    reps = Column(Integer, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    distance_meters = Column(Float, nullable=True)

    exercise = relationship("CoachExercise")


class CoachCheckin(Base):
    __tablename__ = "coach_checkins"
    __table_args__ = (
        CheckConstraint("energy BETWEEN 1 AND 5", name="energy_scale"),
        CheckConstraint("effort_rpe BETWEEN 1 AND 10", name="rpe_scale"),
    )

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("coach_sessions.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=_utc_now)
    energy = Column(Integer, nullable=True)
    effort_rpe = Column(Integer, nullable=True)
    pain_location = Column(String, nullable=True)
    note = Column(Text, nullable=True)


class CoachNote(Base):
    __tablename__ = "coach_notes"

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=_utc_now)
    text = Column(Text, nullable=False)
    tags = Column(JSON, nullable=False, default=list)

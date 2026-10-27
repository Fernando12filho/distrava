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
from sqlalchemy.orm import DeclarativeBase, backref, relationship

from app import analytics


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
    # Minutes to add to start_time (stored in UTC) to get the wall clock where
    # the activity happened. CSV rows hold local time already, so theirs is 0.
    utc_offset_minutes = Column(Integer, nullable=True)
    # Session effort, 0–10 on the CR-10 scale, as the user rated it
    # (RULE-LOAD-01). Lives on the activity so a re-import, which updates rows
    # in place, keeps it.
    session_rpe = Column(Integer, nullable=True)

    @property
    def local_start_time(self):
        return analytics.to_local(self.start_time, self.utc_offset_minutes)

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
    # Highest heart rate held for a few seconds in any workout (RULE-METRIC-02),
    # learned on import. Replaces the age estimate once it is higher.
    observed_max_hr = Column(Integer, nullable=True)
    # Median of Apple Health's daily resting HR over the last 7 days of the most
    # recent export (RULE-METRIC-01), and the last day it covers.
    observed_resting_hr = Column(Integer, nullable=True)
    observed_resting_hr_on = Column(Date, nullable=True)
    # "male" / "female": set only by the user; selects the TRIMP constants.
    sex = Column(String, nullable=True)


# Kept apart from user_settings: personal facts are set only by you, while the
# coach may propose changes to this (with your OK).
class TrainingProfile(Base):
    __tablename__ = "coach_profile"

    id = Column(Integer, primary_key=True)
    runs_per_week = Column(Integer, nullable=True)
    gym_days_per_week = Column(Integer, nullable=True)
    split = Column(String, nullable=True)
    goal = Column(Text, nullable=True)
    years_running = Column(Integer, nullable=True)
    years_lifting = Column(Integer, nullable=True)


# Coach tables all carry the coach_ prefix: drop_coach_tables() relies on it to
# migrate down without touching a single pre-coach table. The unused legacy
# `exercises` table is left alone for the same reason.

SESSION_STATUSES = ("planned", "done", "partial", "skipped", "moved")
SESSION_KINDS = ("run", "ride", "gym", "mobility", "rest")
PLANNED_EFFORTS = ("easy", "hard")


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
    activity_type = Column(String, nullable=True)
    is_custom = Column(Boolean, nullable=False, default=False)


# One row per call to the AI provider, successful or not, so you can see what
# the coach uses and costs. Never the key, prompt or reply: only counts.
class CoachLlmCall(Base):
    __tablename__ = "coach_llm_calls"

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, nullable=False, default=_utc_now)
    task = Column(String, nullable=False)
    provider = Column(String, nullable=False)
    requested_model = Column(String, nullable=False)
    model = Column(String, nullable=True)
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    cache_read_tokens = Column(Integer, nullable=False, default=0)
    cache_write_tokens = Column(Integer, nullable=False, default=0)
    # Estimated from the price table at the time; None for an unpriced model.
    cost_usd = Column(Float, nullable=True)
    stop_reason = Column(String, nullable=True)
    error_kind = Column(String, nullable=True)
    request_id = Column(String, nullable=True)


class CoachWeek(Base):
    __tablename__ = "coach_weeks"
    __table_args__ = (CheckConstraint("strftime('%w', week_start) = '1'", name="week_starts_monday"),)

    id = Column(Integer, primary_key=True)
    week_start = Column(Date, unique=True, nullable=False)
    goal = Column(String, nullable=True)
    created_at = Column(DateTime, default=_utc_now)
    # D7: the factor you chose to ease back in after a break, and each changed
    # item's volume beforehand, so one undo restores the week exactly (AC-10).
    eased_factor = Column(Float, nullable=True)
    eased_snapshot = Column(JSON, nullable=True)

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
    # Plain integer, not a foreign key: SQLite here runs without FK enforcement,
    # and "wipe all data" deletes activities without knowing about the coach,
    # so readers must tolerate an id that no longer resolves.
    matched_activity_id = Column(Integer, nullable=True)
    # "easy" / "hard", set by you or proposed by the coach. Only used until the
    # session is done: then what you did decides (RULE-LOAD-04). Not a CHECK
    # constraint, since ALTER TABLE ADD COLUMN can't add one to old databases.
    planned_effort = Column(String, nullable=True)

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
    logged_sets = relationship(
        "CoachSetLog",
        backref="item",
        cascade="all, delete-orphan",
        order_by="CoachSetLog.set_number",
    )


# What was actually done, set by set. The plan's sets/reps above stay the plan;
# these rows start as a copy of it and the user corrects them, so editing the
# plan later never rewrites history.
class CoachSetLog(Base):
    __tablename__ = "coach_set_logs"
    __table_args__ = (
        CheckConstraint("reps BETWEEN 0 AND 100", name="reps_range"),
        CheckConstraint("rir BETWEEN 0 AND 10", name="rir_range"),
        CheckConstraint("weight_kg > 0", name="weight_positive"),
    )

    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey("coach_session_items.id", ondelete="CASCADE"), nullable=False)
    set_number = Column(Integer, nullable=False)
    reps = Column(Integer, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    weight_kg = Column(Float, nullable=True)
    # Reps in reserve, as the user reported it; the only input that can make a
    # set "hard" (RULE-LOAD-03).
    rir = Column(Integer, nullable=True)


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


# One chat with the coach, across weeks (#43). The newest is the one the panel
# shows; "New chat" starts another.
class CoachConversation(Base):
    __tablename__ = "coach_conversations"

    id = Column(Integer, primary_key=True)
    started_at = Column(DateTime, nullable=False, default=_utc_now)


# One coach request and what came of it. A proposal never touches the board
# until accepted (AC-04); `before` and `after` hold every session it changes
# (None = absent), so accept and undo each check the board still matches and
# write the other side back exactly (AC-10).
PROPOSAL_STATUSES = ("answer", "failed", "pending", "accepted", "discarded", "stale", "undone")


class CoachProposal(Base):
    __tablename__ = "coach_proposals"
    __table_args__ = (CheckConstraint(f"status IN {PROPOSAL_STATUSES}", name="known_proposal_status"),)

    id = Column(Integer, primary_key=True)
    week_id = Column(Integer, ForeignKey("coach_weeks.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=_utc_now)
    request = Column(Text, nullable=False)
    reply = Column(Text, nullable=True)
    status = Column(String, nullable=False)
    calls = Column(JSON, nullable=False, default=list)
    changes = Column(JSON, nullable=False, default=list)
    before = Column(JSON, nullable=True)
    after = Column(JSON, nullable=True)
    # A draft over several weeks (AC-20): {week_start: {"before", "after", "created_week"}}
    # for every week but the one asked from, accepted and undone together with it.
    other_weeks = Column(JSON, nullable=True)
    # Null only between an upgrade and the first start that groups older messages.
    conversation_id = Column(Integer, ForeignKey("coach_conversations.id", ondelete="CASCADE"), nullable=True)

    conversation = relationship(
        "CoachConversation", backref=backref("proposals", cascade="all, delete-orphan", order_by="CoachProposal.id")
    )
    week = relationship("CoachWeek", backref=backref("proposals", cascade="all, delete-orphan", order_by="CoachProposal.id"))


class CoachNote(Base):
    __tablename__ = "coach_notes"

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=_utc_now)
    text = Column(Text, nullable=False)
    tags = Column(JSON, nullable=False, default=list)

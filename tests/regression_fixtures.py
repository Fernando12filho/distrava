"""Deterministic inputs shared by the regression-net snapshot tests.

Snapshot values in those tests were captured from the code as it stood before
any coach work. If one of them changes, a metric changed — that is the point.
Never regenerate a snapshot to make a red test green without knowing why.
"""

from contextlib import contextmanager
from datetime import date, datetime, timedelta
from math import sin

from flask import template_rendered

from app import parser

HR_REST = 55
HR_MAX = 188

# Frozen "today" for anything that windows on date.today().
TODAY = date(2026, 7, 28)


class FrozenDate(date):
    @classmethod
    def today(cls):
        return cls(TODAY.year, TODAY.month, TODAY.day)


@contextmanager
def captured_context(app):
    """Yields a list that fills with the context of every template rendered."""
    contexts = []

    def record(sender, template, context, **extra):
        contexts.append(context)

    template_rendered.connect(record, app)
    try:
        yield contexts
    finally:
        template_rendered.disconnect(record, app)


def synthetic_run_stream(total_meters, base_sec_per_km, phase=0.0, sample_seconds=10):
    """A run whose pace and HR wobble sinusoidally, sampled every `sample_seconds`."""
    times, distances, hr, elevation = [0], [0.0], [130.0], [20.0]
    t = 0
    d = 0.0
    while d < total_meters:
        t += sample_seconds
        sec_per_km = base_sec_per_km + 25 * sin(t / 300 + phase)
        d = min(total_meters, d + sample_seconds * 1000.0 / sec_per_km)
        times.append(t)
        distances.append(round(d, 3))
        hr.append(round(140 + 18 * sin(t / 450 + phase) + t / 120, 1))
        elevation.append(round(20 + 6 * sin(t / 200 + phase), 2))
    return {"time": times, "distance": distances, "hr": hr, "elevation": elevation, "pace": []}


# (day offset from 2026-07-01, activity type, duration seconds, avg hr or None)
LOAD_SCHEDULE = [
    (0, "Run", 1800, 148.0),
    (1, "Strength Training", 2700, 112.0),
    (2, "Run", 2400, 152.0),
    (4, "Cycle", 3600, 135.0),
    (5, "Run", 3600, 145.0),
    (7, "Run", 1500, 162.0),
    (8, "Walk", 2400, None),
    (9, "Run", 2700, 150.0),
    (9, "Strength Training", 1800, 118.0),
    (11, "Run", 4500, 147.0),
    (14, "Run", 1800, 168.0),
    (16, "Cycle", 5400, 132.0),
    (18, "Run", 3000, 155.0),
    (19, "Run", 6000, 144.0),
    (22, "Run", 1200, 171.0),
    (23, "Strength Training", 2700, 115.0),
    (25, "Run", 3300, 151.0),
    (26, "Run", 7200, 146.0),
]

LOAD_START = date(2026, 7, 1)


def load_schedule_rows():
    rows = []
    for offset, activity_type, duration, avg_hr in LOAD_SCHEDULE:
        start = datetime.combine(LOAD_START + timedelta(days=offset), datetime.min.time()).replace(hour=7)
        rows.append(
            dict(
                activity_type=activity_type,
                start_time=start,
                end_time=start + timedelta(seconds=duration),
                duration_seconds=duration,
                distance_meters=duration * 2.6 if activity_type == "Run" else duration * 1.1,
                avg_hr=avg_hr,
                max_hr=avg_hr + 15 if avg_hr else None,
                elevation_gain_meters=None,
                source="csv",
                source_id=None,
            )
        )
    return rows


def seed_load_schedule(db_session):
    for row in load_schedule_rows():
        parser._persist_activity(db_session, **row)


def seed_best_effort_runs(db_session):
    """Two runs with streams plus a ride that must never become a PR."""
    runs = [
        ("Run", datetime(2026, 7, 3, 7, 0), synthetic_run_stream(10600.0, 300.0, phase=0.0)),
        ("Run", datetime(2026, 7, 12, 7, 0), synthetic_run_stream(22000.0, 318.0, phase=1.3)),
        ("Cycle", datetime(2026, 7, 14, 7, 0), synthetic_run_stream(30000.0, 110.0, phase=0.4)),
    ]
    for activity_type, start, stream in runs:
        duration = stream["time"][-1]
        parser._persist_activity(
            db_session,
            activity_type=activity_type,
            start_time=start,
            end_time=start + timedelta(seconds=duration),
            duration_seconds=duration,
            distance_meters=stream["distance"][-1],
            avg_hr=None,
            max_hr=None,
            elevation_gain_meters=None,
            source="gpx",
            source_id=None,
            stream_data=stream,
        )

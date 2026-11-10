"""Builds Apple Health exports in the shape real ones have, for import simulations.

Real exports can't live in the repo (they hold health data), so this writes the
same XML from a short list of workouts: Workout elements with their statistics,
per-sample Records, and the export-time UTC offset on every date.
"""

import io
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

APPLE_TYPES = {
    "Run": "HKWorkoutActivityTypeRunning",
    "Walk": "HKWorkoutActivityTypeWalking",
    "Cycle": "HKWorkoutActivityTypeCycling",
    "Strength": "HKWorkoutActivityTypeTraditionalStrengthTraining",
    "Functional": "HKWorkoutActivityTypeFunctionalStrengthTraining",
    "Cooldown": "HKWorkoutActivityTypeCooldown",
}
WATCH = "Runner’s Apple Watch"
PHONE = "Runner’s iPhone"
DISTANCE_RECORD = "HKQuantityTypeIdentifierDistanceWalkingRunning"
HEART_RATE_RECORD = "HKQuantityTypeIdentifierHeartRate"
HEART_RATE_STATISTIC = "HKQuantityTypeIdentifierHeartRate"


@dataclass
class Workout:
    kind: str
    # Wall-clock time where it happened, as the watch shows it.
    start: datetime
    minutes: float
    km: float = 0.0
    device: str = WATCH
    offset_hours: int = -5
    avg_hr: float | None = 140.0
    samples: bool = True
    phone_km: float = 0.0


def _stamp(moment, offset_hours):
    zone = timezone(timedelta(hours=offset_hours))
    return moment.replace(tzinfo=zone).strftime("%Y-%m-%d %H:%M:%S %z")


def _record(kind, source, unit, start, end, offset, value):
    return (
        f'<Record type="{kind}" sourceName="{source}" unit="{unit}" '
        f'creationDate="{_stamp(end, offset)}" startDate="{_stamp(start, offset)}" '
        f'endDate="{_stamp(end, offset)}" value="{value}"/>'
    )


def _records(w):
    if not w.samples:
        return []
    end = w.start + timedelta(minutes=w.minutes)
    steps = max(2, int(w.minutes))
    step = (end - w.start) / steps
    rows = []
    for n in range(steps):
        at = w.start + step * n
        rows.append(_record(HEART_RATE_RECORD, w.device, "count/min", at, at, w.offset_hours, w.avg_hr or 140))
        if w.km:
            rows.append(_record(DISTANCE_RECORD, w.device, "km", at, at + step, w.offset_hours, round(w.km / steps, 5)))
    if w.phone_km:
        # A phone in the pocket logs the same run as a few coarse chunks.
        chunk = (end - w.start) / 3
        for n in range(3):
            at = w.start + chunk * n + timedelta(seconds=7)
            rows.append(_record(DISTANCE_RECORD, PHONE, "km", at, at + chunk, w.offset_hours, round(w.phone_km / 3, 5)))
    return rows


def _workout_xml(w):
    end = w.start + timedelta(minutes=w.minutes)
    stats = ""
    if w.km:
        stats += f'<WorkoutStatistics type="{DISTANCE_RECORD}" sum="{w.km}" unit="km"/>'
    if w.avg_hr:
        stats += f'<WorkoutStatistics type="{HEART_RATE_STATISTIC}" average="{w.avg_hr}" maximum="{w.avg_hr + 20}" unit="count/min"/>'
    return (
        f'<Workout workoutActivityType="{APPLE_TYPES[w.kind]}" duration="{w.minutes}" durationUnit="min" '
        f'sourceName="{w.device}" startDate="{_stamp(w.start, w.offset_hours)}" '
        f'endDate="{_stamp(end, w.offset_hours)}">{stats}</Workout>'
    )


def export_xml(workouts):
    body = "\n".join(_workout_xml(w) for w in workouts)
    records = "\n".join(row for w in workouts for row in _records(w))
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<HealthData>\n{body}\n{records}\n</HealthData>'.encode()


def export_zip(workouts):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("apple_health_export/export.xml", export_xml(workouts))
    buffer.seek(0)
    return buffer


def upload(client, workouts, filename="export.zip"):
    """Sends an export through the real import route, as the Import page does."""
    return client.post(
        "/import",
        data={"file": (export_zip(workouts), filename)},
        content_type="multipart/form-data",
    )

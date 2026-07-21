import csv
import hashlib
import io
import zipfile
from datetime import datetime, timedelta, timezone
from math import atan2, cos, radians, sin, sqrt

import defusedxml.ElementTree as ET

from app import analytics
from app.models import Activity, ActivityStream, BestEffort, UserSettings

STANDARD_DISTANCES = [
    ("400m", 400.0),
    ("1/2 Mile", 804.0),
    ("1K", 1000.0),
    ("1 Mile", 1609.0),
    ("2 Miles", 3218.0),
    ("5K", 5000.0),
    ("10K", 10000.0),
    ("15K", 15000.0),
    ("10 Miles", 16093.0),
    ("Half Marathon", 21097.0),
    ("Marathon", 42195.0),
]

APPLE_DATE_FMT = "%Y-%m-%d %H:%M:%S %z"
EARTH_RADIUS_M = 6371000

ACTIVITY_TYPE_MAP = {"running": "Run", "walking": "Walk", "cycling": "Cycle"}

RECORD_TYPES = {
    "HKQuantityTypeIdentifierHeartRate": "hr",
    "HKQuantityTypeIdentifierDistanceWalkingRunning": "distance",
    "HKQuantityTypeIdentifierDistanceCycling": "distance",
}

# Newer Apple Health exports omit the totalDistance attribute on <Workout> and
# report it instead as a child <WorkoutStatistics> sum.
DISTANCE_STATISTIC_TYPES = {
    "HKQuantityTypeIdentifierDistanceWalkingRunning",
    "HKQuantityTypeIdentifierDistanceCycling",
}

GPX_NS = {
    "gpx": "http://www.topografix.com/GPX/1/1",
    "gpxtpx": "http://www.garmin.com/xmlschemas/TrackPointExtension/v1",
}


def _normalize_activity_type(raw):
    if raw.startswith("HKWorkoutActivityType"):
        raw = raw[len("HKWorkoutActivityType"):]
    return ACTIVITY_TYPE_MAP.get(raw.lower(), raw)


def _to_meters(value, unit):
    value = float(value)
    if unit == "km":
        return value * 1000
    if unit == "mi":
        return value * 1609.344
    return value


def _to_seconds(value, unit):
    value = float(value)
    if unit == "min":
        return int(round(value * 60))
    if unit == "hr":
        return int(round(value * 3600))
    return int(round(value))


def _parse_apple_date(raw):
    return datetime.strptime(raw, APPLE_DATE_FMT).astimezone(timezone.utc).replace(tzinfo=None)


def _drop_overlapping_duplicates(windows):
    kept = []
    for w in windows:
        overlaps = any(
            w["activity_type"] == k["activity_type"]
            and w["start_time"] < k["end_time"]
            and k["start_time"] < w["end_time"]
            for k in kept
        )
        if not overlaps:
            kept.append(w)
    return kept


def _collect_workout_windows(xml_bytes):
    windows = []
    me_attrs = {}
    # WorkoutStatistics/FileReference end-events fire before their parent Workout's
    # end-event, and every element is cleared immediately after being visited — so
    # their data has to be stashed here and consumed when the enclosing Workout closes,
    # not read back off the (by-then-cleared) parent afterward.
    pending_distance_meters = None
    pending_route_file = None

    for _, elem in ET.iterparse(io.BytesIO(xml_bytes), events=("end",)):
        tag = elem.tag
        if tag == "Me":
            birth_date = elem.get("HKCharacteristicTypeIdentifierDateOfBirth")
            if birth_date:
                me_attrs["birth_year"] = int(birth_date.split("-")[0])
        elif tag == "WorkoutStatistics":
            if elem.get("type") in DISTANCE_STATISTIC_TYPES:
                pending_distance_meters = _to_meters(elem.get("sum"), elem.get("unit"))
        elif tag == "FileReference":
            path = elem.get("path")
            if path and path.endswith(".gpx"):
                pending_route_file = path.lstrip("/")
        elif tag == "Workout":
            total_distance = elem.get("totalDistance")
            if total_distance is not None:
                distance_meters = _to_meters(total_distance, elem.get("totalDistanceUnit"))
            elif pending_distance_meters is not None:
                distance_meters = pending_distance_meters
            else:
                distance_meters = 0.0

            windows.append(
                {
                    "activity_type": _normalize_activity_type(elem.get("workoutActivityType")),
                    "start_time": _parse_apple_date(elem.get("startDate")),
                    "end_time": _parse_apple_date(elem.get("endDate")),
                    "duration_seconds": _to_seconds(elem.get("duration"), elem.get("durationUnit")),
                    "distance_meters": distance_meters,
                    "source_device": elem.get("sourceName"),
                    "route_file": pending_route_file,
                }
            )
            pending_distance_meters = None
            pending_route_file = None
        elem.clear()
    return _drop_overlapping_duplicates(windows), me_attrs


def _bucket_records(xml_bytes, windows, route_points_by_index=None):
    buckets = [{} for _ in windows]
    distance_by_source = [{} for _ in windows]
    for _, elem in ET.iterparse(io.BytesIO(xml_bytes), events=("end",)):
        if elem.tag == "Record":
            metric = RECORD_TYPES.get(elem.get("type"))
            if metric is not None:
                start = _parse_apple_date(elem.get("startDate"))
                value = float(elem.get("value"))
                if metric == "distance":
                    value = _to_meters(value, elem.get("unit"))
                for i, w in enumerate(windows):
                    if w["start_time"] <= start <= w["end_time"]:
                        elapsed = int((start - w["start_time"]).total_seconds())
                        if metric == "distance":
                            source = elem.get("sourceName") or ""
                            distance_by_source[i].setdefault(source, {})[elapsed] = value
                        else:
                            buckets[i].setdefault(elapsed, {})[metric] = value
                        break
        elem.clear()

    # An iPhone and a Watch worn on the same run both log distance for it, so their
    # records interleave and summing all of them double-counts — the phone's sparse
    # aggregates land on top of the watch's per-second samples and the cumulative
    # stream lurches forward by whole kilometres, which best_effort reads as an
    # impossibly fast split. Keep only the source that sampled the workout most
    # densely and drop the rest.
    for i, by_source in enumerate(distance_by_source):
        if not by_source:
            continue
        best_source = max(by_source, key=lambda s: len(by_source[s]))
        for elapsed, value in by_source[best_source].items():
            buckets[i].setdefault(elapsed, {})["distance"] = value

    if route_points_by_index:
        for i, points in route_points_by_index.items():
            for p in points:
                entry = buckets[i].setdefault(p["elapsed"], {})
                entry["lat"] = p["lat"]
                entry["lon"] = p["lon"]
                if p["elevation"] is not None:
                    entry["elevation"] = p["elevation"]

    streams = []
    for bucket in buckets:
        times = sorted(bucket.keys())
        # Apple Health distance records report the distance covered within that
        # record's own interval, not a running odometer total — accumulate them so
        # the stream matches the cumulative shape km_splits/best_effort expect
        # (already true for GPX imports, which sum haversine legs as they go).
        cumulative_distance = 0.0
        distances = []
        for t in times:
            interval = bucket[t].get("distance")
            if interval is None:
                distances.append(None)
            else:
                cumulative_distance += interval
                distances.append(cumulative_distance)
        streams.append(
            {
                "time": times,
                "hr": [bucket[t].get("hr") for t in times],
                "distance": distances,
                "elevation": [bucket[t].get("elevation") for t in times],
                "lat": [bucket[t].get("lat") for t in times],
                "lon": [bucket[t].get("lon") for t in times],
                "pace": [],
            }
        )
    return streams


def parse_apple_health_xml(xml_bytes):
    windows, _me_attrs = _collect_workout_windows(xml_bytes)
    streams = _bucket_records(xml_bytes, windows)
    for w, stream in zip(windows, streams):
        w["stream_data"] = stream
    return windows


def _make_dedup_key(activity_type, start_time, duration_seconds):
    raw = f"{activity_type}|{start_time.isoformat()}|{duration_seconds}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _persist_activity(
    db_session,
    activity_type,
    start_time,
    end_time,
    duration_seconds,
    distance_meters,
    avg_hr,
    max_hr,
    elevation_gain_meters,
    source,
    source_id,
    stream_data=None,
    source_device=None,
):
    dedup_key = _make_dedup_key(activity_type, start_time, duration_seconds)
    existing = db_session.query(Activity).filter_by(dedup_key=dedup_key).first()
    if existing:
        return False

    activity = Activity(
        activity_type=activity_type,
        start_time=start_time,
        end_time=end_time,
        duration_seconds=duration_seconds,
        distance_meters=distance_meters,
        avg_hr=avg_hr,
        max_hr=max_hr,
        elevation_gain_meters=elevation_gain_meters,
        source_device=source_device,
        source=source,
        source_id=source_id,
        dedup_key=dedup_key,
    )
    db_session.add(activity)
    db_session.flush()
    if stream_data is not None:
        db_session.add(ActivityStream(activity_id=activity.id, stream_data=stream_data))
        db_session.commit()
        update_best_efforts(db_session, activity, stream_data)
    else:
        db_session.commit()
    return True


def is_best_effort_eligible(activity):
    return analytics.categorize_activity_type(activity.activity_type)["category"] == "Run"


def update_best_efforts(db_session, activity, stream_data):
    # Best efforts are a running PR board: a ride covers 5K in a time no run can match,
    # and gym workouts carry stray incidental distance samples.
    if not is_best_effort_eligible(activity):
        return

    times, distances = analytics.coalesce_stream_metric(stream_data["time"], stream_data["distance"])
    if len(times) < 2:
        return

    for label, target_meters in STANDARD_DISTANCES:
        candidate_seconds = analytics.best_effort(times, distances, target_meters)
        if candidate_seconds is None:
            continue

        existing = db_session.query(BestEffort).filter_by(distance_label=label).first()
        existing_seconds = existing.duration_seconds if existing else None
        if not analytics.is_new_best_effort(existing_seconds, candidate_seconds):
            continue

        pace = candidate_seconds / (target_meters / 1000.0)
        if existing:
            existing.activity_id = activity.id
            existing.distance_meters = target_meters
            existing.duration_seconds = candidate_seconds
            existing.pace_per_km_seconds = pace
            existing.achieved_at = activity.start_time
        else:
            db_session.add(
                BestEffort(
                    distance_label=label,
                    distance_meters=target_meters,
                    activity_id=activity.id,
                    duration_seconds=candidate_seconds,
                    pace_per_km_seconds=pace,
                    achieved_at=activity.start_time,
                )
            )
    db_session.commit()


def recompute_best_efforts(db_session):
    db_session.query(BestEffort).delete()
    db_session.commit()

    rows = (
        db_session.query(Activity, ActivityStream)
        .join(ActivityStream, ActivityStream.activity_id == Activity.id)
        .order_by(Activity.start_time.asc())
        .all()
    )
    for activity, stream in rows:
        update_best_efforts(db_session, activity, stream.stream_data)


def _is_unsafe_zip_entry(name):
    if name.startswith("/") or name.startswith("\\"):
        return True
    parts = name.replace("\\", "/").split("/")
    return ".." in parts


def _maybe_set_birth_year(db_session, me_attrs):
    birth_year = me_attrs.get("birth_year")
    if birth_year is None:
        return
    settings = db_session.query(UserSettings).first()
    if settings is None:
        settings = UserSettings()
        db_session.add(settings)
    if settings.birth_year is None:
        settings.birth_year = birth_year
        db_session.commit()


def import_apple_health_zip(zip_path, db_session):
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        for name in names:
            if _is_unsafe_zip_entry(name):
                raise ValueError(f"unsafe zip entry: {name}")
        export_name = next((n for n in names if n.endswith("export.xml")), None)
        if export_name is None:
            raise ValueError("export.xml not found in zip")
        export_dir = export_name.rsplit("/", 1)[0] if "/" in export_name else ""
        xml_bytes = zf.read(export_name)

        windows, me_attrs = _collect_workout_windows(xml_bytes)

        route_points_by_index = {}
        for i, w in enumerate(windows):
            route_file = w.pop("route_file", None)
            if not route_file:
                continue
            full_path = f"{export_dir}/{route_file}" if export_dir else route_file
            if full_path in names:
                route_points_by_index[i] = _parse_route_gpx(zf.read(full_path), w["start_time"])

        streams = _bucket_records(xml_bytes, windows, route_points_by_index)

    imported = 0
    skipped = 0
    for w, stream in zip(windows, streams):
        hr_values = [v for v in stream["hr"] if v is not None]
        has_elevation = any(v is not None for v in stream["elevation"])
        created = _persist_activity(
            db_session,
            activity_type=w["activity_type"],
            start_time=w["start_time"],
            end_time=w["end_time"],
            duration_seconds=w["duration_seconds"],
            distance_meters=w["distance_meters"],
            avg_hr=(sum(hr_values) / len(hr_values)) if hr_values else None,
            max_hr=max(hr_values) if hr_values else None,
            elevation_gain_meters=(
                analytics.elevation_gain_from_stream(stream["time"], stream["elevation"])
                if has_elevation
                else None
            ),
            source="apple_health",
            source_id=None,
            source_device=w.get("source_device"),
            stream_data=stream,
        )
        if created:
            imported += 1
        else:
            skipped += 1

    _maybe_set_birth_year(db_session, me_attrs)
    return {"imported": imported, "skipped": skipped}


def _haversine(lat1, lon1, lat2, lon2):
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * atan2(sqrt(a), sqrt(1 - a))


def _parse_gpx_time(raw):
    return datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ")


def _parse_route_gpx(gpx_bytes, window_start_utc):
    root = ET.fromstring(gpx_bytes)
    points = []
    for trkpt in root.findall(".//gpx:trkpt", GPX_NS):
        time_el = trkpt.find("gpx:time", GPX_NS)
        if time_el is None:
            continue
        ele_el = trkpt.find("gpx:ele", GPX_NS)
        elapsed = int((_parse_gpx_time(time_el.text) - window_start_utc).total_seconds())
        points.append(
            {
                "elapsed": elapsed,
                "lat": float(trkpt.get("lat")),
                "lon": float(trkpt.get("lon")),
                "elevation": float(ele_el.text) if ele_el is not None else None,
            }
        )
    return points


def import_gpx(file_path, db_session):
    tree = ET.parse(str(file_path))
    root = tree.getroot()
    trkpts = root.findall(".//gpx:trkpt", GPX_NS)
    if not trkpts:
        raise ValueError("no track points found in gpx file")

    points = []
    for pt in trkpts:
        ele_el = pt.find("gpx:ele", GPX_NS)
        time_el = pt.find("gpx:time", GPX_NS)
        hr_el = pt.find("gpx:extensions/gpxtpx:TrackPointExtension/gpxtpx:hr", GPX_NS)
        points.append(
            {
                "lat": float(pt.get("lat")),
                "lon": float(pt.get("lon")),
                "ele": float(ele_el.text) if ele_el is not None else None,
                "time": _parse_gpx_time(time_el.text),
                "hr": float(hr_el.text) if hr_el is not None else None,
            }
        )

    start_time = points[0]["time"]
    end_time = points[-1]["time"]
    duration_seconds = int((end_time - start_time).total_seconds())

    distance_meters = 0.0
    elevation_gain = 0.0
    cumulative_distances = [0.0]
    for prev, curr in zip(points, points[1:]):
        leg = _haversine(prev["lat"], prev["lon"], curr["lat"], curr["lon"])
        distance_meters += leg
        cumulative_distances.append(distance_meters)
        if prev["ele"] is not None and curr["ele"] is not None and curr["ele"] > prev["ele"]:
            elevation_gain += curr["ele"] - prev["ele"]

    hr_values = [p["hr"] for p in points if p["hr"] is not None]
    avg_hr = sum(hr_values) / len(hr_values) if hr_values else None
    max_hr = max(hr_values) if hr_values else None

    activity_type_raw = root.findtext(".//gpx:type", default="Run", namespaces=GPX_NS)
    activity_type = _normalize_activity_type(activity_type_raw)

    stream_data = {
        "time": [int((p["time"] - start_time).total_seconds()) for p in points],
        "hr": [p["hr"] for p in points],
        "distance": cumulative_distances,
        "elevation": [p["ele"] for p in points],
        "lat": [p["lat"] for p in points],
        "lon": [p["lon"] for p in points],
        "pace": [],
    }

    created = _persist_activity(
        db_session,
        activity_type=activity_type,
        start_time=start_time,
        end_time=end_time,
        duration_seconds=duration_seconds,
        distance_meters=distance_meters,
        avg_hr=avg_hr,
        max_hr=max_hr,
        elevation_gain_meters=elevation_gain,
        source="gpx",
        source_id=None,
        stream_data=stream_data,
    )
    return {"imported": 1, "skipped": 0} if created else {"imported": 0, "skipped": 1}


def import_csv(file_path, db_session):
    imported = 0
    skipped = 0
    with open(file_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            start_time = datetime.fromisoformat(row["date"])
            duration_seconds = int(row["duration_seconds"])
            end_time = start_time + timedelta(seconds=duration_seconds)
            created = _persist_activity(
                db_session,
                activity_type=_normalize_activity_type(row["activity_type"]),
                start_time=start_time,
                end_time=end_time,
                duration_seconds=duration_seconds,
                distance_meters=float(row["distance_meters"]),
                avg_hr=float(row["avg_hr"]) if row.get("avg_hr") else None,
                max_hr=float(row["max_hr"]) if row.get("max_hr") else None,
                elevation_gain_meters=(
                    float(row["elevation_gain_meters"]) if row.get("elevation_gain_meters") else None
                ),
                source="csv",
                source_id=None,
                stream_data=None,
            )
            if created:
                imported += 1
            else:
                skipped += 1
    return {"imported": imported, "skipped": skipped}

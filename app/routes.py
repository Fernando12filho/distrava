import tempfile
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from math import ceil
from pathlib import Path
from urllib.parse import urlencode

from flask import Blueprint, current_app, g, jsonify, redirect, render_template, request, url_for
from sqlalchemy import func

from app import analytics, parser
from app.models import Activity, ActivityStream, BestEffort, UserSettings

bp = Blueprint("main", __name__)

MAX_UPLOAD_BYTES = 200 * 1024 * 1024
ALLOWED_IMPORT_EXTENSIONS = {".zip", ".gpx", ".csv"}
ACTIVITIES_PER_PAGE = 10


def get_db():
    if "db_session" not in g:
        g.db_session = current_app.session_factory()
    return g.db_session


@bp.route("/")
def index():
    return redirect(url_for("main.dashboard"))


def _display_title(activity):
    if activity.title:
        return activity.title
    return analytics.categorize_activity_type(activity.activity_type)["label"]


def _detail_page_title(activity):
    if activity.title:
        return activity.title
    label = analytics.categorize_activity_type(activity.activity_type)["label"]
    return f"{label} · {activity.start_time.strftime('%b %d, %Y')}"


def _get_units(settings):
    return settings.units if settings and settings.units else "metric"


def _avg_pace_seconds(activity):
    if not activity.distance_meters:
        return None
    return activity.duration_seconds / (activity.distance_meters / 1000)


def _activity_row(activity, units="metric"):
    cat = analytics.categorize_activity_type(activity.activity_type)
    dist_value, dist_unit = analytics.convert_distance(activity.distance_meters, units) if activity.distance_meters else (None, None)
    pace_seconds = _avg_pace_seconds(activity)
    pace_value, _pace_unit = analytics.convert_pace(pace_seconds, units) if pace_seconds is not None else (None, None)
    return {
        "id": activity.id,
        "date": activity.start_time.strftime("%b %d"),
        "type": cat["label"],
        "dot": cat["dot"],
        "title": _display_title(activity),
        "dist": f"{dist_value:.1f} {dist_unit}" if dist_value is not None else "—",
        "dur": analytics.format_duration(activity.duration_seconds),
        "pace": analytics.format_pace(pace_value) or "—",
        "hr": f"{activity.avg_hr:.0f}" if activity.avg_hr is not None else "—",
    }


def _sort_value(activity, sort_key):
    if sort_key == "title":
        return _display_title(activity).lower()
    if sort_key == "dist":
        return activity.distance_meters or 0.0
    if sort_key == "dur":
        return activity.duration_seconds or 0
    if sort_key == "pace":
        pace = _avg_pace_seconds(activity)
        return pace if pace is not None else float("inf")
    if sort_key == "hr":
        return activity.avg_hr if activity.avg_hr is not None else -1
    return activity.start_time


def _qs(overrides):
    params = {k: v for k, v in request.args.to_dict().items()}
    params.update(overrides)
    params = {k: v for k, v in params.items() if v not in (None, "")}
    return "?" + urlencode(params) if params else ""


TYPE_FILTER_OPTIONS = ["All", "Run", "Ride", "Gym", "Other"]
SORT_COLUMNS = [("date", "Date"), ("title", "Title"), ("dist", "Distance"), ("dur", "Duration"), ("pace", "Pace"), ("hr", "HR")]


@bp.route("/activities")
def activity_list():
    db = get_db()
    units = _get_units(db.query(UserSettings).first())
    query = db.query(Activity)

    date_from = request.args.get("from")
    if date_from:
        query = query.filter(Activity.start_time >= datetime.fromisoformat(date_from))

    date_to = request.args.get("to")
    if date_to:
        query = query.filter(Activity.start_time <= datetime.fromisoformat(date_to))

    range_key = request.args.get("range", "all")
    if range_key != "all" and not date_from and not date_to:
        now = datetime.now()
        if range_key == "30":
            query = query.filter(Activity.start_time >= now - timedelta(days=30))
        elif range_key == "90":
            query = query.filter(Activity.start_time >= now - timedelta(days=90))
        elif range_key == "year":
            query = query.filter(Activity.start_time >= datetime(now.year, 1, 1))

    activities = query.all()

    activity_type = request.args.get("type")
    if activity_type and activity_type != "All":
        activities = [
            a for a in activities if analytics.categorize_activity_type(a.activity_type)["category"] == activity_type
        ]

    sort_key = request.args.get("sort", "date")
    sort_dir = request.args.get("dir", "desc")
    activities.sort(key=lambda a: _sort_value(a, sort_key), reverse=(sort_dir != "asc"))

    total = len(activities)
    total_pages = max(1, ceil(total / ACTIVITIES_PER_PAGE))
    page = max(1, min(int(request.args.get("page", 1)), total_pages))
    start = (page - 1) * ACTIVITIES_PER_PAGE
    page_activities = activities[start : start + ACTIVITIES_PER_PAGE]

    rows = [{**_activity_row(a, units)} for a in page_activities]

    active_type = activity_type or "All"
    type_filters = [
        {"label": t, "active": t == active_type, "href": url_for("main.activity_list") + _qs({"type": t, "page": 1})}
        for t in TYPE_FILTER_OPTIONS
    ]

    sort_links = {}
    for key, _label in SORT_COLUMNS:
        next_dir = "asc" if (sort_key == key and sort_dir == "desc") else "desc"
        sort_links[key] = {
            "href": url_for("main.activity_list") + _qs({"sort": key, "dir": next_dir, "page": 1}),
            "arrow": ("↑" if sort_dir == "asc" else "↓") if sort_key == key else "",
        }

    return render_template(
        "activity_list.html",
        rows=rows,
        total=total,
        page=page,
        total_pages=total_pages,
        range_start=start + 1 if total else 0,
        range_end=min(start + ACTIVITIES_PER_PAGE, total),
        sort_key=sort_key,
        sort_dir=sort_dir,
        active_type=active_type,
        active_range=range_key,
        type_filters=type_filters,
        sort_links=sort_links,
        prev_href=url_for("main.activity_list") + _qs({"page": page - 1}),
        next_href=url_for("main.activity_list") + _qs({"page": page + 1}),
    )


def _compute_splits(stream_data, split_meters=1000.0):
    times, distances = analytics.coalesce_stream_metric(stream_data["time"], stream_data["distance"])
    if len(times) < 2:
        return []

    splits = analytics.km_splits(times, distances, split_meters=split_meters)

    elev_times, elevations = analytics.coalesce_stream_metric(
        stream_data["time"], stream_data.get("elevation", [])
    )
    hr_times, hr_values = analytics.coalesce_stream_metric(stream_data["time"], stream_data.get("hr", []))
    cumulative_time = times[0]
    prev_elevation = analytics.value_at_time(elev_times, elevations, cumulative_time) if elev_times else None
    for split in splits:
        cumulative_time += split["duration_seconds"]
        curr_elevation = analytics.value_at_time(elev_times, elevations, cumulative_time) if elev_times else None
        if prev_elevation is not None and curr_elevation is not None and split["distance_meters"] > 0:
            grade_percent = (curr_elevation - prev_elevation) / split["distance_meters"] * 100
            split["grade_adjusted_pace_seconds"] = analytics.grade_adjusted_pace(
                split["pace_per_km_seconds"], grade_percent
            )
            split["elevation_change_meters"] = curr_elevation - prev_elevation
        else:
            split["grade_adjusted_pace_seconds"] = None
            split["elevation_change_meters"] = None
        split["hr"] = analytics.value_at_time(hr_times, hr_values, cumulative_time) if hr_times else None
        prev_elevation = curr_elevation
    return splits


def _convert_splits_for_display(splits, units):
    for split in splits:
        if split["elevation_change_meters"] is not None:
            value, _unit = analytics.convert_elevation(split["elevation_change_meters"], units)
            split["elevation_change_display"] = value
        else:
            split["elevation_change_display"] = None
    return splits


def _time_in_zones_display(stream_data, max_hr, resting_hr):
    hr_times, hr_values = analytics.coalesce_stream_metric(stream_data["time"], stream_data.get("hr", []))
    if len(hr_times) < 2:
        return []
    bands = analytics.hr_zone_bands(max_hr, resting_hr)
    seconds_by_zone = analytics.time_in_zone(hr_times, hr_values, bands)
    total = sum(seconds_by_zone.values())
    if total <= 0:
        return []
    return [
        {
            **band,
            "time": analytics.format_duration(seconds_by_zone[band["zone_number"]]),
            "pct": seconds_by_zone[band["zone_number"]] / total * 100,
        }
        for band in bands
    ]


def _activity_own_best_efforts(db, activity, stream_data):
    times, distances = analytics.coalesce_stream_metric(stream_data["time"], stream_data["distance"])
    if len(times) < 2:
        return []

    efforts = []
    for label, target_meters in parser.STANDARD_DISTANCES:
        seconds = analytics.best_effort(times, distances, target_meters)
        if seconds is None:
            continue
        global_best = db.query(BestEffort).filter_by(distance_label=label).first()
        is_pr = bool(global_best and global_best.activity_id == activity.id)
        efforts.append({"label": f"Fastest {label}", "value": analytics.format_duration(seconds), "is_pr": is_pr})
    return efforts


@bp.route("/activities/<int:activity_id>")
def activity_detail(activity_id):
    db = get_db()
    activity = db.get(Activity, activity_id)
    if activity is None:
        return "Activity not found", 404

    settings = db.query(UserSettings).first()
    units = _get_units(settings)
    category = analytics.categorize_activity_type(activity.activity_type)
    # Splits/best-efforts/pace are a running concept — Apple Health streams for
    # non-running workouts (e.g. Volleyball) can carry stray incidental distance
    # samples that would otherwise produce nonsensical pace values here.
    is_pace_based = category["category"] == "Run"

    stream = db.query(ActivityStream).filter_by(activity_id=activity_id).first()
    splits = []
    efforts = []
    hr_zones = []
    if stream is not None:
        resting_hr, max_hr = _resolve_hr_profile(settings, date.today())
        hr_zones = _time_in_zones_display(stream.stream_data, max_hr, resting_hr)
    if stream is not None and is_pace_based:
        split_meters = analytics.split_distance_meters(units)
        splits = _convert_splits_for_display(
            analytics.annotate_splits_for_display(_compute_splits(stream.stream_data, split_meters)), units
        )
        efforts = _activity_own_best_efforts(db, activity, stream.stream_data)

    dist_value, dist_unit = (
        analytics.convert_distance(activity.distance_meters, units) if activity.distance_meters else (None, None)
    )
    pace_seconds = _avg_pace_seconds(activity) if is_pace_based else None
    pace_value, pace_unit = analytics.convert_pace(pace_seconds, units) if pace_seconds is not None else (None, None)
    elev_value, elev_unit = (
        analytics.convert_elevation(activity.elevation_gain_meters, units)
        if activity.elevation_gain_meters is not None
        else (None, None)
    )

    return render_template(
        "activity_detail.html",
        activity=activity,
        display_title=_detail_page_title(activity),
        category=category,
        splits=splits,
        efforts=efforts,
        hr_zones=hr_zones,
        is_pace_based=is_pace_based,
        units=units,
        dist_value=dist_value,
        dist_unit=dist_unit or "km",
        pace_value=pace_value,
        pace_unit=pace_unit or "km",
        elev_value=elev_value,
        elev_unit=elev_unit or "m",
        split_unit_label="mile" if units == "imperial" else "kilometer",
        split_col_label="MI" if units == "imperial" else "KM",
    )


@bp.route("/activities/<int:activity_id>/stream.json")
def activity_stream(activity_id):
    db = get_db()
    activity = db.get(Activity, activity_id)
    if activity is None:
        return jsonify({"error": "not found"}), 404

    stream = db.query(ActivityStream).filter_by(activity_id=activity_id).first()
    if stream is None:
        return jsonify({"hr": [], "pace": [], "elevation": [], "distance": [], "time": []})
    return jsonify(stream.stream_data)


@bp.route("/import", methods=["GET"])
def import_page():
    return render_template("import.html")


@bp.route("/import", methods=["POST"])
def import_file():
    if "file" not in request.files:
        return jsonify({"error": "no file provided"}), 400

    upload = request.files["file"]
    filename = upload.filename or ""
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_IMPORT_EXTENSIONS:
        return jsonify({"error": f"unsupported file type: {suffix}"}), 400

    upload.seek(0, 2)
    size = upload.tell()
    upload.seek(0)
    max_upload_bytes = current_app.config.get("MAX_UPLOAD_BYTES", MAX_UPLOAD_BYTES)
    if size > max_upload_bytes:
        return jsonify({"error": "file too large"}), 413

    db = get_db()
    tmp_path = Path(tempfile.gettempdir()) / filename
    upload.save(tmp_path)
    started = time.monotonic()
    try:
        if suffix == ".zip":
            result = parser.import_apple_health_zip(tmp_path, db)
        elif suffix == ".gpx":
            result = parser.import_gpx(tmp_path, db)
        else:
            result = parser.import_csv(tmp_path, db)
    finally:
        tmp_path.unlink(missing_ok=True)
    elapsed = time.monotonic() - started

    earliest, latest = db.query(func.min(Activity.start_time), func.max(Activity.start_time)).one()
    date_range = f"{earliest.strftime('%b %Y')} → {latest.strftime('%b %Y')}" if earliest and latest else None

    result.update(
        {
            "filename": filename,
            "size_bytes": size,
            "elapsed_seconds": round(elapsed, 1),
            "date_range": date_range,
        }
    )
    return jsonify(result), 200


DEFAULT_RESTING_HR = 60
DEFAULT_MAX_HR = 190


def _resolve_hr_profile(settings, today):
    resting_hr = settings.resting_hr if settings and settings.resting_hr else DEFAULT_RESTING_HR
    if settings and settings.max_hr:
        max_hr = settings.max_hr
    elif settings and settings.birth_year:
        max_hr = analytics.default_max_hr(settings.birth_year, today.year)
    else:
        max_hr = DEFAULT_MAX_HR
    return resting_hr, max_hr


@bp.route("/settings", methods=["GET", "POST"])
def settings_page():
    db = get_db()
    settings = db.query(UserSettings).first()

    if request.method == "POST":
        if settings is None:
            settings = UserSettings()
            db.add(settings)
        resting_hr = request.form.get("resting_hr")
        max_hr = request.form.get("max_hr")
        birth_year = request.form.get("birth_year")
        weight_input = request.form.get("weight_kg")
        units = request.form.get("units") or "metric"
        settings.resting_hr = int(resting_hr) if resting_hr else None
        settings.max_hr = int(max_hr) if max_hr else None
        settings.birth_year = int(birth_year) if birth_year else None
        settings.weight_kg = analytics.weight_to_kg(float(weight_input), units) if weight_input else None
        settings.units = units
        db.commit()
        if request.headers.get("X-Requested-With") == "fetch":
            return "", 204
        return redirect(url_for("main.settings_page"))

    resolved_resting_hr, resolved_max_hr = _resolve_hr_profile(settings, date.today())
    db_url = current_app.config.get("DATABASE_URL", "")
    db_path = db_url[len("sqlite:///") :] if db_url.startswith("sqlite:///") else db_url
    db_size_mb = None
    path = Path(db_path)
    if path.exists():
        db_size_mb = path.stat().st_size / (1024 * 1024)

    units = _get_units(settings)
    weight_value, weight_unit = (
        analytics.convert_weight(settings.weight_kg, units) if settings and settings.weight_kg else (None, "kg" if units == "metric" else "lb")
    )

    return render_template(
        "settings.html",
        settings=settings,
        resolved_max_hr=resolved_max_hr,
        zones=analytics.hr_zone_bands(resolved_max_hr, resolved_resting_hr),
        resolved_resting_hr=resolved_resting_hr,
        db_path=db_path,
        db_size_mb=db_size_mb,
        units=units,
        weight_value=weight_value,
        weight_unit=weight_unit,
    )


@bp.route("/settings/wipe", methods=["POST"])
def settings_wipe():
    db = get_db()
    db.query(ActivityStream).delete()
    db.query(BestEffort).delete()
    db.query(Activity).delete()
    db.commit()
    return redirect(url_for("main.settings_page"))


def _pct_delta(current, previous):
    if not previous:
        return None
    return (current - previous) / previous * 100


WEEKLY_VOLUME_WEEKS = 12
CALENDAR_DAYS = 35
RACE_PREDICTION_TARGETS = [("5K", 5000.0), ("10K", 10000.0), ("Half Marathon", 21097.0), ("Marathon", 42195.0)]


@bp.route("/dashboard")
def dashboard():
    db = get_db()
    today = date.today()

    activities = db.query(Activity).order_by(Activity.start_time.asc()).all()
    has_data = len(activities) > 0

    this_week_start = today - timedelta(days=6)
    last_week_start = today - timedelta(days=13)
    last_week_end = today - timedelta(days=7)

    this_week = [a for a in activities if this_week_start <= a.start_time.date() <= today]
    last_week = [a for a in activities if last_week_start <= a.start_time.date() <= last_week_end]

    this_week_distance = sum(a.distance_meters for a in this_week)
    last_week_distance = sum(a.distance_meters for a in last_week)
    this_week_duration = sum(a.duration_seconds for a in this_week)
    last_week_duration = sum(a.duration_seconds for a in last_week)

    settings = db.query(UserSettings).first()
    units = _get_units(settings)
    resting_hr, max_hr = _resolve_hr_profile(settings, today)

    daily_totals = {}
    for a in activities:
        if a.avg_hr is None:
            continue
        day = a.start_time.date()
        load = analytics.trimp(a.duration_seconds / 60, a.avg_hr, resting_hr, max_hr)
        daily_totals[day] = daily_totals.get(day, 0.0) + load

    training_load = 0.0
    training_load_delta = None
    if daily_totals:
        start_date = min(daily_totals.keys())
        loads = analytics.build_daily_trimp_loads(daily_totals, start_date, today)
        fitness_series = analytics.ctl_atl(loads)
        training_load = fitness_series[-1]["atl"]
        trend_index = len(fitness_series) - 1 - 7
        if trend_index >= 0:
            training_load_delta = _pct_delta(training_load, fitness_series[trend_index]["atl"])

    calendar_start = today - timedelta(days=CALENDAR_DAYS - 1)
    calendar = analytics.calendar_levels(daily_totals, calendar_start, today)
    streak = analytics.current_streak(calendar)

    dist_unit = analytics.convert_distance(0.0, units)[1]
    weekly_volume = []
    for weeks_back in range(WEEKLY_VOLUME_WEEKS - 1, -1, -1):
        week_end = today - timedelta(days=7 * weeks_back)
        week_start = week_end - timedelta(days=6)
        total_meters = sum(a.distance_meters for a in activities if week_start <= a.start_time.date() <= week_end)
        total_value, _unit = analytics.convert_distance(total_meters, units)
        weekly_volume.append(round(total_value, 1))

    weekly_loads = defaultdict(float)
    for day, load in daily_totals.items():
        weekly_loads[day.isocalendar()[:2]] += load
    if weekly_loads:
        best_week_key, best_week_load = max(weekly_loads.items(), key=lambda kv: kv[1])
        best_week_label = "This week" if best_week_key == today.isocalendar()[:2] else f"Week {best_week_key[1]}, {best_week_key[0]}"
    else:
        best_week_load = 0.0
        best_week_label = "—"

    recent = [_activity_row(a, units) for a in list(reversed(activities))[:5]]

    best_efforts = db.query(BestEffort).order_by(BestEffort.distance_meters.asc()).all()
    five_k = next((be for be in best_efforts if be.distance_label == "5K"), None)
    one_k = next((be for be in best_efforts if be.distance_label == "1K"), None)
    runs = [a for a in activities if analytics.categorize_activity_type(a.activity_type)["category"] == "Run"]
    longest_run = max(runs, key=lambda a: a.distance_meters, default=None)

    recent_prs = []
    if five_k:
        recent_prs.append(
            {
                "label": "Fastest 5K",
                "value": analytics.format_duration(five_k.duration_seconds),
                "date": five_k.achieved_at.strftime("%b %d, %Y"),
            }
        )
    if one_k:
        recent_prs.append(
            {
                "label": "Best 1K",
                "value": analytics.format_duration(one_k.duration_seconds),
                "date": one_k.achieved_at.strftime("%b %d, %Y"),
            }
        )
    if longest_run:
        longest_value, longest_unit = analytics.convert_distance(longest_run.distance_meters, units)
        recent_prs.append(
            {
                "label": "Longest run",
                "value": f"{longest_value:.1f} {longest_unit}",
                "date": longest_run.start_time.strftime("%b %d, %Y"),
            }
        )
    recent_prs.append({"label": "Highest weekly load", "value": f"{best_week_load:.0f}", "date": best_week_label})

    # Longest PR distance is the most reliable Riegel basis: extrapolating up
    # from short efforts overstates endurance far more than scaling between
    # race-length efforts does.
    prediction_basis = max(best_efforts, key=lambda be: be.distance_meters, default=None)
    race_predictions = []
    vo2max = None
    if prediction_basis is not None:
        for label, target_meters in RACE_PREDICTION_TARGETS:
            seconds = analytics.riegel_predict(
                prediction_basis.duration_seconds, prediction_basis.distance_meters, target_meters
            )
            race_predictions.append({"label": label, "value": analytics.format_duration(seconds)})
        vo2max = analytics.estimate_vo2max(prediction_basis.distance_meters, prediction_basis.duration_seconds)

    last_import = max((a.created_at for a in activities if a.created_at), default=None)
    weekly_distance_value, _unit = analytics.convert_distance(this_week_distance, units)

    return render_template(
        "dashboard.html",
        has_data=has_data,
        last_import=last_import,
        weekly_distance_value=weekly_distance_value,
        dist_unit=dist_unit,
        weekly_distance_delta=_pct_delta(this_week_distance, last_week_distance),
        weekly_duration_hours=this_week_duration / 3600,
        weekly_duration_delta=_pct_delta(this_week_duration, last_week_duration),
        weekly_count=len(this_week),
        weekly_count_delta=len(this_week) - len(last_week),
        training_load=training_load,
        training_load_delta=training_load_delta,
        calendar=calendar,
        streak=streak,
        calendar_start=calendar_start,
        calendar_end=today,
        weekly_volume=weekly_volume,
        weekly_volume_unit_label="miles" if units == "imperial" else "kilometers",
        recent=recent,
        recent_prs=recent_prs,
        race_predictions=race_predictions,
        prediction_basis_label=prediction_basis.distance_label if prediction_basis else None,
        vo2max=vo2max,
    )

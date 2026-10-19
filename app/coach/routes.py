from datetime import date, datetime, timedelta

from flask import Blueprint, abort, redirect, render_template, request, url_for
from sqlalchemy import func

from app import analytics
from app.coach import board, volume
from app.coach.catalog import INTENSITIES, SESSION_TEMPLATES
from app.coach.matcher import SESSION_ACTIVITY_TYPES, match_sessions
from app.coach.week import DAYS_PER_WEEK, week_start_for
from app.models import Activity, CoachExercise, CoachSession, CoachSessionItem, CoachWeek, UserSettings
from app.routes import _get_units, get_db

bp = Blueprint("coach", __name__, url_prefix="/coach")

# "moved" is set by the rebalancer, never picked by hand.
USER_STATUSES = ("planned", "done", "partial", "skipped")

KIND_LABELS = {"run": "Run", "ride": "Ride", "gym": "Gym", "mobility": "Mobility", "rest": "Rest"}


def _is_fetch():
    return request.headers.get("X-Requested-With") == "fetch"


def _board_url(week_start, session_id=None):
    params = {"week": week_start.isoformat()}
    if session_id is not None:
        params["session"] = session_id
    return url_for("coach.board_page", **params)


def _day_index(raw):
    try:
        value = int(raw)
    except (TypeError, ValueError):
        abort(400)
    if not 0 <= value < DAYS_PER_WEEK:
        abort(400)
    return value


def _session_view(session, units):
    items = [
        {
            "id": item.id,
            "name": item.exercise.name,
            "muscle": item.exercise.muscle_group,
            "intensity": item.exercise.intensity,
            "intensity_level": INTENSITIES.index(item.exercise.intensity) + 1,
            "sets": item.sets,
            "reps": item.reps,
            "duration_seconds": item.duration_seconds,
            "distance_meters": item.distance_meters,
        }
        for item in session.items
    ]
    for item in items:
        item["volume"] = board.item_volume(item, units)
        item["shape"] = volume.item_shape(item)
        item["form"] = volume.form_values(item, units)
    return {
        "id": session.id,
        "date": session.week.week_start + timedelta(days=session.day_index),
        "day_index": session.day_index,
        "position": session.position,
        "kind": session.kind,
        "kind_label": KIND_LABELS[session.kind],
        "focus": session.focus,
        "status": session.status,
        "summary": board.session_summary(session.kind, items, units),
        "exercises": items,
        "distance_meters": sum(i["distance_meters"] or 0 for i in items) or None,
        "duration_seconds": sum((i["duration_seconds"] or 0) * (i["sets"] or 1) for i in items) or None,
        "matched_activity_id": session.matched_activity_id,
        "matched": None,
        "suggestion": None,
    }


def _week_sessions(db, week_start, units):
    week = db.query(CoachWeek).filter_by(week_start=week_start).first()
    return [_session_view(s, units) for s in week.sessions] if week else []


def _activity_view(activity):
    return {
        "id": activity.id,
        "activity_type": activity.activity_type,
        "start_time": activity.local_start_time,
        "distance_meters": activity.distance_meters,
        "duration_seconds": activity.duration_seconds,
    }


def _week_matches(db, week_start):
    """Matcher results for one week, plus the activities they refer to by id."""
    week = db.query(CoachWeek).filter_by(week_start=week_start).first()
    if week is None:
        return {}, {}
    sessions = [_session_view(s, "metric") for s in week.sessions]
    # A run logged a day off may belong to this week, and start_time is UTC
    # while matching uses local days, so look two days past each edge.
    window_start = datetime.combine(week_start - timedelta(days=2), datetime.min.time())
    window_end = window_start + timedelta(days=DAYS_PER_WEEK + 4)
    claimed = {
        activity_id
        for (activity_id,) in db.query(CoachSession.matched_activity_id).filter(CoachSession.matched_activity_id.isnot(None))
    }
    activities = [
        _activity_view(a)
        for a in db.query(Activity).filter(
            Activity.start_time >= window_start,
            Activity.start_time < window_end,
            Activity.activity_type.in_(SESSION_ACTIVITY_TYPES.values()),
        )
        if a.id not in claimed
    ]
    return match_sessions(sessions, activities), {a["id"]: a for a in activities}


def _attach_matches(db, sessions, week_start, units):
    results, activities = _week_matches(db, week_start)
    for session in sessions:
        result = results.get(session["id"])
        if result:
            candidates = [activities[i] for i in result["activity_ids"]]
            if result["kind"] == "match":
                prompt = "Import matches"
            elif len(candidates) > 1:
                prompt = "Which import was this?"
            else:
                prompt = "Was this import this session?"
            session["suggestion"] = {
                "prompt": prompt,
                "candidates": [
                    {"id": a["id"], "label": board.activity_label(a, units, session["date"])} for a in candidates
                ],
            }

    matched_ids = [s["matched_activity_id"] for s in sessions if s["matched_activity_id"]]
    matched = {a.id: a for a in db.query(Activity).filter(Activity.id.in_(matched_ids))} if matched_ids else {}
    for session in sessions:
        activity = matched.get(session["matched_activity_id"])
        if activity is not None:
            session["matched"] = {
                "label": board.activity_label(_activity_view(activity), units, session["date"]),
                "url": url_for("main.activity_detail", activity_id=activity.id),
            }


def _next_position(db, week_id, day_index):
    highest = (
        db.query(func.max(CoachSession.position))
        .filter(CoachSession.week_id == week_id, CoachSession.day_index == day_index)
        .scalar()
    )
    return 0 if highest is None else highest + 1


@bp.route("/")
def board_page():
    db = get_db()
    today = date.today()
    try:
        week_start = board.parse_week_param(request.args.get("week"), today)
    except ValueError:
        abort(400)
    units = _get_units(db.query(UserSettings).first())

    sessions = _week_sessions(db, week_start, units)
    _attach_matches(db, sessions, week_start, units)
    selected_id = request.args.get("session", type=int)
    selected = next((s for s in sessions if s["id"] == selected_id), None)

    this_week = week_start_for(today)
    today_sessions = [
        s for s in (sessions if week_start == this_week else _week_sessions(db, this_week, units))
        if s["day_index"] == today.weekday()
    ]
    week_end = week_start + timedelta(days=DAYS_PER_WEEK - 1)

    return render_template(
        "coach.html",
        days=board.build_week_view(week_start, today, sessions),
        week_start=week_start,
        week_number=week_start.isocalendar()[1],
        range_label=f"{week_start:%b %d} – {week_end:%b %d, %Y}",
        prev_url=_board_url(week_start - timedelta(days=DAYS_PER_WEEK)),
        next_url=_board_url(week_start + timedelta(days=DAYS_PER_WEEK)),
        this_week_url=_board_url(this_week),
        is_this_week=week_start == this_week,
        selected=selected,
        templates=[(key, t["focus"]) for key, t in SESSION_TEMPLATES.items()],
        today=today,
        today_sessions=today_sessions,
        provider_connected=False,
        user_statuses=USER_STATUSES,
        distance_unit=analytics.convert_distance(0.0, units)[1],
    )


@bp.route("/sessions", methods=["POST"])
def add_session():
    db = get_db()
    template = SESSION_TEMPLATES.get(request.form.get("template", ""))
    if template is None:
        abort(400)
    day_index = _day_index(request.form.get("day_index"))
    try:
        week_start = week_start_for(date.fromisoformat(request.form.get("week_start", "")))
    except ValueError:
        abort(400)

    week = db.query(CoachWeek).filter_by(week_start=week_start).first()
    if week is None:
        week = CoachWeek(week_start=week_start)
        db.add(week)
        db.flush()

    exercises = {e.slug: e for e in db.query(CoachExercise).filter(CoachExercise.slug.isnot(None))}
    session = CoachSession(
        week=week,
        day_index=day_index,
        position=_next_position(db, week.id, day_index),
        kind=template["kind"],
        focus=template["focus"],
    )
    for position, item in enumerate(template["items"]):
        session.items.append(
            CoachSessionItem(
                exercise=exercises[item["slug"]],
                position=position,
                sets=item.get("sets"),
                reps=item.get("reps"),
                duration_seconds=item.get("duration_seconds"),
                distance_meters=item.get("distance_meters"),
            )
        )
    db.add(session)
    db.commit()
    return redirect(_board_url(week_start, session.id), code=303)


def _get_session(db, session_id):
    session = db.get(CoachSession, session_id)
    if session is None:
        abort(404)
    return session


@bp.route("/sessions/<int:session_id>/move", methods=["POST"])
def move_session(session_id):
    db = get_db()
    session = _get_session(db, session_id)
    day_index = _day_index(request.form.get("day_index"))
    if day_index != session.day_index:
        session.position = _next_position(db, session.week_id, day_index)
        session.day_index = day_index
        db.commit()
    if _is_fetch():
        return "", 204
    return redirect(_board_url(session.week.week_start, session.id), code=303)


@bp.route("/sessions/<int:session_id>/status", methods=["POST"])
def set_status(session_id):
    db = get_db()
    session = _get_session(db, session_id)
    status = request.form.get("status", "")
    if status not in USER_STATUSES:
        abort(400)
    session.status = status
    if status == "planned":
        # Back to planned frees the activity so the matcher can offer it again.
        session.matched_activity_id = None
    db.commit()
    return redirect(_board_url(session.week.week_start, session.id), code=303)


@bp.route("/sessions/<int:session_id>/confirm", methods=["POST"])
def confirm_match(session_id):
    db = get_db()
    session = _get_session(db, session_id)
    activity_id = request.form.get("activity_id", type=int)
    # Re-run the matcher rather than trusting the form: only an activity it
    # currently offers for this session can be confirmed.
    results, _activities = _week_matches(db, session.week.week_start)
    if activity_id is None or activity_id not in results.get(session.id, {}).get("activity_ids", []):
        abort(400)
    session.status = "done"
    session.matched_activity_id = activity_id
    db.commit()
    return redirect(_board_url(session.week.week_start, session.id), code=303)


@bp.route("/sessions/<int:session_id>/delete", methods=["POST"])
def delete_session(session_id):
    db = get_db()
    session = _get_session(db, session_id)
    week_start = session.week.week_start
    db.delete(session)
    db.commit()
    return redirect(_board_url(week_start), code=303)


@bp.route("/items/<int:item_id>/volume", methods=["POST"])
def edit_volume(item_id):
    db = get_db()
    item = db.get(CoachSessionItem, item_id)
    if item is None:
        abort(404)
    units = _get_units(db.query(UserSettings).first())
    shape = volume.item_shape(
        {
            "sets": item.sets,
            "reps": item.reps,
            "duration_seconds": item.duration_seconds,
            "distance_meters": item.distance_meters,
        }
    )
    try:
        updates = volume.parse_volume(shape, request.form, units)
    except ValueError:
        abort(400)
    for field, value in updates.items():
        setattr(item, field, value)
    db.commit()
    return redirect(_board_url(item.session.week.week_start, item.session_id), code=303)


@bp.route("/items/<int:item_id>/delete", methods=["POST"])
def delete_item(item_id):
    db = get_db()
    item = db.get(CoachSessionItem, item_id)
    if item is None:
        abort(404)
    session = item.session
    db.delete(item)
    db.commit()
    return redirect(_board_url(session.week.week_start, session.id), code=303)

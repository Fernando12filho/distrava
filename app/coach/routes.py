import json
import queue
import threading
from collections import defaultdict
from datetime import date, datetime, timedelta

from flask import Blueprint, Response, abort, jsonify, redirect, render_template, request, stream_with_context, url_for
from sqlalchemy import func

from app import analytics
from app.coach import agent, assistant, board, hard_sets, progression, rebalancer, set_log, volume
from app.coach import profile as coach_profile
from app.coach import tools as coach_tools
from app.coach.keystore import KeystoreUnavailable
from app.coach.providers import ProviderError
from app.coach.usage import call_cost, format_cost
from app.coach.catalog import SESSION_TEMPLATES
from app.coach.matcher import SESSION_ACTIVITY_TYPES, match_sessions
from app.coach.week import DAYS_PER_WEEK, week_start_for
from app.models import (
    PLANNED_EFFORTS,
    Activity,
    ActivityStream,
    CoachConversation,
    CoachExercise,
    CoachProposal,
    CoachSession,
    CoachSessionItem,
    CoachSetLog,
    CoachWeek,
    TrainingProfile,
    UserSettings,
)
from app.routes import _effort_view, _get_units, _hr_quality, _resolve_hr_profile, _trim2, get_db
from app.training_rules import (
    HARD_SET_MAX_RIR,
    SETS_PER_MUSCLE_IMPROVE_MIN,
    DISTANCE_BASELINE_WEEKS,
    RETURN_WEEK_FACTORS,
    SETS_PER_MUSCLE_MAINTAIN_MIN,
    Z3_BOUNDARY_FRACTION_HRR,
)

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


def _plan_of(item):
    return {
        "sets": item.sets,
        "reps": item.reps,
        "duration_seconds": item.duration_seconds,
        "distance_meters": item.distance_meters,
    }


def _log_kind(item):
    return "seconds" if item.duration_seconds and not item.reps else "reps"


def _logged_view(item, units):
    return [
        {
            "id": s.id,
            "set_number": s.set_number,
            "reps": "" if s.reps is None else s.reps,
            "seconds": "" if s.duration_seconds is None else s.duration_seconds,
            "weight": set_log.weight_value(s.weight_kg, units),
            "rir": "" if s.rir is None else s.rir,
            "hard": set_log.is_hard(s.rir),
        }
        for s in item.logged_sets
    ]


def _session_view(session, units):
    items = [
        {
            "id": item.id,
            "name": item.exercise.name,
            "muscle": item.exercise.muscle_group,
            "sets": item.sets,
            "reps": item.reps,
            "duration_seconds": item.duration_seconds,
            "distance_meters": item.distance_meters,
            "log_kind": _log_kind(item),
            "logged": _logged_view(item, units),
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
        "planned_effort": session.planned_effort,
        "summary": board.session_summary(session.kind, items, units),
        "exercises": items,
        "distance_meters": sum(i["distance_meters"] or 0 for i in items) or None,
        "duration_seconds": sum((i["duration_seconds"] or 0) * (i["sets"] or 1) for i in items) or None,
        "matched_activity_id": session.matched_activity_id,
        "has_log": any(i["logged"] for i in items),
        "matched": None,
        "suggestion": None,
    }


def _week_sessions(db, week_start, units):
    week = db.query(CoachWeek).filter_by(week_start=week_start).first()
    return [_session_view(s, units) for s in week.sessions] if week else []


# Shared by the Coach panel and the dashboard so both always show the same day.
def today_plan(db, today, units):
    return [s for s in _week_sessions(db, week_start_for(today), units) if s["day_index"] == today.weekday()]


def _week_logged_sets(db, week_start):
    week = db.query(CoachWeek).filter_by(week_start=week_start).first()
    if week is None:
        return []
    return [
        {"muscle_group": item.exercise.muscle_group, "rir": logged.rir, "session_id": session.id}
        for session in week.sessions
        for item in session.items
        for logged in item.logged_sets
    ]


# RULE-LOAD-02 + D1: minutes above the estimated threshold, or None when the
# workout has too little second-by-second heart rate to say (D10).
def _z3_minutes(activity, stream, resting_hr, max_hr):
    if stream is None or not stream.stream_data.get("hr"):
        return None
    shown, _note = _hr_quality(activity, stream)
    if not shown:
        return None
    boundary = resting_hr + Z3_BOUNDARY_FRACTION_HRR * (max_hr - resting_hr)
    return analytics.minutes_above(stream.stream_data["time"], stream.stream_data["hr"], boundary)


def _rebalancer_session(session, day_offset, activity, stream, hr_profile):
    """Plain dict for the pure rebalancer; day_offset shifts last week's days negative."""
    logged = [(item.exercise.muscle_group, s.rir) for item in session.items for s in item.logged_sets]
    groups = {item.exercise.muscle_group for item in session.items} - {None, "none"}
    return {
        "id": session.id,
        "day_index": session.day_index + day_offset,
        "position": session.position,
        "kind": session.kind,
        "status": session.status,
        "focus": session.focus,
        "planned_effort": session.planned_effort,
        "srpe": activity.session_rpe if activity else None,
        "z3_minutes": _z3_minutes(activity, stream, *hr_profile) if activity else None,
        "muscle_groups": groups,
        "hard_set_groups": {g for g, rir in logged if set_log.is_hard(rir)} - {None, "none"},
        "rated_set_groups": {g for g, rir in logged if rir is not None} - {None, "none"},
    }


# The week plus last week's final days, which still count for spacing.
_LOOKBACK_DAYS = 2


def _rebalancer_week(db, week_start):
    weeks = [(week_start, 0), (week_start - timedelta(days=DAYS_PER_WEEK), -DAYS_PER_WEEK)]
    sessions = []
    for start, offset in weeks:
        week = db.query(CoachWeek).filter_by(week_start=start).first()
        if week is None:
            continue
        sessions += [s for s in week.sessions if offset == 0 or s.day_index >= DAYS_PER_WEEK - _LOOKBACK_DAYS]
    activity_ids = [s.matched_activity_id for s in sessions if s.matched_activity_id]
    activities = {a.id: a for a in db.query(Activity).filter(Activity.id.in_(activity_ids))} if activity_ids else {}
    streams = (
        {st.activity_id: st for st in db.query(ActivityStream).filter(ActivityStream.activity_id.in_(activity_ids))}
        if activity_ids
        else {}
    )
    hr_profile = _resolve_hr_profile(db.query(UserSettings).first(), date.today())
    return [
        _rebalancer_session(
            s,
            0 if s.week.week_start == week_start else -DAYS_PER_WEEK,
            activities.get(s.matched_activity_id),
            streams.get(s.matched_activity_id),
            hr_profile,
        )
        for s in sessions
    ]


_CONFLICT_TEXT = {
    ("RULE-REC-02", "cap"): "More than {cap} hard runs this week",
    ("RULE-REC-02", "close"): "Two hard runs less than {runs_h} h apart",
    ("RULE-REC-01", "close"): "{groups} trained hard twice within {muscle_h} h",
    ("RULE-REC-04", "close"): "Hard legs in the {legs_h} h before a hard run",
}
_CONFLICT_VALUES = {
    "cap": rebalancer.MAX_HARD_RUNS_PER_WEEK,
    "runs_h": rebalancer.MIN_HOURS_BETWEEN_HARD_RUNS,
    "muscle_h": rebalancer.MIN_HOURS_SAME_MUSCLE_HARD,
    "legs_h": rebalancer.MIN_HOURS_HARD_LEGS_BEFORE_HARD_RUN,
}


def _day_label(day_index):
    return board.DOW_LABELS[day_index % DAYS_PER_WEEK].title() + (" (last week)" if day_index < 0 else "")


def _run_meters(db, start, end):
    """Imported running distance between two local dates (end excluded)."""
    # start_time is UTC; a day of margin each side, then filter on local dates.
    window = (datetime.combine(start - timedelta(days=1), datetime.min.time()), datetime.combine(end + timedelta(days=1), datetime.min.time()))
    runs = db.query(Activity).filter(Activity.activity_type == "Run", Activity.start_time >= window[0], Activity.start_time < window[1])
    return sum(a.distance_meters or 0.0 for a in runs if start <= a.local_start_time.date() < end)


def _last_workout_date(db, today):
    recent = db.query(Activity).filter(Activity.start_time < datetime.combine(today + timedelta(days=2), datetime.min.time()))
    dates = [a.local_start_time.date() for a in recent.order_by(Activity.start_time.desc()).limit(5)]
    done = db.query(CoachSession).filter(CoachSession.status.in_(("done", "partial")))
    dates += [s.week.week_start + timedelta(days=s.day_index) for s in done]
    dates = [d for d in dates if d <= today]
    return max(dates) if dates else None


# Ease-back scaling (D7) touches training volume only, not mobility or rest.
_EASE_KINDS = ("run", "ride", "gym")


def _easable_items(week, today_index):
    return [
        item
        for s in week.sessions
        if s.status == "planned" and s.kind in _EASE_KINDS and s.day_index >= today_index
        for item in s.items
        if progression.scale_item(_plan_of(item), RETURN_WEEK_FACTORS[0])
    ]


def _distance_label(meters, units):
    value, unit = analytics.convert_distance(meters, units)
    return f"{_trim2(value)} {unit}"


def _distance_inputs(db, week_start, today):
    """RULE-PROG-02 inputs: imported running so far this week, and each of the weeks before."""
    week_end = week_start + timedelta(days=DAYS_PER_WEEK)
    return {
        "so_far_meters": _run_meters(db, week_start, min(week_end, today + timedelta(days=1))),
        "previous_weeks_meters": [
            _run_meters(db, week_start - timedelta(days=DAYS_PER_WEEK * k), week_start - timedelta(days=DAYS_PER_WEEK * (k - 1)))
            for k in range(1, DISTANCE_BASELINE_WEEKS + 1)
        ],
    }


def _progression_view(db, week_start, today, today_index, rebalancer_sessions):
    week = db.query(CoachWeek).filter_by(week_start=week_start).first()
    units = _get_units(db.query(UserSettings).first())

    # RULE-PROG-02: imported runs so far plus planned runs still to come.
    planned_ahead = sum(
        item.distance_meters or 0.0
        for s in (week.sessions if week else [])
        if s.kind == "run" and s.status == "planned" and s.day_index >= today_index
        for item in s.items
    )
    inputs = _distance_inputs(db, week_start, today)
    change = progression.distance_change(inputs["so_far_meters"] + planned_ahead, inputs["previous_weeks_meters"])
    distance = (
        {
            "level": change["level"],
            "pct": _trim2(change["pct"]),
            "this_week": _distance_label(change["this_week_meters"], units),
            "baseline": _distance_label(change["baseline_meters"], units),
        }
        if change
        else None
    )

    # RULE-PROG-04 + D7: offered only for the current week, once, with volume left.
    days_off = progression.break_days(_last_workout_date(db, today), today)
    is_this_week = week_start == week_start_for(today)
    can_ease = bool(week and is_this_week and week.eased_factor is None and _easable_items(week, today_index))
    options = progression.return_options(days_off) if can_ease else []

    # RULE-WEEK-01, by session count.
    balance = progression.run_balance(
        [rebalancer.effort(s)["hard"] for s in rebalancer_sessions if s["kind"] == "run" and s["day_index"] >= 0 and s["status"] != "skipped"]
    )
    return {
        "distance": distance,
        "baseline_weeks": DISTANCE_BASELINE_WEEKS,
        "days_off": days_off,
        "return_options": options,
        "eased": round(week.eased_factor * 100) if week and week.eased_factor else None,
        "balance": balance,
    }


def _week_check(db, week_start, today):
    sessions = _rebalancer_week(db, week_start)
    by_id = {s["id"]: s for s in sessions}
    conflicts = [
        {
            "rule": c["rule"],
            "text": _CONFLICT_TEXT[(c["rule"], c["reason"])].format(
                groups=", ".join(c["groups"]).replace("_", " ").capitalize(), **_CONFLICT_VALUES
            ),
            "sessions": [f"{_day_label(by_id[i]['day_index'])} {by_id[i]['focus']}" for i in c["session_ids"]],
        }
        for c in rebalancer.check_week(sessions)
    ]
    this_week = week_start == week_start_for(today)
    # Past weeks are history: nothing left to move into.
    today_index = today.weekday() if this_week else (-1 if week_start > today else DAYS_PER_WEEK)
    skipped = [
        {
            "id": s["id"],
            "label": f"{_day_label(s['day_index'])} {s['focus']}",
            "options": [(d, _day_label(d)) for d in rebalancer.move_options(sessions, s["id"], today_index)],
        }
        for s in sessions
        if s["status"] == "skipped" and s["day_index"] >= 0
    ]
    return {
        "conflicts": conflicts,
        "skipped": skipped,
        "today_index": today_index,
        "sessions": sessions,
        "progression": _progression_view(db, week_start, today, today_index, sessions),
    }


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
            Activity.activity_type.in_([t for types in SESSION_ACTIVITY_TYPES.values() for t in types]),
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
                "effort": _effort_view(activity),
            }


def _next_position(db, week_id, day_index):
    highest = (
        db.query(func.max(CoachSession.position))
        .filter(CoachSession.week_id == week_id, CoachSession.day_index == day_index)
        .scalar()
    )
    return 0 if highest is None else highest + 1


_THREAD_NOTES = {
    "pending": "Preview on the board",
    "accepted": "Applied",
    "undone": "Undone",
    "discarded": "Discarded",
    "stale": "Not applied: the week changed",
}


def _ghost_view(state, units):
    return {
        "kind": state["kind"],
        "kind_label": KIND_LABELS[state["kind"]],
        "focus": state["focus"],
        "summary": board.session_summary(state["kind"], state["items"], units),
        "planned_effort": state["planned_effort"],
    }


# D3: a pending proposal shows in place — what it changes faded, what it would
# become dashed beside it — with the reason and the exact changes above.
def _coach_view(db, week_start, sessions, days, units):
    week = db.query(CoachWeek).filter_by(week_start=week_start).first()
    conversation = _active_conversation(db)
    proposals = list(week.proposals) if week else []
    latest = proposals[-1] if proposals else None
    pending = next((p for p in proposals if p.status == "pending"), None)
    before, after = (pending.before, pending.after) if pending else ({}, {})
    if pending is None:
        # AC-20: a draft asked from another week shows here too, with its Accept.
        for waiting in db.query(CoachProposal).filter_by(status="pending"):
            part = (waiting.other_weeks or {}).get(week_start.isoformat())
            if part:
                pending, before, after = waiting, part["before"], part["after"]
    if pending:
        changed = {int(k) for k in before}
        for session in sessions:
            if session["id"] in changed:
                session["ghost"] = "remove"
        for day in days:
            day["ghosts"] = [
                _ghost_view(state, units)
                for state in sorted((s for s in after.values() if s), key=lambda s: s["position"])
                if state["day_index"] == day["index"]
            ]
    return {
        "pending": pending,
        "applied": latest if latest is not None and _undoable(db, latest) else None,
        "stale": latest if latest is not None and latest.status == "stale" else None,
        "thread": [
            {
                "request": p.request,
                "reply": p.reply,
                "note": _THREAD_NOTES.get(p.status),
                "steps": p.steps or [],
                # #43: the chat is the same on every week, so a message from another week says which.
                "week_label": None if p.week.week_start == week_start else f"Week of {p.week.week_start:%b %d}",
            }
            for p in (conversation.proposals if conversation else [])
        ],
    }


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
    today_sessions = today_plan(db, today, units)
    week_end = week_start + timedelta(days=DAYS_PER_WEEK - 1)
    days = board.build_week_view(week_start, today, sessions)
    coach = _coach_view(db, week_start, sessions, days, units)

    return render_template(
        "coach.html",
        days=days,
        coach=coach,
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
        hard_sets=hard_sets.weekly_hard_sets(_week_logged_sets(db, week_start)),
        week_check=_week_check(db, week_start, today),
        week_rules={
            **_CONFLICT_VALUES,
            "srpe_hard": rebalancer.SRPE_HARD_MIN,
            "z3_minutes": rebalancer.Z3_MIN_MINUTES_HARD,
        },
        hard_set_max_rir=HARD_SET_MAX_RIR,
        sets_improve_min=SETS_PER_MUSCLE_IMPROVE_MIN,
        sets_maintain_min=SETS_PER_MUSCLE_MAINTAIN_MIN,
        provider_connected=bool(assistant.api_key()),
        user_statuses=USER_STATUSES,
        distance_unit=analytics.convert_distance(0.0, units)[1],
        weight_unit=analytics.convert_weight(0.0, units)[1],
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


# A finished gym session starts out as its plan, set by set, for the user to
# correct. Once anything is logged it's never refilled, so going back to
# "planned" and done again keeps what was entered (and any set removed).
def _fill_logged_sets(session):
    if session.kind != "gym" or any(item.logged_sets for item in session.items):
        return
    for item in session.items:
        for row in set_log.planned_sets(_plan_of(item)):
            item.logged_sets.append(CoachSetLog(**row))


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


@bp.route("/sessions/<int:session_id>/planned-effort", methods=["POST"])
def set_planned_effort(session_id):
    db = get_db()
    session = _get_session(db, session_id)
    value = request.form.get("effort", "")
    if value and value not in PLANNED_EFFORTS:
        abort(400)
    session.planned_effort = value or None
    db.commit()
    if _is_fetch():
        return "", 204
    return redirect(_board_url(session.week.week_start, session.id), code=303)


# RULE-PROG-01: a skipped session moves only to a day the rebalancer allows; the
# same check that offers the day runs again here, so a stale page can't stack it.
@bp.route("/sessions/<int:session_id>/reschedule", methods=["POST"])
def reschedule_session(session_id):
    db = get_db()
    session = _get_session(db, session_id)
    if session.status != "skipped":
        abort(400)
    day_index = _day_index(request.form.get("day_index"))
    week_start = session.week.week_start
    check = _week_check(db, week_start, date.today())
    allowed = rebalancer.move_options(check["sessions"], session.id, check["today_index"])
    if day_index not in allowed:
        abort(400)
    session.position = _next_position(db, session.week_id, day_index)
    session.day_index = day_index
    session.status = "planned"
    db.commit()
    return redirect(_board_url(week_start, session.id), code=303)


def _week_or_404(db, raw):
    try:
        week_start = date.fromisoformat(raw)
    except ValueError:
        abort(404)
    week = db.query(CoachWeek).filter_by(week_start=week_start).first()
    if week is None:
        abort(404)
    return week


# D7: scale the rest of the week's planned volume by the factor you picked,
# keeping each changed value so undo can put it back exactly (AC-10).
@bp.route("/weeks/<week>/ease", methods=["POST"])
def ease_week(week):
    db = get_db()
    coach_week = _week_or_404(db, week)
    try:
        factor = float(request.form.get("factor", ""))
    except ValueError:
        abort(400)
    if factor not in RETURN_WEEK_FACTORS:
        abort(400)
    check = _week_check(db, coach_week.week_start, date.today())
    if not check["progression"]["return_options"]:
        abort(400)
    snapshot = {}
    for item in _easable_items(coach_week, check["today_index"]):
        changes = progression.scale_item(_plan_of(item), factor)
        snapshot[str(item.id)] = {field: getattr(item, field) for field in changes}
        for field, value in changes.items():
            setattr(item, field, value)
    coach_week.eased_factor = factor
    coach_week.eased_snapshot = snapshot
    db.commit()
    return redirect(_board_url(coach_week.week_start), code=303)


@bp.route("/weeks/<week>/ease/undo", methods=["POST"])
def undo_ease(week):
    db = get_db()
    coach_week = _week_or_404(db, week)
    if coach_week.eased_factor is None:
        abort(400)
    for item_id, values in (coach_week.eased_snapshot or {}).items():
        item = db.get(CoachSessionItem, int(item_id))
        if item is not None:
            for field, value in values.items():
                setattr(item, field, value)
    coach_week.eased_factor = None
    coach_week.eased_snapshot = None
    db.commit()
    return redirect(_board_url(coach_week.week_start), code=303)


# --- coach proposals (step 7) ------------------------------------------------------


def _first_changeable_day(week_start, today):
    """Days before this index are history; 7 means the whole week is."""
    if week_start == week_start_for(today):
        return today.weekday()
    return 0 if week_start > today else DAYS_PER_WEEK


def _exercise_key(exercise):
    return exercise.slug or f"custom:{exercise.id}"


def _session_state(session):
    return {
        "id": session.id,
        "day_index": session.day_index,
        "position": session.position,
        "kind": session.kind,
        "focus": session.focus,
        "status": session.status,
        "planned_effort": session.planned_effort,
        "locked": bool(session.matched_activity_id or session.checkins or any(i.logged_sets for i in session.items)),
        "items": [
            {"id": item.id, "position": item.position, "exercise": _exercise_key(item.exercise), **_plan_of(item)}
            for item in session.items
        ],
    }


def _week_state(week, today):
    return {
        "today_index": _first_changeable_day(week.week_start, today),
        "sessions": [_session_state(s) for s in week.sessions],
    }


def _catalog(db):
    return {
        e.slug: {k: getattr(e, k) for k in ("name", "category", "muscle_group", "equipment", "activity_type")}
        for e in db.query(CoachExercise).filter(CoachExercise.slug.isnot(None)).order_by(CoachExercise.slug)
    }


def _current(db, week, ids):
    """The board now, for the sessions a proposal touches (JSON keys are strings)."""
    sessions = {s.id: s for s in week.sessions} if week is not None else {}
    return {str(i): (_session_state(sessions[int(i)]) if int(i) in sessions else None) for i in ids}


def _exercise_for(db, key):
    if key.startswith("custom:"):
        return db.get(CoachExercise, int(key.split(":", 1)[1]))
    return db.query(CoachExercise).filter_by(slug=key).one()


# Writes sessions back exactly as recorded, ids included, so an undone removal
# comes back as the same row. Only planned sessions with nothing logged are ever
# recorded (the tools refuse the rest), so no logged sets or check-ins are lost.
def _write_states(db, week, states):
    # Exercise lookups would otherwise flush a recreated row before it's filled in.
    with db.no_autoflush:
        for key, state in states.items():
            _write_state(db, week, int(key), state)


def _write_state(db, week, session_id, state):
    session = db.get(CoachSession, session_id)
    if state is None:
        if session is not None:
            db.delete(session)
        return
    if session is None:
        session = CoachSession(id=session_id, week=week)
        db.add(session)
    for field in ("day_index", "position", "kind", "focus", "status", "planned_effort"):
        setattr(session, field, state[field])
    items = {item.id: item for item in session.items}
    for item_state in state["items"]:
        item = items.pop(item_state["id"], None)
        if item is None:
            item = CoachSessionItem(id=item_state["id"])
            session.items.append(item)
        item.position = item_state["position"]
        item.exercise = _exercise_for(db, item_state["exercise"])
        for field in ("sets", "reps", "duration_seconds", "distance_meters"):
            setattr(item, field, item_state[field])
    for leftover in items.values():
        session.items.remove(leftover)


def _create_new_sessions(db, week, before, after):
    """Sessions the coach added carry negative ids until accepted. They're created
    here with real ids, and the maps come back rewritten with them so undo removes
    exactly these rows."""
    before, after = dict(before), dict(after)
    with db.no_autoflush:
        for key in [k for k in after if int(k) < 0]:
            state = after.pop(key)
            before.pop(key)
            session = CoachSession(week=week, **{f: state[f] for f in ("day_index", "position", "kind", "focus", "status", "planned_effort")})
            for item in state["items"]:
                session.items.append(
                    CoachSessionItem(
                        position=item["position"],
                        exercise=_exercise_for(db, item["exercise"]),
                        **{f: item[f] for f in ("sets", "reps", "duration_seconds", "distance_meters")},
                    )
                )
            db.add(session)
            db.flush()
            after[str(session.id)] = _session_state(session)
            before[str(session.id)] = None
    return before, after


def _week_parts(db, proposal):
    """(week or None, week_start, before, after) for every week a proposal changes."""
    parts = [(proposal.week, proposal.week.week_start, proposal.before, proposal.after)]
    for iso, part in (proposal.other_weeks or {}).items():
        start = date.fromisoformat(iso)
        parts.append((db.query(CoachWeek).filter_by(week_start=start).first(), start, part["before"], part["after"]))
    return parts


def _proposal_context(db, week, today, units):
    check = _week_check(db, week.week_start, today)
    profile = db.query(TrainingProfile).first()
    return check, {
        "week_start": week.week_start,
        "today": today,
        "units": units,
        "profile": {f: getattr(profile, f) for f in coach_profile.FIELDS if getattr(profile, f) is not None} if profile else {},
        "week_check": [f"{c['text']} ({', '.join(c['sessions'])}; {c['rule']})" for c in check["conflicts"]],
        "distance": _distance_inputs(db, week.week_start, today),
    }


def _week_loader(db, today):
    """Another week for the coach's draft — reading never creates a week."""

    def load_week(week_start):
        found = db.query(CoachWeek).filter_by(week_start=week_start).first()
        state = _week_state(found, today) if found else {"today_index": _first_changeable_day(week_start, today), "sessions": []}
        return {"state": state, "rebalancer": _rebalancer_week(db, week_start)}

    return load_week


@bp.route("/weeks/<week>/ask", methods=["POST"])
def ask_coach(week):
    db = get_db()
    message = (request.form.get("message") or "").strip()
    if not message:
        abort(400)
    try:
        week_start = date.fromisoformat(week)
    except ValueError:
        abort(404)
    if week_start.weekday() != 0:
        abort(404)
    chosen = assistant.provider()
    if chosen is None:
        return redirect(_board_url(week_start), code=303)

    coach_week = db.query(CoachWeek).filter_by(week_start=week_start).first()
    if coach_week is None:
        coach_week = CoachWeek(week_start=week_start)
        db.add(coach_week)
        db.flush()
    # One preview at a time: a new request replaces the one still waiting, in any week.
    for waiting in db.query(CoachProposal).filter_by(status="pending"):
        waiting.status = "discarded"
    db.commit()

    today = date.today()
    units = _get_units(db.query(UserSettings).first())
    state = _week_state(coach_week, today)
    catalog = _catalog(db)
    check, context = _proposal_context(db, coach_week, today, units)

    def complete(system, messages, tools, on_text=None):
        return assistant.run_task(db, chosen, "coach", system, messages, tools=tools, on_text=on_text)

    conversation = _active_conversation(db) or CoachConversation()
    history = [
        {"request": p.request, "reply": p.reply, "status": p.status, "week_start": p.week.week_start} for p in conversation.proposals
    ]

    def run(on_event=None):
        steps = []

        def record(event):
            if event["type"] == "step":
                steps.append(event["text"])
            on_event(event)

        try:
            readers = {"load_week": _week_loader(db, today)}
            result = agent.propose(
                complete, state, catalog, check["sessions"], message, context, history, readers, on_event=record if on_event else None
            )
        except ProviderError as err:
            result = {"status": "failed", "reply": str(err), "calls": [], "after": None, "changes": []}
        _save_proposal(db, coach_week, conversation, message, result, steps or None)

    if "text/event-stream" in request.headers.get("Accept", ""):
        return _event_stream(run, _board_url(week_start))
    run()
    return redirect(_board_url(week_start), code=303)


def _event_stream(run, done_url):
    """Streams one coach request as server-sent events (#43). The request runs in a
    worker thread and hands its events over a queue; this thread only waits on that
    queue, so the database session is never used by both at once. The last event,
    "done", tells the page to fetch the saved board."""
    events = queue.Queue()

    def work():
        try:
            run(events.put)
        finally:
            events.put(None)

    def frames():
        threading.Thread(target=work, daemon=True).start()
        while (event := events.get()) is not None:
            yield f"data: {json.dumps(event)}\n\n"
        yield f"data: {json.dumps({'type': 'done', 'url': done_url})}\n\n"

    return Response(stream_with_context(frames()), mimetype="text/event-stream", headers={"Cache-Control": "no-cache"})


def _save_proposal(db, coach_week, conversation, message, result, steps):
    """Stores one coach request and what came of it, in the conversation it belongs to."""
    before = after = other_weeks = None
    week_start = coach_week.week_start
    if result["status"] == "pending":
        parts = dict(result["weeks"])
        here = parts.pop(week_start.isoformat(), {"before": {}, "after": {}})
        before, after = here["before"], here["after"]
        other_weeks = {iso: {**part, "created_week": False} for iso, part in parts.items()} or None
    db.add(
        CoachProposal(
            week=coach_week,
            conversation=conversation,
            request=message,
            reply=result["reply"],
            status=result["status"],
            calls=result["calls"],
            changes=result["changes"],
            before=before,
            after=after,
            other_weeks=other_weeks,
            steps=steps,
        )
    )
    db.commit()


def _active_conversation(db):
    return db.query(CoachConversation).order_by(CoachConversation.id.desc()).first()


@bp.route("/conversations", methods=["POST"])
def new_conversation():
    """New chat (#43): the coach starts without the earlier turns, and a preview
    still waiting belonged to that chat, so it goes too."""
    db = get_db()
    try:
        week_start = date.fromisoformat(request.form.get("week", ""))
    except ValueError:
        abort(400)
    if week_start.weekday() != 0:
        abort(400)
    for waiting in db.query(CoachProposal).filter_by(status="pending"):
        waiting.status = "discarded"
    db.add(CoachConversation())
    db.commit()
    return redirect(_board_url(week_start), code=303)


def _proposal_or_404(db, proposal_id):
    proposal = db.get(CoachProposal, proposal_id)
    if proposal is None:
        abort(404)
    return proposal


@bp.route("/proposals/<int:proposal_id>/accept", methods=["POST"])
def accept_proposal(proposal_id):
    db = get_db()
    proposal = _proposal_or_404(db, proposal_id)
    if proposal.status != "pending":
        abort(400)
    parts = _week_parts(db, proposal)
    # AC-04: a manual edit since the preview, in any of its weeks, wins; nothing is applied.
    if any(_current(db, week, before) != before for week, _start, before, _after in parts):
        proposal.status = "stale"
    else:
        # AC-20: every week of the draft, or none.
        other_weeks = {}
        for week, start, before, after in parts:
            created = week is None
            if created:
                week = CoachWeek(week_start=start)
                db.add(week)
                db.flush()
            before, after = _create_new_sessions(db, week, before, after)
            _write_states(db, week, after)
            if week is proposal.week:
                proposal.before, proposal.after = before, after
            else:
                other_weeks[start.isoformat()] = {"before": before, "after": after, "created_week": created}
        proposal.other_weeks = other_weeks or None
        proposal.status = "accepted"
    db.commit()
    return redirect(_board_url(proposal.week.week_start), code=303)


@bp.route("/proposals/<int:proposal_id>/discard", methods=["POST"])
def discard_proposal(proposal_id):
    db = get_db()
    proposal = _proposal_or_404(db, proposal_id)
    if proposal.status != "pending":
        abort(400)
    proposal.status = "discarded"
    db.commit()
    return redirect(_board_url(proposal.week.week_start), code=303)


def _undoable(db, proposal):
    return proposal.status == "accepted" and all(_current(db, week, after) == after for week, _start, _before, after in _week_parts(db, proposal))


@bp.route("/proposals/<int:proposal_id>/undo", methods=["POST"])
def undo_proposal(proposal_id):
    db = get_db()
    proposal = _proposal_or_404(db, proposal_id)
    if proposal.status != "accepted":
        abort(400)
    # Once a changed session is used or edited, undo would overwrite your
    # record, so it is no longer offered.
    if _undoable(db, proposal):
        for week, start, before, _after in _week_parts(db, proposal):
            _write_states(db, week, before)
            part = (proposal.other_weeks or {}).get(start.isoformat())
            # A week the accept created goes again, so undo is byte-for-byte (AC-10).
            if part and part["created_week"]:
                db.flush()
                db.refresh(week)
                if not week.sessions and not week.proposals:
                    db.delete(week)
        proposal.status = "undone"
        db.commit()
    return redirect(_board_url(proposal.week.week_start), code=303)


def _settings_url(status):
    return url_for("main.settings_page", ai=status, _anchor="ai")


# AC-01: the key goes straight to the keychain; it is never echoed, logged or
# stored anywhere else, and a failure says so instead of falling back.
@bp.route("/settings/key", methods=["POST"])
def save_key():
    try:
        assistant.keystore().set(request.form.get("api_key", ""))
    except ValueError:
        return redirect(_settings_url("invalid"), code=303)
    except KeystoreUnavailable:
        return redirect(_settings_url("unavailable"), code=303)
    return redirect(_settings_url("saved"), code=303)


@bp.route("/settings/key/delete", methods=["POST"])
def delete_key():
    try:
        assistant.keystore().delete()
    except KeystoreUnavailable:
        return redirect(_settings_url("unavailable"), code=303)
    return redirect(_settings_url("removed"), code=303)


@bp.route("/settings/test", methods=["POST"])
def test_connection():
    chosen = assistant.provider()
    if chosen is None:
        return jsonify(ok=False, message="No API key saved yet.")
    try:
        result = assistant.run_task(
            get_db(), chosen, "connection_test", system=None, messages=[{"role": "user", "content": "Reply with the single word OK."}]
        )
    except ProviderError as err:
        return jsonify(ok=False, message=str(err))
    cost = format_cost(call_cost(result["model"], result["usage"]))
    return jsonify(ok=True, message=f"Connected to {result['model']}. This test cost {cost}.")


@bp.route("/sessions/<int:session_id>/status", methods=["POST"])
def set_status(session_id):
    db = get_db()
    session = _get_session(db, session_id)
    status = request.form.get("status", "")
    if status not in USER_STATUSES:
        abort(400)
    session.status = status
    if status in ("done", "partial"):
        _fill_logged_sets(session)
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
    _fill_logged_sets(session)
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
    shape = volume.item_shape(_plan_of(item))
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


def _get_set(db, set_id):
    logged = db.get(CoachSetLog, set_id)
    if logged is None:
        abort(404)
    return logged


@bp.route("/sets/<int:set_id>", methods=["POST"])
def edit_set(set_id):
    db = get_db()
    logged = _get_set(db, set_id)
    units = _get_units(db.query(UserSettings).first())
    try:
        updates = set_log.parse_set(_log_kind(logged.item), request.form, units)
    except ValueError:
        abort(400)
    for field, value in updates.items():
        setattr(logged, field, value)
    db.commit()
    session = logged.item.session
    return redirect(_board_url(session.week.week_start, session.id), code=303)


@bp.route("/sets/<int:set_id>/delete", methods=["POST"])
def delete_set(set_id):
    db = get_db()
    logged = _get_set(db, set_id)
    item = logged.item
    item.logged_sets.remove(logged)
    for number, remaining in enumerate(item.logged_sets, start=1):
        remaining.set_number = number
    db.commit()
    return redirect(_board_url(item.session.week.week_start, item.session_id), code=303)


@bp.route("/items/<int:item_id>/sets", methods=["POST"])
def add_set(item_id):
    db = get_db()
    item = db.get(CoachSessionItem, item_id)
    if item is None:
        abort(404)
    if volume.item_shape(_plan_of(item)) not in ("sets_reps", "sets_seconds"):
        abort(400)
    # An extra set usually repeats the last one; how hard it felt is the user's
    # call each time, so reps in reserve starts blank.
    last = item.logged_sets[-1] if item.logged_sets else None
    item.logged_sets.append(
        CoachSetLog(
            set_number=len(item.logged_sets) + 1,
            reps=last.reps if last else item.reps,
            duration_seconds=last.duration_seconds if last else item.duration_seconds,
            weight_kg=last.weight_kg if last else None,
        )
    )
    db.commit()
    return redirect(_board_url(item.session.week.week_start, item.session_id), code=303)

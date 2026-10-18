from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.coach.week import week_days, week_start_for
from app.models import (
    CoachCheckin,
    CoachExercise,
    CoachNote,
    CoachSession,
    CoachSessionItem,
    CoachWeek,
)

MONDAY = date(2026, 10, 19)


@pytest.fixture()
def exercise(db_session):
    exercise = CoachExercise(
        slug="bench_press",
        name="Bench press",
        category="strength",
        muscle_group="chest",
        equipment="barbell",
        intensity="hard",
    )
    db_session.add(exercise)
    db_session.commit()
    return exercise


@pytest.fixture()
def week(db_session):
    week = CoachWeek(week_start=MONDAY, goal="Sub-25 5K")
    db_session.add(week)
    db_session.commit()
    return week


def _session(week, **overrides):
    fields = dict(week=week, day_index=0, kind="gym", focus="Chest & Triceps")
    fields.update(overrides)
    return CoachSession(**fields)


def test_week_start_for_any_day_is_that_weeks_monday():
    assert week_start_for(date(2026, 10, 19)) == MONDAY
    assert week_start_for(date(2026, 10, 22)) == MONDAY
    assert week_start_for(date(2026, 10, 25)) == MONDAY


def test_week_days_are_seven_columns_monday_to_sunday():
    days = week_days(MONDAY)

    assert len(days) == 7
    assert days[0] == MONDAY
    assert days[-1] == date(2026, 10, 25)


def test_week_days_rejects_a_non_monday_start():
    with pytest.raises(ValueError):
        week_days(date(2026, 10, 20))


def test_week_start_must_be_a_monday(db_session):
    db_session.add(CoachWeek(week_start=date(2026, 10, 21)))

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_only_one_week_per_monday(db_session, week):
    db_session.add(CoachWeek(week_start=MONDAY))

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_sessions_are_ordered_by_day_then_position(db_session, week):
    db_session.add_all(
        [
            _session(week, day_index=2, position=0),
            _session(week, day_index=0, position=1),
            _session(week, day_index=0, position=0),
        ]
    )
    db_session.commit()

    assert [(s.day_index, s.position) for s in week.sessions] == [(0, 0), (0, 1), (2, 0)]


def test_new_session_is_planned_at_the_top_of_its_day(db_session, week):
    session = _session(week)
    db_session.add(session)
    db_session.commit()

    assert session.status == "planned"
    assert session.position == 0


@pytest.mark.parametrize("day_index", [-1, 7])
def test_session_day_index_stays_inside_the_week(db_session, week, day_index):
    db_session.add(_session(week, day_index=day_index))

    with pytest.raises(IntegrityError):
        db_session.commit()


@pytest.mark.parametrize("status", ["planned", "done", "partial", "skipped", "moved"])
def test_session_accepts_every_board_status(db_session, week, status):
    db_session.add(_session(week, status=status))
    db_session.commit()


def test_session_rejects_unknown_status(db_session, week):
    db_session.add(_session(week, status="missed"))

    with pytest.raises(IntegrityError):
        db_session.commit()


@pytest.mark.parametrize("kind", ["run", "ride", "gym", "mobility", "rest"])
def test_session_accepts_every_kind(db_session, week, kind):
    db_session.add(_session(week, kind=kind))
    db_session.commit()


def test_session_rejects_unknown_kind(db_session, week):
    db_session.add(_session(week, kind="crossfit"))

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_session_requires_a_focus(db_session, week):
    db_session.add(_session(week, focus=None))

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_rest_session_needs_no_exercises(db_session, week):
    db_session.add(_session(week, kind="rest", focus="Rest"))
    db_session.commit()

    assert db_session.query(CoachSession).one().items == []


def test_session_items_are_ordered_by_position(db_session, week, exercise):
    session = _session(week)
    session.items = [
        CoachSessionItem(exercise=exercise, position=1, sets=3, reps=10),
        CoachSessionItem(exercise=exercise, position=0, sets=4, reps=6),
    ]
    db_session.add(session)
    db_session.commit()
    db_session.expire_all()

    assert [(i.sets, i.reps) for i in db_session.query(CoachSession).one().items] == [(4, 6), (3, 10)]


def test_session_item_requires_an_exercise(db_session, week):
    session = _session(week)
    session.items.append(CoachSessionItem(sets=3, reps=10))
    db_session.add(session)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_deleting_a_week_deletes_sessions_items_and_checkins(db_session, week, exercise):
    session = _session(week)
    session.items.append(CoachSessionItem(exercise=exercise, sets=4, reps=6))
    session.checkins.append(CoachCheckin(energy=4))
    db_session.add(session)
    db_session.commit()

    db_session.delete(week)
    db_session.commit()

    assert db_session.query(CoachSession).count() == 0
    assert db_session.query(CoachSessionItem).count() == 0
    assert db_session.query(CoachCheckin).count() == 0
    assert db_session.query(CoachExercise).count() == 1


def test_deleting_a_session_keeps_the_rest_of_the_week(db_session, week, exercise):
    keep = _session(week, day_index=1, focus="Back & Biceps")
    drop = _session(week)
    drop.items.append(CoachSessionItem(exercise=exercise, sets=4, reps=6))
    db_session.add_all([keep, drop])
    db_session.commit()

    db_session.delete(drop)
    db_session.commit()

    assert [s.focus for s in db_session.query(CoachSession).all()] == ["Back & Biceps"]
    assert db_session.query(CoachSessionItem).count() == 0


def test_ac07_every_checkin_answer_is_skippable(db_session, week):
    session = _session(week)
    session.checkins.append(CoachCheckin())
    db_session.add(session)
    db_session.commit()

    checkin = db_session.query(CoachCheckin).one()
    assert (checkin.energy, checkin.effort_rpe, checkin.pain_location) == (None, None, None)


@pytest.mark.parametrize("field, value", [("energy", 0), ("energy", 6), ("effort_rpe", 0), ("effort_rpe", 11)])
def test_checkin_answers_stay_on_their_scales(db_session, week, field, value):
    session = _session(week)
    session.checkins.append(CoachCheckin(**{field: value}))
    db_session.add(session)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_note_stores_text_and_tags(db_session):
    db_session.add(CoachNote(text="Left knee sore after long run", tags=["pain", "knee"]))
    db_session.commit()

    note = db_session.query(CoachNote).one()
    assert note.tags == ["pain", "knee"]
    assert note.created_at is not None


def test_note_tags_default_to_empty(db_session):
    db_session.add(CoachNote(text="Felt great"))
    db_session.commit()

    assert db_session.query(CoachNote).one().tags == []


def test_custom_exercise_needs_no_catalog_slug(db_session):
    db_session.add_all(
        [
            CoachExercise(name="Trainer's sled push", category="strength", intensity="hard", is_custom=True),
            CoachExercise(name="Partner carry", category="strength", intensity="hard", is_custom=True),
        ]
    )
    db_session.commit()

    assert db_session.query(CoachExercise).filter_by(is_custom=True).count() == 2


def test_catalog_slugs_are_unique(db_session, exercise):
    db_session.add(CoachExercise(slug="bench_press", name="Dup", category="strength", intensity="hard"))

    with pytest.raises(IntegrityError):
        db_session.commit()

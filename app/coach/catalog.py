from app.models import CoachExercise

CATEGORIES = ("endurance", "strength", "mobility", "stretching", "meditation", "rest")

# The groups gym splits are named after ("Chest & Triceps", "Shoulders & Abs"),
# so the rebalancer can check "no hard sessions on the same group two days
# running" in code.
MUSCLE_GROUPS = (
    "chest",
    "back",
    "shoulders",
    "biceps",
    "triceps",
    "abs",
    "legs",
    "glutes",
    "full_body",
    "none",
)

EQUIPMENT = ("none", "barbell", "dumbbell", "kettlebell", "cable", "pullup_bar", "band", "mat", "bike")

# No fixed easy/moderate/hard per exercise: a squat is only hard when the sets
# were (RULE-LOAD-04), so hardness comes from the logged session, never the catalog.
def _entry(slug, name, category, muscle_group, equipment, activity_type=None):
    return dict(
        slug=slug,
        name=name,
        category=category,
        muscle_group=muscle_group,
        equipment=equipment,
        activity_type=activity_type,
    )


CATALOG = [
    _entry("recovery_run", "Recovery run", "endurance", "legs", "none", "Run"),
    _entry("easy_run", "Easy run", "endurance", "legs", "none", "Run"),
    _entry("long_run", "Long run", "endurance", "legs", "none", "Run"),
    _entry("tempo_run", "Tempo run", "endurance", "legs", "none", "Run"),
    _entry("intervals", "Intervals", "endurance", "legs", "none", "Run"),
    _entry("hill_repeats", "Hill repeats", "endurance", "legs", "none", "Run"),
    _entry("easy_ride", "Easy ride", "endurance", "legs", "bike", "Cycle"),
    _entry("walk", "Walk", "endurance", "legs", "none", "Walk"),
    _entry("back_squat", "Back squat", "strength", "legs", "barbell"),
    _entry("deadlift", "Deadlift", "strength", "legs", "barbell"),
    _entry("romanian_deadlift", "Romanian deadlift", "strength", "glutes", "barbell"),
    _entry("hip_thrust", "Hip thrust", "strength", "glutes", "barbell"),
    _entry("walking_lunge", "Walking lunge", "strength", "legs", "dumbbell"),
    _entry("calf_raise", "Calf raise", "strength", "legs", "none"),
    _entry("bench_press", "Bench press", "strength", "chest", "barbell"),
    _entry("dumbbell_bench_press", "Dumbbell bench press", "strength", "chest", "dumbbell"),
    _entry("incline_dumbbell_press", "Incline dumbbell press", "strength", "chest", "dumbbell"),
    _entry("push_up", "Push-up", "strength", "chest", "none"),
    _entry("dips", "Dips", "strength", "triceps", "none"),
    _entry("triceps_pushdown", "Triceps pushdown", "strength", "triceps", "cable"),
    _entry("overhead_press", "Overhead press", "strength", "shoulders", "barbell"),
    _entry("lateral_raise", "Lateral raise", "strength", "shoulders", "dumbbell"),
    _entry("face_pull", "Face pull", "strength", "shoulders", "cable"),
    _entry("pull_up", "Pull-up", "strength", "back", "pullup_bar"),
    _entry("barbell_row", "Barbell row", "strength", "back", "barbell"),
    _entry("dumbbell_row", "Dumbbell row", "strength", "back", "dumbbell"),
    _entry("dumbbell_curl", "Dumbbell curl", "strength", "biceps", "dumbbell"),
    _entry("kettlebell_swing", "Kettlebell swing", "strength", "full_body", "kettlebell"),
    _entry("plank", "Plank", "strength", "abs", "none"),
    _entry("dead_bug", "Dead bug", "strength", "abs", "mat"),
    _entry("hanging_knee_raise", "Hanging knee raise", "strength", "abs", "pullup_bar"),
    _entry("hip_mobility", "Hip mobility flow", "mobility", "none", "mat"),
    _entry("ankle_mobility", "Ankle mobility", "mobility", "none", "none"),
    _entry("thoracic_rotation", "Thoracic rotations", "mobility", "none", "mat"),
    _entry("hamstring_stretch", "Hamstring stretch", "stretching", "none", "band"),
    _entry("hip_flexor_stretch", "Hip flexor stretch", "stretching", "none", "mat"),
    _entry("full_body_stretch", "Full-body stretch", "stretching", "none", "mat"),
    _entry("box_breathing", "Box breathing", "meditation", "none", "none"),
    _entry("body_scan", "Body scan", "meditation", "none", "mat"),
    _entry("rest_day", "Rest", "rest", "none", "none"),
]


def _sets(slug, sets, reps):
    return {"slug": slug, "sets": sets, "reps": reps}


def _timed(slug, seconds, sets=None):
    return {"slug": slug, "sets": sets, "duration_seconds": seconds}


def _distance(slug, meters):
    return {"slug": slug, "distance_meters": meters}


# What "+" on a day offers. The focus is what the week shows; the items are a
# sensible default the user (or later the coach) edits.
SESSION_TEMPLATES = {
    "running_day": {"kind": "run", "focus": "Running day", "items": [_distance("easy_run", 8000.0)]},
    "chest_triceps": {
        "kind": "gym",
        "focus": "Chest & Triceps",
        "items": [
            _sets("bench_press", 4, 6),
            _sets("incline_dumbbell_press", 3, 10),
            _sets("dips", 3, 8),
            _sets("triceps_pushdown", 3, 12),
        ],
    },
    "back_biceps": {
        "kind": "gym",
        "focus": "Back & Biceps",
        "items": [_sets("pull_up", 4, 5), _sets("barbell_row", 4, 8), _sets("dumbbell_curl", 3, 10)],
    },
    "legs_glutes": {
        "kind": "gym",
        "focus": "Legs & Glutes",
        "items": [
            _sets("back_squat", 4, 6),
            _sets("romanian_deadlift", 3, 8),
            _sets("walking_lunge", 3, 10),
            _sets("calf_raise", 3, 15),
        ],
    },
    "shoulders_abs": {
        "kind": "gym",
        "focus": "Shoulders & Abs",
        "items": [
            _sets("overhead_press", 4, 6),
            _sets("lateral_raise", 3, 12),
            _sets("face_pull", 3, 15),
            _timed("plank", 45, sets=3),
            _sets("hanging_knee_raise", 3, 10),
        ],
    },
    "easy_ride": {"kind": "ride", "focus": "Easy ride", "items": [_timed("easy_ride", 2700)]},
    "mobility": {
        "kind": "mobility",
        "focus": "Mobility & stretch",
        "items": [_timed("hip_mobility", 600), _timed("full_body_stretch", 600)],
    },
    "rest": {"kind": "rest", "focus": "Rest", "items": []},
}


# Catalog rows belong to the app, so they're brought in line with CATALOG on
# every start (a renamed muscle group reaches existing databases). Custom
# exercises have no slug and are never touched.
def seed_catalog(db_session):
    existing = {e.slug: e for e in db_session.query(CoachExercise).filter(CoachExercise.slug.isnot(None))}
    for entry in CATALOG:
        row = existing.get(entry["slug"])
        if row is None:
            db_session.add(CoachExercise(**entry))
            continue
        for field, value in entry.items():
            if getattr(row, field) != value:
                setattr(row, field, value)
    db_session.commit()

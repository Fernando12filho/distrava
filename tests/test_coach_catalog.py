from app import parser
from app.coach import catalog
from app.models import SESSION_KINDS, CoachExercise


def test_catalog_slugs_are_unique():
    slugs = [entry["slug"] for entry in catalog.CATALOG]

    assert len(slugs) == len(set(slugs))


def test_every_entry_uses_the_fixed_vocabularies():
    for entry in catalog.CATALOG:
        assert entry["category"] in catalog.CATEGORIES, entry["slug"]
        assert entry["muscle_group"] in catalog.MUSCLE_GROUPS, entry["slug"]
        assert entry["equipment"] in catalog.EQUIPMENT, entry["slug"]


def test_ac_rule_load_04_catalog_carries_no_fixed_intensity():
    # "Leg day" is not hard by itself: hardness comes from what was done.
    for entry in catalog.CATALOG:
        assert "intensity" not in entry, entry["slug"]
    assert not hasattr(catalog, "INTENSITIES")


def test_catalog_covers_running_gym_and_foundations():
    categories = {entry["category"] for entry in catalog.CATALOG}

    assert categories == set(catalog.CATEGORIES)


def test_every_muscle_group_a_gym_split_names_has_exercises():
    trained = {entry["muscle_group"] for entry in catalog.CATALOG if entry["category"] == "strength"}

    assert {"chest", "back", "shoulders", "biceps", "triceps", "abs", "legs", "glutes"} <= trained


def test_endurance_entries_map_to_an_importable_activity_type():
    for entry in catalog.CATALOG:
        if entry["category"] == "endurance":
            assert entry["activity_type"] in parser.ACTIVITY_TYPE_MAP.values(), entry["slug"]
        else:
            assert entry["activity_type"] is None, entry["slug"]


def test_strength_entries_name_a_real_muscle_group():
    for entry in catalog.CATALOG:
        if entry["category"] == "strength":
            assert entry["muscle_group"] != "none", entry["slug"]


def test_session_templates_only_use_catalog_exercises():
    slugs = {entry["slug"] for entry in catalog.CATALOG}

    for key, template in catalog.SESSION_TEMPLATES.items():
        for item in template["items"]:
            assert item["slug"] in slugs, f"{key}: {item['slug']}"


def test_session_templates_use_known_kinds():
    for key, template in catalog.SESSION_TEMPLATES.items():
        assert template["kind"] in SESSION_KINDS, key


def test_rest_template_has_no_exercises_and_every_other_has_some():
    for key, template in catalog.SESSION_TEMPLATES.items():
        if template["kind"] == "rest":
            assert template["items"] == [], key
        else:
            assert template["items"], key


def test_template_items_carry_a_volume():
    for key, template in catalog.SESSION_TEMPLATES.items():
        for item in template["items"]:
            has_sets = item.get("sets") and item.get("reps")
            has_duration = item.get("duration_seconds")
            has_distance = item.get("distance_meters")
            assert has_sets or has_duration or has_distance, f"{key}: {item['slug']}"


def test_seed_inserts_every_entry(db_session):
    catalog.seed_catalog(db_session)

    stored = {e.slug for e in db_session.query(CoachExercise).all()}
    assert stored == {entry["slug"] for entry in catalog.CATALOG}


def test_seed_is_idempotent(db_session):
    catalog.seed_catalog(db_session)
    catalog.seed_catalog(db_session)

    assert db_session.query(CoachExercise).count() == len(catalog.CATALOG)


def test_seed_refreshes_catalog_rows_that_drifted(db_session):
    db_session.add(CoachExercise(slug="bench_press", name="Bench", category="strength", muscle_group="push"))
    db_session.commit()

    catalog.seed_catalog(db_session)

    bench = db_session.query(CoachExercise).filter_by(slug="bench_press").one()
    assert (bench.name, bench.muscle_group, bench.equipment) == ("Bench press", "chest", "barbell")
    assert db_session.query(CoachExercise).count() == len(catalog.CATALOG)


def test_seed_leaves_custom_exercises_alone(db_session):
    db_session.add(CoachExercise(name="Sled push", category="strength", is_custom=True))
    db_session.commit()

    catalog.seed_catalog(db_session)

    assert db_session.query(CoachExercise).filter_by(is_custom=True).one().name == "Sled push"


def test_create_app_seeds_the_catalog(app, db_session):
    assert db_session.query(CoachExercise).count() == len(catalog.CATALOG)

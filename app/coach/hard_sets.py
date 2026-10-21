"""Hard sets per muscle group for one week — pure counting, no estimates.

Each exercise counts toward the one muscle group the catalog gives it. A set
without a reps-in-reserve entry is shown as unrated rather than guessed
(RULE-LOAD-04).
"""

from app.coach.catalog import MUSCLE_GROUPS
from app.coach.set_log import is_hard
from app.training_rules import SETS_PER_MUSCLE_IMPROVE_MIN, SETS_PER_MUSCLE_MAINTAIN_MIN


# RULE-WEEK-02
def _range(hard_sets):
    if hard_sets >= SETS_PER_MUSCLE_IMPROVE_MIN:
        return "growth"
    if hard_sets >= SETS_PER_MUSCLE_MAINTAIN_MIN:
        return "maintenance"
    return None


def weekly_hard_sets(sets):
    """sets: [{"muscle_group", "rir", "session_id"}] for the week's logged sets."""
    groups = {}
    for logged in sets:
        name = logged["muscle_group"]
        if name in (None, "none"):
            continue
        group = groups.setdefault(name, {"hard_sets": 0, "unrated": 0, "session_ids": set()})
        hard = is_hard(logged["rir"])
        if hard is None:
            group["unrated"] += 1
        elif hard:
            group["hard_sets"] += 1
            group["session_ids"].add(logged["session_id"])

    ordered = [name for name in MUSCLE_GROUPS if name in groups]
    return {
        "groups": [
            {
                "muscle_group": name,
                "hard_sets": groups[name]["hard_sets"],
                "unrated": groups[name]["unrated"],
                # RULE-WEEK-03: any frequency is fine; shown, never judged.
                "sessions": len(groups[name]["session_ids"]),
                "range": _range(groups[name]["hard_sets"]),
            }
            for name in ordered
        ],
        "unrated": sum(g["unrated"] for g in groups.values()),
    }

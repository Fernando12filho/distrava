import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("build_roadmap", ROOT / "scripts" / "build_roadmap.py")
build_roadmap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_roadmap)

SAMPLE = """# Plan — Distrava

_Living document. Updated at the end of every piece of work. Last update: 2026-10-20._

## 3. Roadmap

### M1 — Trust the data
_Your imports are right._

| Status | Feature | Notes |
|---|---|---|
| ✅ | Import & dedup | Phase 1 |
| ⏭ | Date filter in local time | small |
| 🔬 | Effort labels | research §A |

### M2 — Records & dashboard
_Explained._

| Status | Feature | Notes |
|---|---|---|
| ⬜ | PR history | |

## 4. Rules the app uses today, and where they come from

| Rule | Used in | Source |
|---|---|---|
| Karvonen zones | zones | [R] Karvonen 1957 |
| Strava distances | records | [Y] |
| Effort labels | catalog | [A] my judgement |

## 5. Research

| Status | Topic | What it decides |
|---|---|---|
| ⏭ | A. What makes a session "hard" | effort labels |

## 7. Waiting on

| Status | Item | Who |
|---|---|---|
| ⏭ | Run the research prompt | you |
"""


@pytest.fixture()
def plan():
    return build_roadmap.parse_plan(SAMPLE)


def test_reads_the_last_update_date(plan):
    assert plan["updated"] == "2026-10-20"


def test_reads_each_milestone_with_its_summary(plan):
    assert [(m["id"], m["title"], m["summary"]) for m in plan["milestones"]] == [
        ("M1", "Trust the data", "Your imports are right."),
        ("M2", "Records & dashboard", "Explained."),
    ]


def test_maps_status_emoji_to_names(plan):
    items = plan["milestones"][0]["items"]

    assert [(i["status"], i["feature"]) for i in items] == [
        ("done", "Import & dedup"),
        ("next", "Date filter in local time"),
        ("research", "Effort labels"),
    ]


def test_counts_progress_per_milestone(plan):
    assert build_roadmap.progress(plan["milestones"][0]) == (1, 3)


def test_reads_rules_with_their_source_tag(plan):
    assert [(r["rule"], r["tag"]) for r in plan["rules"]] == [
        ("Karvonen zones", "R"),
        ("Strava distances", "Y"),
        ("Effort labels", "A"),
    ]


def test_reads_research_and_waiting_tables(plan):
    assert plan["research"][0]["topic"] == 'A. What makes a session "hard"'
    assert plan["waiting"][0]["item"] == "Run the research prompt"


def test_an_unknown_status_is_an_error_not_a_silent_skip():
    broken = SAMPLE.replace("| ⏭ | Date filter", "| ❓ | Date filter")

    with pytest.raises(ValueError, match="❓"):
        build_roadmap.parse_plan(broken)


def test_render_escapes_text_and_shows_every_feature(plan):
    html = build_roadmap.render(plan)

    assert "Import &amp; dedup" in html
    assert "Records &amp; dashboard" in html
    assert "PR history" in html
    assert "What makes a session &quot;hard&quot;" in html


def test_render_loads_nothing_from_the_network(plan):
    assert "http://" not in build_roadmap.render(plan)
    assert "https://" not in build_roadmap.render(plan)


def test_the_real_plan_parses():
    plan = build_roadmap.parse_plan((ROOT / "plan.md").read_text())

    assert [m["id"] for m in plan["milestones"]] == ["M1", "M2", "M3", "M4"]
    assert all(r["tag"] in {"R", "Y", "S", "A"} for r in plan["rules"])


def test_the_committed_roadmap_page_matches_plan_md():
    expected = build_roadmap.render(build_roadmap.parse_plan((ROOT / "plan.md").read_text()))

    actual = (ROOT / "docs" / "roadmap.html").read_text()

    assert actual == expected, "docs/roadmap.html is stale: run python scripts/build_roadmap.py"

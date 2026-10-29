"""Step 8a: search_rules. Training advice comes only from research/training-rules.md:
results are real rule ids with their own sources, nothing found says "not covered",
and the coach can't cite a rule it didn't look up (AC-18).
"""

import json
import re
from pathlib import Path

from app import create_app
from app.coach import agent, rules
from app.coach.providers import FakeProvider

from tests.test_agent_loop import _run, _tool_results
from tests.test_preview_undo import WEEK, _ask, client, fake, frozen_today, keystore, week  # noqa: F401

RESEARCH = (Path(__file__).resolve().parent.parent / "research" / "training-rules.md").read_text()
RULES = rules.parse(RESEARCH)


def _search(topic):
    return {"name": "search_rules", "input": {"topic": topic}}


def _ids(result):
    return [m["id"] for m in result["matches"]]


def test_every_rule_in_the_research_file_is_read():
    assert len(RULES["rules"]) == len(re.findall(r"^### RULE-", RESEARCH, re.MULTILINE))
    for rule in RULES["rules"]:
        assert re.fullmatch(r"RULE-[A-Z]+-\d{2}", rule["id"])
        assert rule["title"] and rule["rule"] and rule["sources"]


def test_a_topic_finds_its_rule_first():
    result = rules.search(RULES, "spacing hard runs")

    assert result["covered"] is True
    assert _ids(result)[0] == "RULE-REC-02"


def test_a_match_carries_the_rule_its_parameters_and_sources():
    match = rules.search(RULES, "weekly running distance increase")["matches"][0]

    assert match["id"] == "RULE-PROG-02"
    assert set(match) >= {"id", "title", "rule", "parameters", "evidence", "confidence", "sources", "caveats"}
    assert "20 %" in match["rule"]


def test_word_forms_still_match():
    assert "RULE-REC-01" in _ids(rules.search(RULES, "muscle group spaced recovery"))


def test_an_id_finds_exactly_that_rule():
    assert _ids(rules.search(RULES, "RULE-REC-01")) == ["RULE-REC-01"]


def test_results_are_capped():
    assert len(rules.search(RULES, "hard run session week strength")["matches"]) <= rules.MAX_MATCHES


def test_ac_18_sources_are_only_ones_listed_in_the_research_file():
    for rule in RULES["rules"]:
        for source in rule["sources"]:
            assert source in RESEARCH


def test_numbers_reach_the_coach_with_at_most_2_decimals():
    # Standing rule; a DOI like 10.1249/MSS… is an identifier, not a number, and stays whole.
    text = json.dumps([rules.search(RULES, r["id"]) for r in RULES["rules"]], ensure_ascii=False)

    assert re.findall(r"(?<![\w/.])\d+\.\d{3,}(?![\w/])", text) == []
    assert "RR 0.32" in text and "10.1249/MSS" in text


def test_ac_18_an_uncovered_question_says_so():
    result = rules.search(RULES, "creatine dosage")

    assert result["covered"] is False
    assert result["matches"] == []
    assert "not covered" in result["note"]


def test_a_number_alone_matches_nothing():
    # "10" sits in many rules' parameters; it says nothing about the topic.
    assert rules.search(RULES, "10 % rule")["covered"] is False
    assert _ids(rules.search(RULES, "10 % mileage increase")) == ["RULE-PROG-02"]


def test_a_popular_rule_the_research_rejects_is_named():
    result = rules.search(RULES, "stretch before running")

    assert any(row["rule"].startswith('"Stretch before running') for row in result["not_supported"])


def test_an_empty_topic_lists_every_rule_by_title():
    result = rules.search(RULES, "  ")

    assert [r["id"] for r in result["index"]] == [r["id"] for r in RULES["rules"]]
    assert result["matches"] == []


def test_no_research_file_means_nothing_is_covered():
    result = rules.search(rules.parse(""), "spacing hard runs")

    assert result["covered"] is False


# --- In the agent loop ---


def _readers():
    def load_week(_week_start):
        raise AssertionError("not read here")

    return {"load_week": load_week, "rules": RULES}


def test_search_rules_is_offered_as_a_strict_read_tool():
    fake = FakeProvider([{"text": "OK."}])

    _run(fake, readers=_readers())

    tool = next(t for t in fake.calls[0]["tools"] if t["name"] == "search_rules")
    assert tool["strict"] is True


def test_ac_15_a_rule_search_answers_without_writing():
    fake = FakeProvider([{"tool_calls": [_search("spacing hard runs")]}, {"text": "Keep hard runs apart (RULE-REC-02)."}])

    result, _ = _run(fake, request="How should I space hard runs?", readers=_readers())

    found = json.loads(_tool_results(fake.calls[1])[0]["content"])
    assert found["matches"][0]["id"] == "RULE-REC-02"
    assert result["status"] == "answer" and result["calls"] == []


def test_numbers_in_a_found_rule_may_be_used():
    fake = FakeProvider([{"tool_calls": [_search("spacing hard runs")]}, {"text": "At most 2 hard runs a week (RULE-REC-02)."}])

    result, _ = _run(fake, request="How many hard runs?", readers=_readers())

    assert result["status"] == "answer"


def test_ac_18_citing_a_rule_it_did_not_look_up_is_sent_back():
    fake = FakeProvider([{"text": "Rest 48 hours, per RULE-REC-09."}, {"text": "I'd need to look that up first."}])

    result, _ = _run(fake, request="How long should I rest? 48 hours?", readers=_readers())

    sent_back = fake.calls[1]["messages"][-1]["content"][0]["text"]
    assert "RULE-REC-09" in sent_back and "search_rules" in sent_back
    assert result["reply"] == "I'd need to look that up first."


def test_the_coach_page_searches_the_real_research_file(client, fake, week):
    fake.replies.extend([{"tool_calls": [_search("spacing hard runs")]}, {"text": "Keep hard runs apart (RULE-REC-02)."}])

    _ask(client, "How should I space hard runs?")

    found = json.loads(_tool_results(fake.calls[1])[0]["content"])
    assert found["matches"][0]["id"] == "RULE-REC-02"


def test_a_missing_research_file_answers_not_covered(engine, keystore, fake, tmp_path):
    app = create_app(
        {"TESTING": True, "ENGINE": engine, "KEYSTORE": keystore, "PROVIDER_FACTORY": lambda key: fake, "RESEARCH_RULES": tmp_path / "none.md"}
    )
    fake.replies.extend([{"tool_calls": [_search("spacing hard runs")]}, {"text": "The app's research isn't available."}])

    app.test_client().post(f"/coach/weeks/{WEEK}/ask", data={"message": "How should I space hard runs?"})

    assert json.loads(_tool_results(fake.calls[1])[0]["content"])["covered"] is False


def test_the_step_names_the_rules_found_in_code_written_words():
    found = {"covered": True, "matches": [{"id": "RULE-REC-02"}, {"id": "RULE-REC-04"}], "not_supported": []}

    assert agent.step_label(_search("anything 12"), [], found) == "Looked up the research: RULE-REC-02, RULE-REC-04"
    assert agent.step_label(_search("creatine"), [], {"covered": False, "matches": [], "not_supported": []}) == (
        "Looked up the research: not covered"
    )

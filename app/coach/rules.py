"""search_rules (spec "Agent loop", step 8a): the coach's only source of training
advice is research/training-rules.md. Pure: the file's text comes in, matching
rules go out with their own sources, and a topic the research doesn't cover
says so instead of borrowing a loosely related rule (AC-18).
"""

import math
import re

# Enough to compare two or three rules without sending the whole file each step.
MAX_MATCHES = 3
# A rule must match at least this share of the topic's weight (rarer words weigh
# more), so "creatine for runners" isn't answered by every rule that says "run".
MIN_COVERAGE = 0.5

NOT_COVERED = (
    "not covered: the research file has no rule on this. Say so plainly; "
    "don't give advice on it from general knowledge."
)
NO_RESEARCH = "not covered: the research file isn't available, so there is no rule to give."

_RULE_HEADING = re.compile(r"^### (RULE-[A-Z]+-\d+): (.+)$")
_SECTION_HEADING = re.compile(r"^### [A-Z]\. (.+)$")
_FIELD = re.compile(r"^- ([A-Za-z ]+): ?(.*)$")
RULE_ID = re.compile(r"\bRULE-[A-Z]+-\d+\b", re.IGNORECASE)
_URL = re.compile(r"\s*https?://\S+")
# A decimal number, but not part of a DOI ("10.1249/MSS…") or another identifier.
_LONG_DECIMAL = re.compile(r"(?<![\w/.])\d+\.\d{3,}(?![\w/])")
_FIELDS = {
    "Rule": "rule",
    "Parameters": "parameters",
    "Applies to": "applies_to",
    "Evidence strength": "evidence",
    "Population studied": "population",
    "Sources": "sources",
    "Caveats": "caveats",
    "Confidence for a recreational adult": "confidence",
}
# Field weights in ranking: a word in the title says more than one in a caveat.
_WEIGHTS = {"title": 3, "rule": 2, "section": 1, "applies_to": 1, "parameters": 1, "caveats": 1}
_STOPWORDS = set(
    "a an and are as at be before by can do does for from how i in is it my of on or per should so the to "
    "what when which with without you your rule rules".split()
)


def _stem(word):
    for suffix in ("ing", "ed", "es", "s", "ly", "y", "e"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            word = word[: -len(suffix)]
            break
    # "running" → "runn" → "run", so it meets "run" and "runs".
    if len(word) > 3 and word[-1] == word[-2] and word[-1] not in "aeiou":
        word = word[:-1]
    return word


def _stems(text):
    # Letters only: a number like "10" sits in many rules' parameters and says nothing about the topic.
    return {_stem(w) for w in re.findall(r"[a-z]+", text.lower()) if w not in _STOPWORDS}


def _two_decimals(text):
    # Standing rule: at most 2 decimals in what the coach sees ("RR 0.315" → "RR 0.32").
    return _LONG_DECIMAL.sub(lambda m: f"{round(float(m.group(0)), 2):g}", text)


def _not_supported(lines):
    rows, inside = [], False
    for line in lines:
        if line.startswith("## "):
            inside = line.startswith("## 3. Not supported")
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if inside and line.startswith("|") and len(cells) == 3 and cells[0] != "Popular rule" and not set(cells[0]) <= set("-: "):
            rows.append({"rule": cells[0], "evidence": cells[1], "sources": cells[2]})
    return rows


def parse(text):
    """{"rules": [...], "not_supported": [...]} from the research file's text."""
    lines = _two_decimals(text).splitlines()
    found, section, current, field = [], "", None, None
    for line in lines:
        if heading := _RULE_HEADING.match(line):
            current = {"id": heading.group(1), "title": heading.group(2).strip(), "section": section, "sources": []}
            current.update({key: "" for key in _FIELDS.values() if key != "sources"})
            found.append(current)
            field = None
        elif heading := _SECTION_HEADING.match(line):
            section, current = heading.group(1).strip(), None
        elif line.startswith(("## ", "---")):
            current = None
        elif current is not None and (match := _FIELD.match(line)) and match.group(1) in _FIELDS:
            field = _FIELDS[match.group(1)]
            if field != "sources":
                current[field] = match.group(2).strip()
            elif match.group(2).strip():
                # "none found …": the coach must see that a rule has no direct source.
                current["sources"].append(match.group(2).strip())
        elif current is not None and field == "sources" and line.strip().startswith("- "):
            # Without its URL: the coach cites authors and year, and URLs are long.
            current["sources"].append(_URL.sub("", line.strip()[2:]).strip())
    return {"rules": found, "not_supported": _not_supported(lines)}


def _idf(stem, documents):
    seen = sum(1 for words in documents if stem in words)
    return math.log((len(documents) + 1) / (seen + 1)) + 1


def _ranked(query, entries, fields):
    """Entries matching enough of the query, best first: (entry, score) pairs."""
    words = [{f: _stems(entry.get(f, "")) for f in fields} for entry in entries]
    documents = [set().union(*w.values()) for w in words]
    weight = {stem: _idf(stem, documents) for stem in query}
    total = sum(weight.values())
    ranked = []
    for position, (entry, fields_words) in enumerate(zip(entries, words)):
        matched = [s for s in query if s in documents[position]]
        if sum(weight[s] for s in matched) < MIN_COVERAGE * total:
            continue
        score = sum(weight[s] * max(fields[f] for f in fields if s in fields_words[f]) for s in matched)
        ranked.append((-score, position, entry))
    return [entry for _score, _position, entry in sorted(ranked, key=lambda r: r[:2])]


def _match(rule):
    keys = ("id", "title", "rule", "parameters", "applies_to", "evidence", "confidence", "sources", "caveats")
    return {key: rule[key] for key in keys}


def search(research, topic):
    """The rules on a topic, a rule id, or (empty topic) every rule's id and title."""
    rules = research["rules"]
    if not rules:
        return {"covered": False, "matches": [], "not_supported": [], "note": NO_RESEARCH}
    if not topic.strip():
        return {"covered": True, "matches": [], "not_supported": [], "index": [{"id": r["id"], "title": r["title"]} for r in rules]}

    asked_ids = {i.upper() for i in RULE_ID.findall(topic)}
    if asked_ids:
        matches = [r for r in rules if r["id"] in asked_ids]
        rejected = []
    elif not (query := _stems(topic)):
        matches, rejected = [], []
    else:
        matches = _ranked(query, rules, _WEIGHTS)
        rejected = _ranked(query, research["not_supported"], {"rule": 2, "evidence": 1})[:MAX_MATCHES]
    result = {"covered": bool(matches), "matches": [_match(r) for r in matches[:MAX_MATCHES]], "not_supported": rejected}
    if not matches:
        result["note"] = NOT_COVERED
    return result

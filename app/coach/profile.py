"""The training profile: how you train today, in your own words and numbers.

Set by you in Settings, or changed by the coach once you accept its proposal.
Nothing here has a default — an empty field means "not said yet", and rules
that depend on it (RULE-WEEK-01/02, RULE-LOAD-03) must treat it as unknown.
"""

# (low, high) for whole numbers; max length for text.
NUMBERS = {
    "runs_per_week": (0, 14),
    "gym_days_per_week": (0, 7),
    "years_running": (0, 80),
    "years_lifting": (0, 80),
}
TEXTS = {
    "split": 80,
    "goal": 300,
}
FIELDS = ("runs_per_week", "gym_days_per_week", "split", "goal", "years_running", "years_lifting")


def _label(field):
    return field.replace("_", " ")


def _number(field, raw):
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{_label(field)} must be a whole number") from None
    low, high = NUMBERS[field]
    if not low <= value <= high:
        raise ValueError(f"{_label(field)} must be between {low} and {high}")
    return value


def _text(field, raw):
    if len(raw) > TEXTS[field]:
        raise ValueError(f"{_label(field)} must be at most {TEXTS[field]} characters")
    return raw


def parse_profile(form):
    parsed = {}
    for field in FIELDS:
        raw = (form.get(field) or "").strip()
        if not raw:
            parsed[field] = None
        elif field in NUMBERS:
            parsed[field] = _number(field, raw)
        else:
            parsed[field] = _text(field, raw)
    return parsed

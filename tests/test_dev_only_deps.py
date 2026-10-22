import re
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent / "app"

# Dev tooling (browser screenshots) must never become something the shipped
# app needs; requirements-dev.txt is the only place it belongs.
DEV_ONLY = ("playwright",)


def test_app_code_never_imports_dev_only_packages():
    pattern = re.compile(rf"^\s*(from|import)\s+({'|'.join(DEV_ONLY)})\b", re.M)
    offenders = [
        str(path.relative_to(APP_DIR.parent))
        for path in APP_DIR.rglob("*.py")
        if pattern.search(path.read_text(encoding="utf-8"))
    ]

    assert offenders == []


def test_runtime_requirements_exclude_dev_tools():
    root = APP_DIR.parent
    runtime = (root / "requirements.txt").read_text().lower()
    dev = (root / "requirements-dev.txt").read_text().lower()

    assert "playwright" not in runtime
    assert "pytest" not in runtime
    assert "-r requirements.txt" in dev
    assert "playwright" in dev

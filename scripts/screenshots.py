"""Screenshot every page of the app, for checking UI changes by eye.

Runs the app on a temporary *copy* of the real database: the pages show real
numbers, but schema upgrades and any writes land on the copy, never on
data/fitness.db. The images therefore contain health data — screenshots/ is
gitignored. Dev-only: needs requirements-dev.txt and `playwright install chromium`.

    python scripts/screenshots.py                       # all pages -> screenshots/
    python scripts/screenshots.py --db path/fitness.db  # e.g. from a git worktree
    python scripts/screenshots.py --empty               # blank database instead
"""

import argparse
import logging
import socket
import sqlite3
import sys
import tempfile
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402

PAGES = {
    "dashboard": "/dashboard",
    "activities": "/activities",
    "coach": "/coach",
    "import": "/import",
    "settings": "/settings",
}


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _copy_database(source, dest):
    # The backup API gives a consistent copy even while the app has the file
    # open; mode=ro guarantees this script can't modify the original.
    src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    dst = sqlite3.connect(dest)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(ROOT / "screenshots"))
    parser.add_argument("--db", default=str(ROOT / "data" / "fitness.db"))
    parser.add_argument("--empty", action="store_true", help="use a blank database")
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=900)
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "screens.db"
        if not args.empty:
            if not Path(args.db).is_file():
                sys.exit(f"no database at {args.db} — pass --db PATH or --empty")
            _copy_database(args.db, db)
        app = create_app({"DATABASE_URL": f"sqlite:///{db}", "TESTING": True})
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
        port = _free_port()
        server = make_server("127.0.0.1", port, app)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{port}"

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page(viewport={"width": args.width, "height": args.height})
                for name, path in PAGES.items():
                    page.goto(base + path, wait_until="networkidle")
                    page.screenshot(path=out / f"{name}.png")
                    print(f"{name}: {page.url}")

                # The sidebar's collapsed state only exists after a click.
                page.goto(base + "/dashboard", wait_until="networkidle")
                page.click("[data-sidebar-toggle]")
                page.wait_for_timeout(150)
                page.screenshot(path=out / "dashboard-sidebar-collapsed.png")
                page.reload(wait_until="networkidle")
                collapsed = page.evaluate(
                    "document.documentElement.classList.contains('sidebar-collapsed')"
                )
                print(f"sidebar collapsed after reload: {collapsed}")
                browser.close()
        finally:
            server.shutdown()

    print(f"saved to {out}")


if __name__ == "__main__":
    main()

"""Screenshot every page of the app, for checking UI changes by eye.

Runs the app on a throwaway database so real health data never ends up in an
image. Dev-only: needs requirements-dev.txt and `playwright install chromium`.

    python scripts/screenshots.py                 # all pages -> screenshots/
    python scripts/screenshots.py --out shots/b4  # pick the folder
"""

import argparse
import socket
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(ROOT / "screenshots"))
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=900)
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        app = create_app({"DATABASE_URL": f"sqlite:///{tmp}/screens.db", "TESTING": True})
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

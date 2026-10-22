import threading

import pytest

sync_api = pytest.importorskip("playwright.sync_api")
from werkzeug.serving import make_server  # noqa: E402

FULL, RAIL = 248, 72

# Samples the sidebar's width on every animation frame for a while, so the test
# sees the motion itself rather than just where it ends.
SAMPLE_WIDTHS = """(ms) => new Promise((done) => {
  const el = document.getElementById("sidebar");
  const widths = [];
  const start = performance.now();
  const tick = () => {
    widths.push(el.getBoundingClientRect().width);
    if (performance.now() - start < ms) requestAnimationFrame(tick);
    else done(widths);
  };
  requestAnimationFrame(tick);
})"""


@pytest.fixture()
def page(app):
    server = make_server("127.0.0.1", 0, app)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sync_api.sync_playwright() as p:
            browser = p.chromium.launch()
            tab = browser.new_page(viewport={"width": 1280, "height": 800})
            tab.goto(f"http://127.0.0.1:{server.port}/dashboard")
            yield tab
            browser.close()
    finally:
        server.shutdown()


def _toggle_and_sample(page):
    page.click("[data-sidebar-toggle]")
    return page.evaluate(SAMPLE_WIDTHS, 900)


def test_collapsing_glides_through_intermediate_widths(page):
    widths = _toggle_and_sample(page)

    assert any(RAIL + 5 < w < FULL - 5 for w in widths)
    assert widths[-1] == RAIL


def test_expanding_glides_back_and_contents_end_fully_visible(page):
    _toggle_and_sample(page)
    widths = _toggle_and_sample(page)

    assert any(RAIL + 5 < w < FULL - 5 for w in widths)
    assert widths[-1] == FULL
    opacity = page.evaluate("getComputedStyle(document.querySelector('.sidebar-nav')).opacity")
    assert opacity == "1"


def test_reduced_motion_switches_instantly(page):
    page.emulate_media(reduced_motion="reduce")
    page.reload()

    widths = _toggle_and_sample(page)

    assert all(w in (RAIL, FULL) for w in widths)
    assert widths[-1] == RAIL

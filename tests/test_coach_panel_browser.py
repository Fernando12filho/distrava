"""The Coach page in a real browser: the chat answers in place, the panel
closes like the left bar, and the week stays readable at common widths.
Skipped where Playwright isn't installed (it's dev-only)."""

import threading
from datetime import date

import pytest

sync_api = pytest.importorskip("playwright.sync_api")
from werkzeug.serving import make_server  # noqa: E402

from app import create_app  # noqa: E402
from app.coach.keystore import MemoryKeystore  # noqa: E402
from app.coach.providers import FakeProvider  # noqa: E402
from app.coach.week import week_start_for  # noqa: E402

PANEL_RAIL = 56


@pytest.fixture()
def fake():
    return FakeProvider([])


@pytest.fixture()
def server(engine, fake):
    store = MemoryKeystore()
    store.set("sk-ant-api03-test-key-not-real")
    app = create_app({"TESTING": True, "ENGINE": engine, "KEYSTORE": store, "PROVIDER_FACTORY": lambda key: fake})
    client = app.test_client()
    monday = week_start_for(date.today()).isoformat()
    for template, day in (("chest_triceps", 0), ("running_day", 2), ("legs_glutes", 3), ("chest_triceps", 3)):
        client.post("/coach/sessions", data={"template": template, "day_index": str(day), "week_start": monday})

    srv = make_server("127.0.0.1", 0, app)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.port}"
    srv.shutdown()


@pytest.fixture()
def browser():
    with sync_api.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def _open(browser, server, width=1440, height=900):
    page = browser.new_page(viewport={"width": width, "height": height})
    page.goto(f"{server}/coach/", wait_until="networkidle")
    return page


def _width(page, selector):
    return page.evaluate(f"document.querySelector('{selector}').getBoundingClientRect().width")


def test_sending_a_message_answers_in_place_without_reloading(browser, server, fake):
    fake.replies.append({"text": "Saturday is free, so the run fits there."})
    page = _open(browser, server)
    page.evaluate("window.__notReloaded = true")

    page.fill(".composer textarea", "Can I move my run?")
    page.click(".composer button[type=submit]")
    page.wait_for_selector("text=Saturday is free, so the run fits there.")

    assert page.evaluate("window.__notReloaded === true")
    assert "Can I move my run?" in page.inner_text(".coach-thread")
    assert page.input_value(".composer textarea") == ""


def test_the_message_shows_at_once_with_a_thinking_state(browser, server, fake):
    fake.replies.append({"text": "Done thinking."})
    page = _open(browser, server)
    # Hold the request so the waiting state can be seen.
    page.route("**/ask", lambda route: (page.wait_for_timeout(400), route.continue_()))

    page.fill(".composer textarea", "Is this week too much?")
    page.click(".composer button[type=submit]")

    page.wait_for_selector(".msg.user >> text=Is this week too much?")
    assert "Coach is thinking" in page.inner_text(".coach-panel")
    page.wait_for_selector("text=Done thinking.")


def test_the_panel_closes_to_a_rail_and_the_board_takes_the_space(browser, server):
    page = _open(browser, server)
    board_before = _width(page, ".coach-board")

    page.click("[data-coach-panel-toggle]")
    page.wait_for_timeout(600)

    assert _width(page, ".coach-panel") == PANEL_RAIL
    assert _width(page, ".coach-board") > board_before + 250
    page.reload(wait_until="networkidle")
    assert _width(page, ".coach-panel") == PANEL_RAIL


@pytest.mark.parametrize("width", [1280, 1440])
def test_day_columns_never_spill_with_both_panels_open(browser, server, width):
    page = _open(browser, server, width=width)

    spills = page.evaluate(
        """() => [...document.querySelectorAll('.day-col-head, .session-card')]
             .filter(el => el.scrollWidth > el.clientWidth + 1)
             .map(el => el.textContent.trim().replace(/\\s+/g, ' '))"""
    )

    assert spills == []


def test_on_a_narrow_window_the_panel_opens_over_the_board_not_below_it(browser, server):
    page = _open(browser, server, width=1000, height=800)

    top = page.evaluate("document.querySelector('.coach-panel').getBoundingClientRect().top")

    assert top < 100


def test_on_load_the_chat_opens_at_the_last_message(browser, server, fake):
    page = _open(browser, server, height=700)
    for n in range(6):
        fake.replies.append({"text": f"Answer number {n}, " + "a fairly long reply that takes some room. " * 4})
        page.fill(".composer textarea", f"Question {n}")
        page.click(".composer button[type=submit]")
        page.wait_for_selector(f"text=Answer number {n}")

    page.reload(wait_until="networkidle")

    gap = page.evaluate("(() => { const b = document.querySelector('.coach-panel-body'); return b.scrollHeight - b.clientHeight - b.scrollTop; })()")
    overflow = page.evaluate("(() => { const b = document.querySelector('.coach-panel-body'); return b.scrollHeight - b.clientHeight; })()")
    assert overflow > 0  # the thread is taller than the panel, so where it opens matters
    assert gap <= 1


# --- #43: the chat panel after VS Code's chat (DS-07) -------------------------------


def test_the_message_box_has_no_resize_handle_and_grows_as_you_type(browser, server):
    page = _open(browser, server)
    box = ".composer textarea"
    assert page.evaluate(f"getComputedStyle(document.querySelector('{box}')).resize") == "none"
    empty = page.evaluate(f"document.querySelector('{box}').getBoundingClientRect().height")

    page.fill(box, "line\n" * 4 + "line")
    five = page.evaluate(f"document.querySelector('{box}').getBoundingClientRect().height")
    page.fill(box, "line\n" * 30 + "line")
    many = page.evaluate(f"document.querySelector('{box}').getBoundingClientRect().height")

    assert five > empty
    assert many < 220  # about 8 lines, then it scrolls inside
    assert page.evaluate(f"(() => {{ const t = document.querySelector('{box}'); return t.scrollHeight > t.clientHeight; }})()")


def test_enter_sends_and_shift_enter_adds_a_line(browser, server, fake):
    fake.replies.append({"text": "Sent with Enter."})
    page = _open(browser, server)
    box = ".composer textarea"

    page.click(box)
    page.keyboard.type("first line")
    page.keyboard.press("Shift+Enter")
    page.keyboard.type("second line")
    assert page.input_value(box) == "first line\nsecond line"

    page.keyboard.press("Enter")
    page.wait_for_selector("text=Sent with Enter.")
    assert "first line" in page.inner_text(".coach-thread")


def test_the_send_button_sits_inside_the_message_box(browser, server):
    page = _open(browser, server)

    composer = page.locator(".composer").bounding_box()
    send = page.locator(".composer button[type=submit]").bounding_box()

    # The bordered box is the composer itself, not just the text area beside the button.
    assert page.evaluate("getComputedStyle(document.querySelector('.composer')).borderTopWidth") != "0px"
    assert page.evaluate("getComputedStyle(document.querySelector('.composer textarea')).borderTopWidth") == "0px"
    assert composer["x"] <= send["x"] and send["x"] + send["width"] <= composer["x"] + composer["width"]
    assert composer["y"] <= send["y"] and send["y"] + send["height"] <= composer["y"] + composer["height"]


def test_coach_replies_use_the_panels_full_width(browser, server, fake):
    fake.replies.append({"text": "A reply long enough to fill the line. " * 6})
    page = _open(browser, server)
    page.fill(".composer textarea", "Hi")
    page.click(".composer button[type=submit]")
    page.wait_for_selector("text=A reply long enough")

    assert _width(page, ".msg.coach") >= _width(page, ".coach-thread") - 1

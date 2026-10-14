"""Browser: what the viewer page's covers say and do when a browser crashes, stops, or will not start, in a real
Chromium.

The page is served through request routing; its control and stream sockets are answered by stubs the test drives,
so no daemon and no Chromium-under-test runs.
"""

import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, Final

import pytest
from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
    Route,
    WebSocketRoute,
    expect,
)

pytestmark = [pytest.mark.browser, pytest.mark.timeout(60)]

_VIEWER_PATH: Final[Path] = Path(__file__).parent / "src" / "browser" / "assets" / "index.html"
_VIEWER_URL: Final[str] = "http://localhost/?session=browser-1"
_CAST_URL: Final[str] = "ws://localhost/browsers/browser-1/cast"
_STREAM_URL: Final[str] = "ws://localhost/browsers/browser-1/stream?**"
_START_URL: Final[str] = "http://localhost/browsers/browser-1/start"
_POLL_MS: Final[int] = 50
_POLL_ATTEMPTS: Final[int] = 100


def _control(lifecycle: str) -> str:
    return json.dumps({"type": "control", "lifecycle": lifecycle, "owner": "human", "waiting": []})


class _Sockets:
    """The page's control and stream sockets as the stubs accepted them, in order."""

    def __init__(self) -> None:
        self.casts: list[WebSocketRoute] = []
        self.streams: list[WebSocketRoute] = []


@pytest.fixture
def desktop_context(module_browser: Browser) -> Iterator[BrowserContext]:
    context = module_browser.new_context(viewport={"width": 1024, "height": 768})
    yield context
    context.close()


def _wait_until(page: Page, is_done: Callable[[], bool]) -> None:
    for _ in range(_POLL_ATTEMPTS):
        if is_done():
            return
        page.wait_for_timeout(_POLL_MS)
    pytest.fail("the viewer did not do what was expected")


def _open_viewer(context: BrowserContext, first_lifecycle: str) -> tuple[Page, _Sockets]:
    """Open the viewer; its first control socket is told the browser is ``first_lifecycle``, later ones nothing."""
    sockets = _Sockets()

    def answer(route: Route) -> None:
        if route.request.url == _VIEWER_URL:
            route.fulfill(status=200, content_type="text/html", body=_VIEWER_PATH.read_text())
        else:
            route.fulfill(status=404, body="")

    def cast(socket: WebSocketRoute) -> None:
        sockets.casts.append(socket)
        if len(sockets.casts) == 1:
            socket.send(_control(first_lifecycle))

    context.route("**/*", answer)
    page = context.new_page()
    page.route_web_socket(_CAST_URL, cast)
    page.route_web_socket(_STREAM_URL, lambda socket: sockets.streams.append(socket))
    page.goto(_VIEWER_URL)
    _wait_until(page, lambda: len(sockets.casts) == 1 and len(sockets.streams) == 1)
    return page, sockets


def _answer_start(page: Page, status: int, body: dict[str, Any]) -> list[str]:
    started: list[str] = []

    def answer(route: Route) -> None:
        started.append(route.request.method)
        route.fulfill(status=status, content_type="application/json", body=json.dumps(body))

    page.route(_START_URL, answer)
    return started


@pytest.mark.parametrize(
    ("reason", "message", "cause"),
    [
        pytest.param(
            "killed",
            "This browser stopped. Its tabs and sign-ins are kept.",
            "It was likely stopped because the machine this workspace runs on was low on memory.",
            id="killed",
        ),
        pytest.param("exited", "This browser stopped. Its tabs and sign-ins are kept.", None, id="exited"),
        pytest.param(
            "unresponsive",
            "This browser stopped responding. Start it again to pick up where it left off.",
            None,
            id="unresponsive",
        ),
    ],
)
def test_a_crash_cover_says_how_the_browser_ended_and_offers_start(
    desktop_context: BrowserContext, reason: str, message: str, cause: str | None
) -> None:
    page, sockets = _open_viewer(desktop_context, "running")

    sockets.casts[0].send(json.dumps({"type": "crashed", "browser_id": "browser-1", "reason": reason}))

    cover = page.locator("#crashoverlay")
    expect(cover.locator(".msg")).to_have_text(message)
    if cause is None:
        expect(cover.locator(".sub")).to_be_hidden()
    else:
        expect(cover.locator(".sub")).to_have_text(cause)
    expect(cover.get_by_role("button", name="Start browser")).to_be_enabled()


def test_a_refused_start_from_the_crash_cover_is_told_there_and_a_cleared_crash_reopens_the_picture(
    desktop_context: BrowserContext,
) -> None:
    page, sockets = _open_viewer(desktop_context, "running")
    sockets.casts[0].send(json.dumps({"type": "crashed", "browser_id": "browser-1", "reason": "killed"}))
    cover = page.locator("#crashoverlay")
    expect(cover).to_be_visible()
    # The picture's socket closes while the browser is down, and is not reopened then.
    sockets.streams[0].close()
    started = _answer_start(
        page,
        409,
        {
            "error": "1/1 browsers open -- close one first.",
            "user_facing_message": "Another browser is already running, and only one can run at a time.",
        },
    )

    cover.get_by_role("button", name="Start browser").click()

    expect(cover.locator(".sub")).to_have_text("Another browser is already running, and only one can run at a time.")
    cover.get_by_text("See details").click()
    expect(cover.locator(".refusaldetails pre")).to_have_text("HTTP 409\n1/1 browsers open -- close one first.")
    expect(cover.get_by_role("button", name="Start browser")).to_be_enabled()
    assert started == ["POST"]
    assert len(sockets.streams) == 1

    # A start that went through: the daemon launches the browser again, and the pane asks for its picture again.
    sockets.casts[0].send(_control("init"))
    expect(cover).to_be_hidden()
    _wait_until(page, lambda: len(sockets.streams) == 2)


def test_a_start_nothing_answers_says_the_browser_did_not_respond(desktop_context: BrowserContext) -> None:
    page, _sockets = _open_viewer(desktop_context, "stopped")
    page.route(_START_URL, lambda route: route.abort())
    cover = page.locator("#stoppedoverlay")

    cover.get_by_role("button", name="Start browser").click()

    expect(cover.locator(".sub")).to_have_text("The browser didn't respond. Try again in a moment.")


def test_a_start_refused_with_no_sentence_of_the_daemons_asks_for_a_bug_report(desktop_context: BrowserContext) -> None:
    page, _sockets = _open_viewer(desktop_context, "stopped")
    _answer_start(page, 404, {"error": "No browser browser-1"})
    cover = page.locator("#stoppedoverlay")

    cover.get_by_role("button", name="Start browser").click()

    expect(cover.locator(".sub")).to_have_text("Couldn't start this browser. Try again. If this persists, report a bug.")
    expect(cover.locator(".refusaldetails pre")).to_have_text("HTTP 404\nNo browser browser-1")


def test_the_programs_own_stop_shows_the_browser_stopped_and_waits_for_it_to_come_back(
    desktop_context: BrowserContext,
) -> None:
    page, sockets = _open_viewer(desktop_context, "running")
    cover = page.locator("#stoppedoverlay")

    sockets.casts[0].send(json.dumps({"type": "stopping", "browser_id": "browser-1"}))

    expect(cover.locator(".msg")).to_have_text("This browser is stopped.")
    expect(cover.locator(".sub")).to_have_text("Its tabs and sign-ins are kept.")
    expect(cover.get_by_role("button", name="Start browser")).to_be_hidden()
    expect(page.locator("#terminatedoverlay")).to_be_hidden()

    # The program turns the pane's reconnect away while it is down; the pane keeps waiting on the same cover.
    sockets.casts[0].close(code=1013)
    _wait_until(page, lambda: len(sockets.casts) == 2)
    expect(cover).to_be_visible()

    # Back up, the program says how the browser came back.
    sockets.casts[1].send(_control("init"))
    expect(cover).to_be_hidden()
    expect(page.locator("#initoverlay")).to_be_visible()

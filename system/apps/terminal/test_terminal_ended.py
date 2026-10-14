"""Browser: what a terminal window says when its terminal ended for a reason, or its page could not be served, in a
real Chromium.

The wrapper page frames the real patched ttyd client with the script dwt adds to it; with no ttyd behind it, the test
writes what a dispatch script would print straight into the client's terminal. The wrapper is itself framed by a host
page, as the shell frames it, and the shell's contract module is a stub that records what the page asks of the shell.
"""

import base64
import gzip
import json
from collections.abc import Iterator
from typing import Final

import pytest
from playwright.sync_api import Browser, BrowserContext, Frame, Page, Route, expect
from terminal_app.dispatch import (
    ENDED_MISSING_FOLDER,
    ENDED_NOT_STARTED,
    load_ttyd_web_client,
)
from terminal_app.errors import TerminalStoreError
from terminal_app.pages import (
    PageConfig,
    SessionPage,
    page_failure,
    render_failure_page,
    render_page,
)
from terminal_app.primitives import TerminalTitle, TmuxSessionName
from terminal_app.pty_page import TERMINAL_ENDED_OSC, add_pty_page_script

pytestmark = [pytest.mark.browser, pytest.mark.timeout(60)]

_WRAPPER_HOST: Final[str] = "terminal.test"
_PTY_LABEL: Final[str] = "pty"
_HOST_URL: Final[str] = f"http://{_WRAPPER_HOST}/host"
_WRAPPER_URL: Final[str] = f"http://{_WRAPPER_HOST}/?session=terminal-1"

# The shell's contract module, as a stub: the wrapper connects through it and the test reads what it asked for.
_CONTRACT_STUB: Final[str] = """
export function connectToShell() {
  window.parent.shellCalls = window.parent.shellCalls || [];
  const record = (call) => window.parent.shellCalls.push(call);
  return {
    isFramed: true,
    hasShell: () => true,
    focused() {},
    location(path, title) { record({ type: "location", path, title }); },
    startWithText(text) { record({ type: "startWithText", text }); },
  };
}
"""


def _wrapper_html(session: str) -> str:
    name = TmuxSessionName(session)
    page = SessionPage(
        name=name,
        title=TerminalTitle(f"Terminal {session.removeprefix('terminal-')}"),
        pty_path=f"/?arg=_&arg=session&arg={session}",
        pty_label=_PTY_LABEL,
    )
    return render_page(PageConfig(session=name, page=page))


@pytest.fixture
def desktop_context(module_browser: Browser) -> Iterator[BrowserContext]:
    context = module_browser.new_context(viewport={"width": 1024, "height": 768})
    yield context
    context.close()


def _serve(context: BrowserContext, wrapper_html: str) -> list[str]:
    """Serve the host page framing ``wrapper_html``, the real ttyd client, the contract stub, and the wrapper's ``new``
    and session routes; answers the methods ``new`` was asked with."""
    client = add_pty_page_script(gzip.decompress(load_ttyd_web_client(None) or b""))
    launched: list[str] = []

    def answer(route: Route) -> None:
        url = route.request.url
        if url == _HOST_URL:
            route.fulfill(content_type="text/html", body=f'<iframe src="{_WRAPPER_URL}" style="width:900px;height:600px">')
        elif url == _WRAPPER_URL:
            route.fulfill(content_type="text/html", body=wrapper_html)
        elif url.startswith(f"http://{_PTY_LABEL}.{_WRAPPER_HOST}/?arg="):
            route.fulfill(content_type="text/html", body=client)
        elif url == f"http://{_WRAPPER_HOST}/_static/app_contract.js":
            route.fulfill(content_type="text/javascript", body=_CONTRACT_STUB)
        elif url == f"http://{_WRAPPER_HOST}/new":
            launched.append(route.request.method)
            route.fulfill(content_type="application/json", body=json.dumps({"path": "/?session=terminal-2"}))
        elif url == f"http://{_WRAPPER_HOST}/api/sessions/terminal-2":
            body = {
                "name": "terminal-2",
                "title": "Terminal 2",
                "pty_path": "/?arg=_&arg=session&arg=terminal-2",
                "pty_label": _PTY_LABEL,
            }
            route.fulfill(content_type="application/json", body=json.dumps(body))
        else:
            route.fulfill(status=404, body="")

    context.route("**/*", answer)
    return launched


def _open(context: BrowserContext) -> tuple[Page, Frame, Frame]:
    page = context.new_page()
    page.goto(_HOST_URL)
    wrapper = page.frame(url=_WRAPPER_URL)
    assert wrapper is not None
    pty = page.frame(url=f"http://{_PTY_LABEL}.{_WRAPPER_HOST}/?arg=_&arg=session&arg=terminal-1")
    assert pty is not None
    pty.wait_for_function("window.term !== undefined && window.term.element !== undefined", timeout=5000)
    return page, wrapper, pty


def _print_end(pty: Frame, kind: str, detail: str) -> None:
    encoded = base64.b64encode(detail.encode()).decode()
    pty.evaluate("(text) => new Promise((resolve) => term.write(text, resolve))", f"\x1b]{TERMINAL_ENDED_OSC};{kind};{encoded}\x07")


def test_a_terminal_tmux_would_not_start_says_so_and_offers_try_again_and_an_agent(
    desktop_context: BrowserContext,
) -> None:
    _serve(desktop_context, _wrapper_html("terminal-1"))
    page, wrapper, pty = _open(desktop_context)

    _print_end(pty, ENDED_NOT_STARTED, "no server running on /tmp/tmux-1000/default")

    ended = wrapper.locator("#ended")
    expect(ended.locator("#ended-message")).to_have_text(
        "This terminal couldn't start. Try again. If this persists, report a bug."
    )
    expect(wrapper.locator("#pty")).to_be_hidden()
    ended.get_by_text("See details").click()
    expect(ended.locator("#ended-details-text")).to_have_text("no server running on /tmp/tmux-1000/default")
    expect(ended.get_by_role("button", name="Start a new terminal")).to_be_hidden()

    ended.get_by_role("button", name="Ask an agent").click()
    asked = [call for call in page.evaluate("window.shellCalls") if call["type"] == "startWithText"]
    assert len(asked) == 1 and "no server running on /tmp/tmux-1000/default" in asked[0]["text"]

    ended.get_by_role("button", name="Try again").click()
    expect(ended).to_be_hidden()
    expect(wrapper.locator("#pty")).to_be_visible()


def test_a_terminal_whose_folder_is_gone_says_so_and_starts_a_new_one_in_the_same_window(
    desktop_context: BrowserContext,
) -> None:
    launched = _serve(desktop_context, _wrapper_html("terminal-1"))
    page, wrapper, pty = _open(desktop_context)

    _print_end(pty, ENDED_MISSING_FOLDER, "/data/gone")

    ended = wrapper.locator("#ended")
    expect(ended.locator("#ended-message")).to_have_text("This terminal closed.")
    expect(ended.locator("#ended-cause")).to_have_text("This terminal's folder no longer exists, so it can't open.")
    expect(ended.get_by_role("button", name="Try again")).to_be_hidden()

    ended.get_by_role("button", name="Start a new terminal").click()

    expect(ended).to_be_hidden()
    expect(wrapper.locator("#pty")).to_have_attribute(
        "src", f"http://{_PTY_LABEL}.{_WRAPPER_HOST}/?arg=_&arg=session&arg=terminal-2"
    )
    assert launched == ["POST"]
    locations = [call for call in page.evaluate("window.shellCalls") if call["type"] == "location"]
    assert locations[-1] == {"type": "location", "path": "/?session=terminal-2", "title": "Terminal 2"}


def test_a_failure_page_asks_an_agent_through_the_shell(desktop_context: BrowserContext) -> None:
    failure = page_failure(TerminalStoreError("the terminal store /x/instances.json is not valid JSON: x"), "terminal-1")
    _serve(desktop_context, render_failure_page(failure))
    page = desktop_context.new_page()
    page.goto(_HOST_URL)
    wrapper = page.frame(url=_WRAPPER_URL)
    assert wrapper is not None

    expect(wrapper.get_by_role("button", name="Try again")).to_be_hidden()
    wrapper.get_by_role("button", name="Ask an agent").click()

    asked = [call for call in page.evaluate("window.shellCalls") if call["type"] == "startWithText"]
    assert len(asked) == 1 and "is not valid JSON" in asked[0]["text"]

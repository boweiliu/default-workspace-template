import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from studio_discord import server, studio


class _FakeShell(BaseHTTPRequestHandler):
    hits: list[str] = []

    def do_GET(self) -> None:  # noqa: N802 -- the stdlib's name
        _FakeShell.hits.append(self.path)
        if self.path == "/_static/app_contract.js":
            body = b"export const connectToShell = () => ({});"
            self.send_response(200)
            self.send_header("Content-Type", "text/javascript")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 -- the stdlib's name
        pass


@pytest.fixture
def fake_shell(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _FakeShell)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{httpd.server_address[1]}"
    monkeypatch.setattr(studio, "SHELL_URL", url)
    studio.clear_module_cache()
    _FakeShell.hits = []
    yield url
    httpd.shutdown()
    studio.clear_module_cache()


@pytest.fixture
def client():  # noqa: ANN201 -- flask's test client type is private
    return server.app.test_client()


def test_index_serves_the_page_with_the_shell_script(client) -> None:
    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Talk to the Studio team" in html
    assert 'from "/_static/app_contract.js"' in html
    assert "__WIDGET_SAMPLE__" not in html and "__SHELL_PAGE_SCRIPT__" not in html


def test_shell_module_is_fetched_from_the_shell_once_then_cached(client, fake_shell: str) -> None:
    first = client.get("/_static/app_contract.js")
    second = client.get("/_static/app_contract.js")
    assert first.status_code == 200
    assert first.mimetype == "text/javascript"
    assert b"connectToShell" in first.data and second.data == first.data
    assert _FakeShell.hits == ["/_static/app_contract.js"]


def test_unknown_module_is_404_without_asking_the_shell(client, fake_shell: str) -> None:
    assert client.get("/_static/../../etc/passwd").status_code == 404
    assert client.get("/_static/other.js").status_code == 404
    assert _FakeShell.hits == []


def test_shell_missing_the_module_is_a_502(client, fake_shell: str) -> None:
    assert client.get("/_static/context_menu.js").status_code == 502


def test_shell_unreachable_is_a_502(client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(studio, "SHELL_URL", "http://127.0.0.1:9")
    studio.clear_module_cache()
    assert client.get("/_static/app_contract.js").status_code == 502


def test_health(client) -> None:
    assert client.get("/health").get_json() == {"status": "ok"}

"""The verify helpers (asset hashes, pixel comparison) and the review prompt/answer handling."""

from pathlib import Path

import pytest
from accounts_preview_checks import _pixel_diff, asset_refs, parse_review, review_prompt
from accounts_preview_common import PreviewError

needs_browser = pytest.mark.timeout(60)

PROD_LOGIN = """<!doctype html>
<html lang="en">
  <head>
    <script type="module" crossorigin src="/accounts/assets/index-CMemAiEY.js"></script>
    <link rel="stylesheet" crossorigin href="/accounts/assets/index-C0HAK5Zs.css">
  </head>
  <body><div id="app"></div></body>
</html>"""


def test_asset_refs_reads_the_hashed_files_an_index_loads() -> None:
    assert asset_refs(PROD_LOGIN) == [
        "/accounts/assets/index-C0HAK5Zs.css",
        "/accounts/assets/index-CMemAiEY.js",
    ]
    assert asset_refs("<html></html>") == []


def _png(page, color: str, height: int = 20) -> bytes:
    page.set_content(
        f'<body style="margin:0"><div style="width:20px;height:{height}px;background:{color}"></div></body>'
    )
    page.set_viewport_size({"width": 20, "height": height})
    return page.screenshot()


@needs_browser
def test_pixel_diff_tells_identical_changed_and_resized_images_apart(browser) -> None:
    page = browser.new_page()
    scratch = browser.new_page()
    try:
        red, red_again, blue, tall = (
            _png(page, "red"),
            _png(page, "red"),
            _png(page, "blue"),
            _png(page, "red", 40),
        )
        assert _pixel_diff(scratch, red, red_again) == {"identical": True, "ratio": 0.0}
        changed = _pixel_diff(scratch, red, blue)
        assert changed["identical"] is False and changed["ratio"] == pytest.approx(1.0)
        resized = _pixel_diff(scratch, red, tall)
        assert resized["identical"] is False and resized["sizes"] == [
            [20, 20],
            [20, 40],
        ]
    finally:
        page.close()
        scratch.close()


def test_review_prompt_names_the_intent_and_every_sheet() -> None:
    prompt = review_prompt(
        "the wordmark reads studio",
        [
            ("/login", "Sign in", Path("/x/login.sheet.png")),
            ("/manage", "Account management", Path("/x/manage.sheet.png")),
        ],
    )
    assert 'The intended change: "the wordmark reads studio"' in prompt
    assert "- /x/login.sheet.png (page /login, Sign in)" in prompt
    assert "- /x/manage.sheet.png (page /manage, Account management)" in prompt
    assert "ONLY a JSON array" in prompt


def test_parse_review_reads_a_fenced_answer() -> None:
    answer = '```json\n[{"page": "/login", "verdict": "pass"}, {"page": "/manage", "verdict": "fail"}]\n```'
    assert parse_review(answer, ["/login", "/manage"]) == [
        {"page": "/login", "verdict": "pass"},
        {"page": "/manage", "verdict": "fail"},
    ]


@pytest.mark.parametrize(
    ("answer", "message"),
    [
        ("Looks good to me!", "no JSON array"),
        ('[{"page": "/login", "verdict": "pass",]', "not valid JSON"),
        ('["/login"]', "not a list of objects"),
        ('[{"page": "/login", "verdict": "pass"}]', r"skipped pages: \['/manage'\]"),
    ],
)
def test_parse_review_rejects_anything_but_a_verdict_per_page(
    answer: str, message: str
) -> None:
    with pytest.raises(PreviewError, match=message):
        parse_review(answer, ["/login", "/manage"])

"""Check a hosted preview before it is shared: ``verify`` (scripted) and ``review`` (one Claude call).

``verify`` runs against the preview app's own local port, so it checks exactly
what reviewers will be served:

- every page loads, and shows content, on both sides;
- the before build's asset files are the very ones prod serves (byte-level:
  vite content-hashes every asset, and the before side is built with prod's
  deploy id), and prod's document pages are byte-identical to the before build's;
- each hosted before page is screenshot-identical to prod (signed-out pages --
  prod has no sample account to compare a signed-in view against);
- before and after differ on the pages the change touches (a page that does not
  differ is a note, not a failure: shared files map conservatively to every page).

It writes one side-by-side sheet per page (prod | before | after) that the
index page shows and ``review`` reads.
"""

from __future__ import annotations

import base64
import html
import json
import re
from pathlib import Path
from typing import Any

from accounts_preview_common import (
    DOC_PAGES,
    PROD_BASE,
    PreviewError,
    Workspace,
    load_claude_p,
    page_label,
    page_state,
    utc_now,
)
from accounts_preview_site import VIEWPORT, http_get, launch_browser, side_url
from playwright.sync_api import sync_playwright

REVIEW_MODEL = "claude-haiku-4-5"

_ASSET_REF = re.compile(r"/accounts/assets/[A-Za-z0-9._-]+")

# Runs in a blank page: decode two PNGs and count the pixels that differ.
_PIXEL_DIFF_JS = """async ([a, b]) => {
  const load = (data) => new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = reject;
    image.src = 'data:image/png;base64,' + data;
  });
  const [first, second] = await Promise.all([load(a), load(b)]);
  if (first.width !== second.width || first.height !== second.height) {
    return {same_size: false, differing: null, total: null,
            sizes: [[first.width, first.height], [second.width, second.height]]};
  }
  const pixels = (image) => {
    const canvas = document.createElement('canvas');
    canvas.width = image.width;
    canvas.height = image.height;
    const context = canvas.getContext('2d');
    context.drawImage(image, 0, 0);
    return context.getImageData(0, 0, image.width, image.height).data;
  };
  const [p, q] = [pixels(first), pixels(second)];
  let differing = 0;
  for (let i = 0; i < p.length; i += 4) {
    if (p[i] !== q[i] || p[i + 1] !== q[i + 1] || p[i + 2] !== q[i + 2] || p[i + 3] !== q[i + 3]) differing++;
  }
  return {same_size: true, differing, total: p.length / 4, sizes: null};
}"""


def asset_refs(index_html: str) -> list[str]:
    """The hashed asset files an index.html loads, e.g. ``/accounts/assets/index-CMemAiEY.js``."""
    return sorted(set(_ASSET_REF.findall(index_html)))


def compare_with_prod(before_dist: Path) -> dict[str, Any]:
    """Byte-level: the before build's asset names (content hashes) and document pages against prod's."""
    status, body = http_get(f"{PROD_BASE}/login")
    if status != 200:
        raise PreviewError(f"{PROD_BASE}/login answered {status}")
    prod_assets = asset_refs(body.decode("utf-8", "replace"))
    before_assets = asset_refs((before_dist / "index.html").read_text())
    docs: dict[str, bool] = {}
    for doc_path in DOC_PAGES:
        local = before_dist / f"{doc_path.strip('/')}.html"
        if not local.is_file():
            continue
        doc_status, doc_body = http_get(f"{PROD_BASE}{doc_path}")
        docs[doc_path] = doc_status == 200 and doc_body == local.read_bytes()
    return {
        "prod_assets": prod_assets,
        "before_assets": before_assets,
        "assets_match": bool(prod_assets) and prod_assets == before_assets,
        "docs_match": docs,
    }


def _pixel_diff(page: Any, first: bytes, second: bytes) -> dict[str, Any]:
    if first == second:
        return {"identical": True, "ratio": 0.0}
    result = page.evaluate(
        _PIXEL_DIFF_JS,
        [base64.b64encode(first).decode(), base64.b64encode(second).decode()],
    )
    if not result["same_size"]:
        return {"identical": False, "ratio": 1.0, "sizes": result["sizes"]}
    return {
        "identical": result["differing"] == 0,
        "ratio": result["differing"] / max(result["total"], 1),
    }


def _shoot(context: Any, url: str) -> tuple[int | None, bytes, bool]:
    """``(status, full-page PNG, has visible text)`` for one URL."""
    page = context.new_page()
    try:
        response = page.goto(url, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(300)
        has_text = bool(
            page.evaluate("document.body && document.body.innerText.trim().length > 0")
        )
        return (
            (response.status if response else None),
            page.screenshot(full_page=True),
            has_text,
        )
    finally:
        page.close()


def _sheet_html(label: str, panels: list[tuple[str, bytes | None]]) -> str:
    cells = []
    for caption, png in panels:
        if png is None:
            body = '<div class="na">No prod comparison: this view is captured signed in as a sample account.</div>'
        else:
            body = f'<img src="data:image/png;base64,{base64.b64encode(png).decode()}">'
        cells.append(
            f"<div class=cell><div class=cap>{html.escape(caption)}</div>{body}</div>"
        )
    return (
        "<!doctype html><html><head><style>"
        "body{margin:0;font:600 14px system-ui,sans-serif;background:#d0d0d0}"
        ".row{display:flex;gap:10px;padding:10px;align-items:flex-start}"
        ".cell{background:#fff}.cap{padding:6px 10px;background:#333;color:#fff}"
        ".na{width:500px;height:200px;display:flex;align-items:center;justify-content:center;"
        "text-align:center;padding:0 30px;box-sizing:border-box;color:#666;font-weight:400}"
        f"</style></head><body><div class=row>{''.join(cells)}</div></body></html>"
    )


def verify_preview(
    ws: Workspace,
    name: str,
    pages: list[str],
    local_url: str,
    allow_prod_mismatch: bool = False,
) -> dict[str, Any]:
    """Run every check against the hosted preview; writes ``site/_raw/verify/`` and returns the report."""
    out = ws.site_dir(name) / "_raw" / "verify"
    out.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    warnings: list[str] = []
    # The rendered site's own copy of the before bundle: a newer build that was
    # never rendered must not vouch for pages rendered from an older one.
    prod = compare_with_prod(ws.site_dir(name) / "_raw" / "before" / "dist")
    if not prod["assets_match"]:
        message = (
            f"the before build's assets {prod['before_assets']} are not the ones prod serves "
            f"{prod['prod_assets']}: prod is not running the before ref"
        )
        (warnings if allow_prod_mismatch else failures).append(message)
    for doc_path, matches in prod["docs_match"].items():
        if not matches:
            message = f"{doc_path} differs from prod's"
            (warnings if allow_prod_mismatch else failures).append(message)
    page_results: dict[str, Any] = {}
    with sync_playwright() as playwright:
        browser = launch_browser(playwright)
        try:
            context = browser.new_context(viewport=VIEWPORT)
            scratch = context.new_page()
            for path in pages:
                label = page_label(path)
                slug = path.strip("/").replace("/", "_")
                entry: dict[str, Any] = {"label": label, "state": page_state(path)}
                shots: dict[str, bytes] = {}
                for side in ("before", "after"):
                    status, png, has_text = _shoot(
                        context, local_url.rstrip("/") + side_url(side, path)
                    )
                    entry[f"{side}_status"] = status
                    if status != 200 or not has_text:
                        failures.append(
                            f"{label} ({side}) did not load: status {status}, visible text {has_text}"
                        )
                    shots[side] = png
                    (out / f"{slug}.{side}.png").write_bytes(png)
                prod_png: bytes | None = None
                if page_state(path) != "signed_in":
                    prod_status, prod_png, _ = _shoot(context, f"{PROD_BASE}{path}")
                    (out / f"{slug}.prod.png").write_bytes(prod_png)
                    comparison = _pixel_diff(scratch, prod_png, shots["before"])
                    entry["prod_status"] = prod_status
                    entry["prod_matches_before"] = comparison["identical"]
                    entry["prod_diff_ratio"] = round(comparison["ratio"], 5)
                    if not comparison["identical"]:
                        message = f"{label}: the before preview does not look like prod ({comparison['ratio']:.2%} of pixels differ)"
                        (warnings if allow_prod_mismatch else failures).append(message)
                change = _pixel_diff(scratch, shots["before"], shots["after"])
                entry["changed"] = not change["identical"]
                entry["change_ratio"] = round(change["ratio"], 5)
                if change["identical"]:
                    warnings.append(f"{label}: before and after look identical")
                sheet_page = context.new_page()
                try:
                    sheet_page.set_content(
                        _sheet_html(
                            label,
                            [
                                ("prod", prod_png),
                                ("before", shots["before"]),
                                ("after", shots["after"]),
                            ],
                        )
                    )
                    sheet_page.wait_for_timeout(200)
                    (out / f"{slug}.sheet.png").write_bytes(
                        sheet_page.screenshot(full_page=True)
                    )
                finally:
                    sheet_page.close()
                entry["sheet"] = f"{slug}.sheet.png"
                page_results[path] = entry
            context.close()
        finally:
            browser.close()
    report = {
        "checked_at": utc_now(),
        "preview_url": local_url,
        "prod": prod,
        "pages": page_results,
        "failures": failures,
        "warnings": warnings,
        "passed": not failures,
    }
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def review_prompt(intent: str, sheets: list[tuple[str, str, Path]]) -> str:
    lines = [
        "You are checking a before/after preview of a change to accounts.imbue.com before it is shared with reviewers.",
        f'The intended change: "{intent}"',
        "Each image is one page, panels left to right: prod, before, after (a prod panel saying there is no comparison",
        "is a signed-in view, judge before vs after only). Read each image with the Read tool:",
    ]
    lines += [f"- {path} (page {route}, {label})" for route, label, path in sheets]
    lines += [
        "For each page decide: does the after panel show the intended change (or, for a page the change should not",
        "affect, does it stay the same); does it show anything broken or unintended (layout shift, missing or",
        "overlapping content, wrong text); and do prod and before match.",
        'Reply with ONLY a JSON array, one object per page: {"page": "<route>", "intended_change_visible": bool,',
        '"unintended_changes": "<empty if none>", "prod_matches_before": bool | null, "verdict": "pass" | "fail"}',
    ]
    return "\n".join(lines)


def parse_review(text: str, routes: list[str]) -> list[dict[str, Any]]:
    """The per-page verdicts from the model's answer; raises when it is not the promised JSON."""
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end <= start:
        raise PreviewError(f"the review answer had no JSON array: {text[:300]!r}")
    try:
        verdicts = json.loads(text[start : end + 1])
    except json.JSONDecodeError as error:
        raise PreviewError(
            f"the review answer was not valid JSON ({error}): {text[:300]!r}"
        ) from error
    if not isinstance(verdicts, list) or not all(
        isinstance(item, dict) for item in verdicts
    ):
        raise PreviewError("the review answer was not a list of objects")
    answered = {str(item.get("page")) for item in verdicts}
    missing = [route for route in routes if route not in answered]
    if missing:
        raise PreviewError(f"the review answer skipped pages: {missing}")
    return verdicts


def review_preview(
    ws: Workspace,
    name: str,
    report: dict[str, Any],
    intent: str,
    model: str = REVIEW_MODEL,
) -> dict[str, Any]:
    """One Claude call over every side-by-side sheet; writes ``site/_raw/verify/review.json``."""
    from_dir = ws.site_dir(name) / "_raw" / "verify"
    sheets = [
        (route, entry["label"], (from_dir / entry["sheet"]).resolve())
        for route, entry in report["pages"].items()
        if entry.get("sheet")
    ]
    if not sheets:
        raise PreviewError(
            "no side-by-side sheets to review -- run the verify step first"
        )
    claude_p = load_claude_p()
    result = claude_p.claude_p_task(
        review_prompt(intent, sheets),
        append_system="Only read the listed image files. Do not edit, create, or run anything.",
        model=model,
    )
    verdicts = parse_review(result.text, [route for route, _, _ in sheets])
    passed = all(str(item.get("verdict")).lower() == "pass" for item in verdicts)
    review = {
        "reviewed_at": utc_now(),
        "intent": intent,
        "model": model,
        "passed": passed,
        "verdicts": verdicts,
        "cost_usd": result.cost_usd,
        "raw_answer": result.text,
    }
    (from_dir / "review.json").write_text(json.dumps(review, indent=2) + "\n")
    return review

# /// script
# requires-python = ">=3.11"
# dependencies = ["playwright==1.58.0", "pydantic>=2"]
# ///
"""Build, check, host, and share a throwaway before/after preview of an accounts.imbue.com change.

Each step is a subcommand; ``all`` chains them and refuses to share until the
checks pass. Every step after ``pages`` reads what it needs from the preview's
``data/.apps/<name>/state.json``, so the steps can be run one at a time.

    run.py all --name studio-wordmark-preview --after origin/studio-wordmark-accounts-header \\
        --intent "the header wordmark reads 'studio' instead of 'minds'; nothing else changes"
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).absolute().parent))

from accounts_preview_checks import REVIEW_MODEL, review_preview, verify_preview  # noqa: E402
from accounts_preview_common import (  # noqa: E402
    DEFAULT_ROOT,
    DOC_PAGES,
    PAGE_CATALOG,
    PreviewError,
    Workspace,
    page_dir_name,
    resolve_commit,
    validate_name,
)
from accounts_preview_hosting import (  # noqa: E402
    host_preview,
    markdown_table,
    public_base_url,
    share_preview,
    teardown_preview,
)
from accounts_preview_pages import discover_pages, read_change, route_sort_key  # noqa: E402
from accounts_preview_site import (  # noqa: E402
    build_side,
    fetch_origin,
    prod_deploy_id,
    render_site,
    write_index,
)


def _say(message: str) -> None:
    sys.stderr.write(message + "\n")
    sys.stderr.flush()


def _require(state: dict[str, Any], key: str, step: str) -> Any:
    if key not in state:
        raise PreviewError(f"preview {state.get('name')!r} has no {key} yet -- run the {step} step first")
    return state[key]


def parse_pages(value: str) -> list[str]:
    pages = [part.strip() for part in value.split(",") if part.strip()]
    known = set(PAGE_CATALOG) | set(DOC_PAGES)
    for page in pages:
        page_dir_name(page)
        if page not in known:
            _say(f"note: {page} is not a page this skill knows; it is captured signed out under its path")
    return sorted(dict.fromkeys(pages), key=route_sort_key)


def step_fetch(ws: Workspace) -> None:
    fetch_origin(ws)
    _say(f"fetched origin in {ws.mngr_repo}")


def step_pages(ws: Workspace, name: str, before: str, after: str, pages: str | None) -> dict[str, Any]:
    validate_name(name)
    before_commit = resolve_commit(ws.mngr_repo, before)
    after_commit = resolve_commit(ws.mngr_repo, after)
    if pages:
        routes, reasons = parse_pages(pages), {"--pages": parse_pages(pages)}
    else:
        changed, sources = read_change(ws.mngr_repo, before_commit, after_commit)
        if not changed:
            raise PreviewError(f"{before}...{after} changes nothing under the accounts frontend")
        routes, reasons = discover_pages(changed, sources)
    ws.update_state(
        name,
        before_ref=before,
        after_ref=after,
        before_commit=before_commit,
        after_commit=after_commit,
        pages=routes,
        page_reasons=reasons,
    )
    return {"pages": routes, "reasons": reasons}


def step_build(ws: Workspace, name: str, side: str, ref: str | None, deploy_id: str | None) -> dict[str, Any]:
    state = ws.load_state(name)
    ref = ref or _require(state, f"{side}_ref", "pages")
    if side == "before" and deploy_id is None:
        deploy_id = prod_deploy_id()
    _say(f"building {side} from {ref} ...")
    provenance = build_side(ws, name, side, ref, deploy_id)
    _say(f"built {side}: {provenance['commit'][:10]} ({provenance['commit_subject']})")
    return provenance


def step_render(ws: Workspace, name: str) -> dict[str, Any]:
    pages = _require(ws.load_state(name), "pages", "pages")
    manifest = render_site(ws, name, pages)
    ws.update_state(name, rendered_at=manifest["rendered_at"], report=None, review=None)
    _say(f"rendered {len(pages)} page(s) per side into {ws.site_dir(name)}")
    return manifest


def step_host(ws: Workspace, name: str) -> dict[str, Any]:
    result = host_preview(ws, name, ws.load_state(name))
    ws.update_state(name, port=result["port"])
    _say(("started" if result["created"] else "already running:") + f" {name} on port {result['port']}")
    return result


def step_verify(ws: Workspace, name: str, preview_url: str | None, allow_prod_mismatch: bool) -> dict[str, Any]:
    state = ws.load_state(name)
    pages = _require(state, "pages", "pages")
    local_url = preview_url or f"http://127.0.0.1:{_require(state, 'port', 'host')}"
    report = verify_preview(ws, name, pages, local_url, allow_prod_mismatch)
    ws.update_state(name, report={k: report[k] for k in ("checked_at", "passed", "failures", "warnings")}, review=None)
    write_index(ws, name, pages, report, None)
    return report


def step_review(ws: Workspace, name: str, intent: str, model: str) -> dict[str, Any]:
    state = ws.load_state(name)
    report_path = ws.site_dir(name) / "_raw" / "verify" / "report.json"
    if not report_path.is_file():
        raise PreviewError(f"preview {name!r} has not been verified yet -- run the verify step first")
    report = json.loads(report_path.read_text())
    review = review_preview(ws, name, report, intent, model)
    ws.update_state(name, review={k: review[k] for k in ("reviewed_at", "intent", "passed", "cost_usd")})
    write_index(ws, name, state["pages"], report, review)
    return review


def step_share(ws: Workspace, name: str, email_domain: str) -> dict[str, Any]:
    state = ws.load_state(name)
    report, review = state.get("report"), state.get("review")
    if not (report and report.get("passed")):
        raise PreviewError(f"preview {name!r} has not passed the verify step; not sharing it")
    if not (review and review.get("passed")):
        raise PreviewError(f"preview {name!r} has not passed the review step; not sharing it")
    result = share_preview(ws, name, email_domain)
    ws.update_state(name, shared_with=result["email_domain"], url=result["url"])
    return result


def step_table(ws: Workspace, name: str, base_url: str | None) -> str:
    pages = _require(ws.load_state(name), "pages", "pages")
    return markdown_table(pages, base_url or public_base_url(ws, name))


def _print_json(value: Any) -> None:
    sys.stdout.write(json.dumps(value, indent=2) + "\n")


def _check_outcome(report: dict[str, Any], review: dict[str, Any] | None, ws: Workspace, name: str) -> None:
    if not report["passed"]:
        raise PreviewError(
            "verify failed -- not sharing:\n  " + "\n  ".join(report["failures"])
            + f"\nSide-by-side sheets: {ws.site_dir(name) / '_raw' / 'verify'}"
        )
    if review is not None and not review["passed"]:
        failing = [item for item in review["verdicts"] if str(item.get("verdict")).lower() != "pass"]
        raise PreviewError(
            "the visual review did not pass -- not sharing:\n  "
            + "\n  ".join(f"{item.get('page')}: {item.get('unintended_changes') or 'intended change not visible'}" for item in failing)
            + f"\nSide-by-side sheets: {ws.site_dir(name) / '_raw' / 'verify'}"
        )


def step_all(ws: Workspace, args: argparse.Namespace) -> str:
    if not args.no_fetch:
        step_fetch(ws)
    found = step_pages(ws, args.name, args.before, args.after, args.pages)
    _say(f"pages: {', '.join(found['pages'])}")
    deploy_id = prod_deploy_id()
    with ThreadPoolExecutor(max_workers=2) as pool:
        before = pool.submit(step_build, ws, args.name, "before", None, deploy_id)
        after = pool.submit(step_build, ws, args.name, "after", None, None)
        before.result()
        after.result()
    step_render(ws, args.name)
    step_host(ws, args.name)
    report = step_verify(ws, args.name, None, args.allow_prod_mismatch)
    _check_outcome(report, None, ws, args.name)
    _say("verify passed; reviewing the side-by-side sheets against the intended change ...")
    review = step_review(ws, args.name, args.intent, args.model)
    _check_outcome(report, review, ws, args.name)
    _say(f"review passed (${review['cost_usd']:.3f})")
    shared = step_share(ws, args.name, args.email_domain)
    _say(f"shared {shared['url']} with @{shared['email_domain']}")
    return step_table(ws, args.name, None)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="workspace root (default: this checkout)")
    parser.add_argument("--mngr-repo", type=Path, help="mngr-internal clone (default: <root>/.external_worktrees/mngr)")
    sub = parser.add_subparsers(dest="command", required=True)

    def named(command: str, help_text: str) -> argparse.ArgumentParser:
        sub_parser = sub.add_parser(command, help=help_text)
        sub_parser.add_argument("--name", required=True, help="preview app name, e.g. studio-wordmark-preview")
        return sub_parser

    sub.add_parser("fetch", help="fetch origin in the mngr clone")
    pages = named("pages", "record the refs and work out which pages the change touches")
    pages.add_argument("--after", required=True, help="the change's ref, e.g. origin/<pr-branch>")
    pages.add_argument("--before", default="origin/main")
    pages.add_argument("--pages", help="comma-separated paths, instead of discovering them")
    build = named("build", "build one side from real source in a throwaway worktree")
    build.add_argument("--side", required=True, choices=["before", "after"])
    build.add_argument("--ref", help="default: the ref the pages step recorded")
    build.add_argument("--deploy-id", help="default: prod's for the before side, none for the after side")
    named("render", "capture every page of both sides as static HTML")
    named("host", "start the preview app (first run) or confirm it is running")
    verify = named("verify", "check the hosted preview against prod and between sides")
    verify.add_argument("--preview-url", help="default: the preview app's local port")
    verify.add_argument("--allow-prod-mismatch", action="store_true", help="report prod differences as notes")
    review = named("review", "one Claude call over the side-by-side sheets")
    review.add_argument("--intent", required=True, help="one sentence: what the change should look like")
    review.add_argument("--model", default=REVIEW_MODEL)
    share = named("share", "grant an email domain access to this preview app only")
    share.add_argument("--email-domain", default="imbue.com")
    table = named("table", "print the PR-description markdown table")
    table.add_argument("--base-url", help="default: the app's public share URL")
    named("teardown", "remove the preview app, its share grant, and its files")
    run_all = named("all", "every step, sharing only once the checks pass")
    run_all.add_argument("--after", required=True)
    run_all.add_argument("--before", default="origin/main")
    run_all.add_argument("--intent", required=True)
    run_all.add_argument("--pages")
    run_all.add_argument("--email-domain", default="imbue.com")
    run_all.add_argument("--model", default=REVIEW_MODEL)
    run_all.add_argument("--no-fetch", action="store_true")
    run_all.add_argument("--allow-prod-mismatch", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    ws = Workspace(args.root, args.mngr_repo)
    try:
        if getattr(args, "name", None) is not None:
            validate_name(args.name)
        if args.command == "fetch":
            step_fetch(ws)
        elif args.command == "pages":
            _print_json(step_pages(ws, args.name, args.before, args.after, args.pages))
        elif args.command == "build":
            _print_json(step_build(ws, args.name, args.side, args.ref, args.deploy_id))
        elif args.command == "render":
            step_render(ws, args.name)
        elif args.command == "host":
            _print_json(step_host(ws, args.name))
        elif args.command == "verify":
            report = step_verify(ws, args.name, args.preview_url, args.allow_prod_mismatch)
            _print_json({k: report[k] for k in ("passed", "failures", "warnings")})
            return 0 if report["passed"] else 1
        elif args.command == "review":
            review = step_review(ws, args.name, args.intent, args.model)
            _print_json({k: review[k] for k in ("passed", "verdicts", "cost_usd")})
            return 0 if review["passed"] else 1
        elif args.command == "share":
            _print_json(step_share(ws, args.name, args.email_domain))
        elif args.command == "table":
            sys.stdout.write(step_table(ws, args.name, args.base_url) + "\n")
        elif args.command == "teardown":
            for line in teardown_preview(ws, args.name) or ["nothing to remove"]:
                _say(line)
        elif args.command == "all":
            sys.stdout.write(step_all(ws, args) + "\n")
    except PreviewError as error:
        _say(f"error: {error}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

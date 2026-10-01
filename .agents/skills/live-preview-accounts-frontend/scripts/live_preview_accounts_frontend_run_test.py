"""The CLI's own rules: names are validated, pages parsed, and nothing is shared before it is checked."""

import pytest
import run
from accounts_preview_common import PreviewError, Workspace, claim_name, is_owned

NAME = "studio-wordmark-preview"


def test_parse_pages_orders_main_pages_first_and_drops_duplicates() -> None:
    assert run.parse_pages("/terms-of-service, /check-inbox,/login,/login") == [
        "/login",
        "/check-inbox",
        "/terms-of-service",
    ]
    for bad in ("login", "/../escape", "/a//b", "/a/"):
        with pytest.raises(PreviewError, match="not a plain route"):
            run.parse_pages(bad)


@pytest.mark.parametrize(
    ("state", "message"),
    [
        ({}, "has not passed the verify step"),
        ({"report": {"passed": False}}, "has not passed the verify step"),
        ({"report": {"passed": True}}, "has not passed the review step"),
        (
            {"report": {"passed": True}, "review": {"passed": False}},
            "has not passed the review step",
        ),
    ],
)
def test_share_refuses_until_verify_and_review_both_passed(
    workspace: Workspace, state: dict, message: str
) -> None:
    workspace.update_state(NAME, skill="live-preview-accounts-frontend", **state)
    with pytest.raises(PreviewError, match=message):
        run.step_share(workspace, NAME, "imbue.com")
    assert not workspace.grants_file.exists()


@pytest.mark.parametrize(
    "name",
    [
        "Studio",
        "a--b",
        "-preview",
        "host-preview",
        "x" * 25 + "-preview",
        "../escape",
        "studio-wordmark",
    ],
)
def test_bad_names_are_refused_before_anything_runs(
    workspace: Workspace, name: str, capsys
) -> None:
    code = run.main(["--root", str(workspace.root), "teardown", f"--name={name}"])
    assert code == 1
    assert "error:" in capsys.readouterr().err


def test_steps_that_need_an_earlier_one_say_which(workspace: Workspace, capsys) -> None:
    assert run.main(["--root", str(workspace.root), "render", "--name", NAME]) == 1
    assert "run the pages step first" in capsys.readouterr().err
    workspace.update_state(
        NAME, skill="live-preview-accounts-frontend", pages=["/login"], port=8099
    )
    assert run.main(["--root", str(workspace.root), "verify", "--name", NAME]) == 1
    assert "run the render step first" in capsys.readouterr().err
    assert (
        run.main(
            ["--root", str(workspace.root), "review", "--name", NAME, "--intent", "x"]
        )
        == 1
    )
    assert "run the verify step first" in capsys.readouterr().err


@pytest.mark.parametrize(
    "occupy",
    [
        lambda ws: ws.apps_registry.write_text(
            '[[apps]]\nname = "studio-wordmark-preview"\nurl = "http://localhost:1"\n'
        ),
        lambda ws: (ws.app_dir(NAME) / "instances.json").parent.mkdir(parents=True),
        lambda ws: (ws.supervisord_dropins / f"{NAME}.conf").write_text(
            "[program:x]\n"
        ),
        lambda ws: (ws.supervisord_dropins / "studio_wordmark_preview.conf").write_text(
            "[program:x]\n"
        ),
    ],
)
def test_a_name_another_app_uses_is_refused(workspace: Workspace, occupy) -> None:
    occupy(workspace)
    with pytest.raises(PreviewError, match="is taken"):
        claim_name(workspace, NAME)
    assert not is_owned(workspace, NAME)


def test_a_preview_this_skill_made_can_be_claimed_again(workspace: Workspace) -> None:
    claim_name(workspace, NAME)
    assert is_owned(workspace, NAME)
    claim_name(workspace, NAME)


def test_changing_the_refs_or_a_build_forgets_the_last_verification(
    workspace: Workspace, monkeypatch
) -> None:
    workspace.update_state(
        NAME,
        skill="live-preview-accounts-frontend",
        rendered_at="t",
        report={"passed": True},
        review={"passed": True},
    )
    monkeypatch.setattr(run, "resolve_commit", lambda repo, ref: ref * 4)
    run.step_pages(workspace, NAME, "origin/main", "origin/x", "/login")
    state = workspace.load_state(NAME)
    assert (state["rendered_at"], state["report"], state["review"]) == (
        None,
        None,
        None,
    )
    with pytest.raises(PreviewError, match="verify step"):
        run.step_share(workspace, NAME, "imbue.com")

"""The CLI's own rules: names are validated, pages parsed, and nothing is shared before it is checked."""

import pytest

import run
from accounts_preview_common import PreviewError, Workspace

NAME = "studio-wordmark-preview"


def test_parse_pages_orders_main_pages_first_and_drops_duplicates() -> None:
    assert run.parse_pages("/terms-of-service, /check-inbox,/login,/login") == ["/login", "/check-inbox", "/terms-of-service"]
    with pytest.raises(PreviewError, match="must be a path"):
        run.parse_pages("login")


@pytest.mark.parametrize(
    ("state", "message"),
    [
        ({}, "has not passed the verify step"),
        ({"report": {"passed": False}}, "has not passed the verify step"),
        ({"report": {"passed": True}}, "has not passed the review step"),
        ({"report": {"passed": True}, "review": {"passed": False}}, "has not passed the review step"),
    ],
)
def test_share_refuses_until_verify_and_review_both_passed(workspace: Workspace, state: dict, message: str) -> None:
    workspace.update_state(NAME, **state)
    with pytest.raises(PreviewError, match=message):
        run.step_share(workspace, NAME, "imbue.com")
    assert not workspace.grants_file.exists()


@pytest.mark.parametrize("name", ["Studio", "a--b", "-preview", "host-preview", "x" * 33, "../escape"])
def test_bad_names_are_refused_before_anything_runs(workspace: Workspace, name: str, capsys) -> None:
    code = run.main(["--root", str(workspace.root), "teardown", f"--name={name}"])
    assert code == 1
    assert "error:" in capsys.readouterr().err


def test_steps_that_need_an_earlier_one_say_which(workspace: Workspace, capsys) -> None:
    assert run.main(["--root", str(workspace.root), "render", "--name", NAME]) == 1
    assert "run the pages step first" in capsys.readouterr().err
    assert run.main(["--root", str(workspace.root), "review", "--name", NAME, "--intent", "x"]) == 1
    assert "run the verify step first" in capsys.readouterr().err

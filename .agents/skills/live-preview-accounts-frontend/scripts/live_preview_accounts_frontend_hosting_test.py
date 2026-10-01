"""Hosting, sharing, the link table, and teardown -- against a scratch workspace and a fake supervisorctl."""

import configparser
import subprocess
import tomllib
from pathlib import Path

import pytest

from accounts_preview_common import PreviewError, Workspace
from accounts_preview_hosting import (
    conf_text,
    host_preview,
    markdown_table,
    pick_port,
    ports_in_use,
    share_preview,
    teardown_preview,
)

NAME = "studio-wordmark-preview"
DOMAIN = "abc.def.us1.imbueminds.com"
LABEL = f"{NAME}-x7k9q2w1"


class FakeSupervisor:
    """Records supervisorctl calls; any other command (forward_port.py --remove) really runs."""

    def __init__(self, running: bool = True) -> None:
        self.calls: list[list[str]] = []
        self.running = running

    def __call__(self, command: list[str]) -> subprocess.CompletedProcess:
        if command[0] != "supervisorctl":
            return subprocess.run(command, capture_output=True, text=True, check=False)
        self.calls.append(command)
        stdout = "lp RUNNING pid 1" if command[1] == "status" and self.running else ""
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")


def _site(ws: Workspace) -> None:
    site = ws.site_dir(NAME)
    site.mkdir(parents=True)
    (site / "index.html").write_text("<!doctype html><title>x</title>")


def _register(ws: Workspace, name: str = NAME, label: str = LABEL, port: int = 8082) -> None:
    with open(ws.apps_registry, "a") as registry:
        registry.write(f'[[apps]]\nname = "{name}"\nurl = "http://localhost:{port}"\nlabel = "{label}"\n\n')


def _enable_sharing(ws: Workspace) -> None:
    ws.share_env.write_text(f"export SHARE_WORKSPACE_DOMAIN={DOMAIN}\n")


def test_conf_is_a_valid_program_block_serving_the_site_and_registering_the_app(workspace: Workspace) -> None:
    text = conf_text(workspace, NAME, 8093)
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string(text)
    section = parser["program:studio_wordmark_preview"]
    command = section["command"]
    assert command.startswith("python3 system/services/oom_priority/bin/oom_tag_service.py user bash -c ")
    assert f"forward_port.py --name {NAME} --url http://localhost:8093" in command
    assert "--program studio_wordmark_preview" in command
    assert "--icon-file data/.apps/studio-wordmark-preview/icon.svg" in command
    assert "exec python3 -m http.server 8093 --bind 127.0.0.1 --directory data/.apps/studio-wordmark-preview/site" in command
    assert section["directory"] == str(workspace.root)
    assert section["stderr_logfile"] == "/var/log/supervisor/studio_wordmark_preview-stderr.log"


def test_pick_port_skips_ports_named_in_dropins_registry_and_already_bound(workspace: Workspace) -> None:
    (workspace.supervisord_dropins / "other.conf").write_text(
        "[program:other]\ncommand=bash -c 'forward_port.py --url http://localhost:8080 && serve'\n"
    )
    _register(workspace, name="thing", label="thing-aaaaaaaa", port=8082)
    assert {8080, 8082, 8081} <= ports_in_use(workspace)
    assert pick_port(workspace, is_bound=lambda port: port == 8083) == 8084


def test_host_writes_the_program_starts_it_and_records_nothing_twice(workspace: Workspace) -> None:
    _site(workspace)
    fake = FakeSupervisor()
    result = host_preview(workspace, NAME, {}, run=fake, is_serving=lambda url, timeout: True)
    conf = workspace.conf_path(NAME)
    assert result["created"] is True
    assert conf.name == "studio_wordmark_preview.conf"
    assert f"http.server {result['port']}" in conf.read_text()
    assert (workspace.app_dir(NAME) / "icon.svg").read_text().startswith("<svg")
    assert ["supervisorctl", "reread"] in fake.calls
    assert ["supervisorctl", "update", "studio_wordmark_preview"] in fake.calls
    again = host_preview(workspace, NAME, {"port": result["port"]}, run=fake, is_serving=lambda url, timeout: True)
    assert again == {"port": result["port"], "created": False}
    assert fake.calls.count(["supervisorctl", "reread"]) == 1


def test_host_starts_a_stopped_program_on_rerun(workspace: Workspace) -> None:
    _site(workspace)
    host_preview(workspace, NAME, {}, run=FakeSupervisor(), is_serving=lambda url, timeout: True)
    stopped = FakeSupervisor(running=False)
    host_preview(workspace, NAME, {"port": 8080}, run=stopped, is_serving=lambda url, timeout: True)
    assert ["supervisorctl", "start", "studio_wordmark_preview"] in stopped.calls


def test_host_refuses_a_program_file_it_did_not_make(workspace: Workspace) -> None:
    _site(workspace)
    workspace.conf_path(NAME).write_text("[program:studio_wordmark_preview]\ncommand=true\n")
    with pytest.raises(PreviewError, match="pick another --name"):
        host_preview(workspace, NAME, {}, run=FakeSupervisor(), is_serving=lambda url, timeout: True)


def test_host_reports_a_preview_that_never_answers(workspace: Workspace) -> None:
    _site(workspace)
    with pytest.raises(PreviewError, match="did not answer"):
        host_preview(workspace, NAME, {}, run=FakeSupervisor(), wait_timeout=0, is_serving=lambda url, timeout: False)


def test_host_needs_a_rendered_site(workspace: Workspace) -> None:
    with pytest.raises(PreviewError, match="render step"):
        host_preview(workspace, NAME, {}, run=FakeSupervisor())


def test_share_adds_the_domain_to_this_app_only_and_keeps_every_other_grant(workspace: Workspace) -> None:
    _enable_sharing(workspace)
    _register(workspace)
    workspace.grants_file.write_text(
        '[workspace]\nusers = []\nemails = ["bowei@imbue.com"]\nemail_domains = []\n\n'
        '[services.signup-preview]\nusers = ["u1"]\nemails = ["josh@imbue.com"]\nemail_domains = ["imbue.com"]\n'
    )
    result = share_preview(workspace, NAME, "@Imbue.com")
    assert result == {"url": f"https://{LABEL}.{DOMAIN}", "email_domain": "imbue.com", "changed": True}
    grants = tomllib.loads(workspace.grants_file.read_text())
    assert grants["workspace"] == {"users": [], "emails": ["bowei@imbue.com"], "email_domains": []}
    assert grants["services"]["signup-preview"]["emails"] == ["josh@imbue.com"]
    assert grants["services"][NAME] == {"users": [], "emails": [], "email_domains": ["imbue.com"]}
    before = workspace.grants_file.read_text()
    assert share_preview(workspace, NAME, "imbue.com")["changed"] is False
    assert workspace.grants_file.read_text() == before
    assert (workspace.grants_file.stat().st_mode & 0o777) == 0o600


def test_share_creates_the_grants_file_when_there_is_none(workspace: Workspace) -> None:
    _enable_sharing(workspace)
    _register(workspace)
    share_preview(workspace, NAME, "imbue.com")
    grants = tomllib.loads(workspace.grants_file.read_text())
    assert grants["workspace"]["email_domains"] == []
    assert grants["services"][NAME]["email_domains"] == ["imbue.com"]


def test_share_refuses_when_sharing_is_off_or_the_app_is_not_registered(workspace: Workspace) -> None:
    with pytest.raises(PreviewError, match="sharing is not enabled"):
        share_preview(workspace, NAME, "imbue.com")
    _enable_sharing(workspace)
    with pytest.raises(PreviewError, match="not registered"):
        share_preview(workspace, NAME, "imbue.com")
    assert not workspace.grants_file.exists()


def test_table_has_one_row_per_page_with_prod_before_and_after_links() -> None:
    table = markdown_table(["/login", "/manage"], f"https://{LABEL}.{DOMAIN}/")
    lines = table.splitlines()
    assert lines[0] == "| Page | Before (prod) | Before (preview) | After (preview) |"
    assert lines[2] == (
        f"| Sign in | [prod](https://accounts.imbue.com/login) | [before](https://{LABEL}.{DOMAIN}/before/login/) "
        f"| [after](https://{LABEL}.{DOMAIN}/after/login/) |"
    )
    assert lines[3].startswith("| Account management (signed in) | [prod](https://accounts.imbue.com/manage) ")
    assert lines[-1] == f"Side-by-side overview of every page: https://{LABEL}.{DOMAIN}/"


def test_teardown_removes_everything_the_preview_made_and_is_rerunnable(workspace: Workspace) -> None:
    _site(workspace)
    _enable_sharing(workspace)
    host_preview(workspace, NAME, {}, run=FakeSupervisor(), is_serving=lambda url, timeout: True)
    _register(workspace, name="keep-me", label="keep-me-aaaaaaaa", port=8090)
    _register(workspace)
    share_preview(workspace, NAME, "imbue.com")
    fake = FakeSupervisor()
    done = teardown_preview(workspace, NAME, run=fake)
    assert len(done) == 4
    assert ["supervisorctl", "stop", "studio_wordmark_preview"] in fake.calls
    assert not workspace.conf_path(NAME).exists()
    assert not workspace.app_dir(NAME).exists()
    apps = tomllib.loads(workspace.apps_registry.read_text())["apps"]
    assert [app["name"] for app in apps] == ["keep-me"]
    assert NAME not in tomllib.loads(workspace.grants_file.read_text()).get("services", {})
    assert teardown_preview(workspace, NAME, run=FakeSupervisor()) == []


def test_teardown_will_not_remove_a_program_file_it_did_not_make(workspace: Workspace) -> None:
    workspace.conf_path(NAME).write_text("[program:studio_wordmark_preview]\ncommand=true\n")
    with pytest.raises(PreviewError, match="not made by this skill"):
        teardown_preview(workspace, NAME, run=FakeSupervisor())
    assert workspace.conf_path(NAME).exists()


def test_teardown_survives_a_partial_preview(workspace: Workspace) -> None:
    (workspace.app_dir(NAME) / "builds").mkdir(parents=True)
    assert teardown_preview(workspace, NAME, run=FakeSupervisor()) == [f"deleted {workspace.app_dir(NAME)}"]
    assert not Path(workspace.app_dir(NAME)).exists()

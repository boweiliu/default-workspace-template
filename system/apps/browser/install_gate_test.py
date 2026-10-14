import json
from datetime import datetime, timedelta, timezone

from browser.install_gate import (
    FORTRESS_UNIT,
    InstallState,
    missing_install_gate,
    unit_failed_since,
)

_BOOT = datetime(2026, 10, 14, 9, 0, tzinfo=timezone.utc)


def _event(event_type: str, unit: str, at: datetime) -> str:
    return json.dumps({"timestamp": at.isoformat(), "type": event_type, "detail": {"unit": unit, "exit_code": 1}})


def test_a_fortress_unit_that_failed_in_this_boot_is_a_failed_install() -> None:
    lines = [
        _event("unit_run", FORTRESS_UNIT, _BOOT - timedelta(days=2)),
        _event("unit_failed", FORTRESS_UNIT, _BOOT + timedelta(minutes=4)),
        _event("unit_run", "1100-secret-scanners.sh", _BOOT + timedelta(minutes=5)),
    ]

    assert unit_failed_since(lines, FORTRESS_UNIT, _BOOT) is True


def test_a_failure_from_a_previous_boot_is_still_installing_until_this_boots_pass_reports() -> None:
    lines = [_event("unit_failed", FORTRESS_UNIT, _BOOT - timedelta(hours=3))]

    assert unit_failed_since(lines, FORTRESS_UNIT, _BOOT) is False


def test_a_later_successful_run_clears_a_failure() -> None:
    lines = [
        _event("unit_failed", FORTRESS_UNIT, _BOOT + timedelta(minutes=1)),
        _event("unit_run", FORTRESS_UNIT, _BOOT + timedelta(minutes=9)),
    ]

    assert unit_failed_since(lines, FORTRESS_UNIT, _BOOT) is False


def test_lines_that_are_not_its_events_are_skipped() -> None:
    lines = [
        "not json",
        json.dumps(["a", "list"]),
        json.dumps({"type": "unit_failed", "detail": "not a dict"}),
        json.dumps({"type": "unit_failed", "timestamp": "yesterday", "detail": {"unit": FORTRESS_UNIT}}),
        _event("unit_failed", "1100-secret-scanners.sh", _BOOT + timedelta(minutes=1)),
    ]

    assert unit_failed_since(lines, FORTRESS_UNIT, _BOOT) is False


def test_a_missing_engine_tells_installing_from_failed() -> None:
    installing = missing_install_gate("Chromium", has_failed=False)
    failed = missing_install_gate("Chromium", has_failed=True)

    assert (installing.state, installing.is_ready) == (InstallState.INSTALLING, False)
    assert (failed.state, failed.is_ready) == (InstallState.FAILED, False)
    assert installing.user_facing_message != failed.user_facing_message
    assert FORTRESS_UNIT in failed.reason

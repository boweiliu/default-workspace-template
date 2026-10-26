"""The apps an update stops to free memory, and how they come back.

``run-status stop-apps`` stops a supervisord program and records it on the run record before the
next one is touched; ``resume-apps`` starts each recorded program and drops it from the record as
it comes up. The record is the point: the pass that stops these apps is the one running out of
memory, so its own chat may be shed before it restores anything, and a landed apply only restores
them by accident (every program is ``autostart=true``, and the apply restarts the services agent).
A pass that ends any other way, or does not reach its end at all, has nothing but this file.

``supervisorctl``, not the control socket, because that is what the rest of this flow and the
skill's prose already use, and the staged copy must run on a workspace whose own tree may predate
any helper. Stdlib-only, like its siblings here.
"""

from collections.abc import Callable, Sequence
from typing import Protocol

# supervisorctl waits out a program's ``startsecs`` (30s for a scaffolded app) before it answers a
# start, so a handful of apps can take a few minutes between them. The teardown is not on the
# user's critical path; a truncated start that left an app down would be.
STOP_TIMEOUT_SECONDS = 120.0
START_TIMEOUT_SECONDS = 180.0

# What supervisord answers for a program that is already in the state being asked for. Both are
# the outcome the caller wanted, so neither is a problem.
_ALREADY_STOPPED = "already stopped"
_ALREADY_STARTED = "already started"


class CompletedCommand(Protocol):
    returncode: int
    stdout: str
    stderr: str


CommandRunner = Callable[[Sequence[str], float], CompletedCommand]


def _answer(result: CompletedCommand) -> str:
    return (result.stdout or result.stderr or "").strip()


def _is_already(result: CompletedCommand, state: str) -> bool:
    return state in _answer(result).lower()


def stop_programs(
    programs: Sequence[str],
    run: CommandRunner,
    record: Callable[[str], None],
) -> list[str]:
    """Stop each program, calling ``record`` for each one that is down afterwards.

    ``record`` is called before the next program is touched, so a pass killed partway through
    leaves a record of everything it has already stopped. Returns one line per program that could
    not be stopped; those are not recorded, since nothing has to bring them back.
    """
    problems: list[str] = []
    for program in programs:
        try:
            result = run(["supervisorctl", "stop", program], STOP_TIMEOUT_SECONDS)
        except OSError as e:
            problems.append(f"could not run supervisorctl for {program}: {e}")
            continue
        if result.returncode != 0 and not _is_already(result, _ALREADY_STOPPED):
            problems.append(f"could not stop {program}: {_answer(result)}")
            continue
        record(program)
    return problems


def start_programs(
    programs: Sequence[str],
    run: CommandRunner,
    forget: Callable[[str], None],
) -> list[str]:
    """Start each program again, calling ``forget`` for each one that is up afterwards.

    A program already running is forgotten too: something else started it, and the record's job is
    done. Returns one line per program still down, which stays on the record so a later
    ``resume-apps`` tries it again.
    """
    problems: list[str] = []
    for program in programs:
        try:
            result = run(["supervisorctl", "start", program], START_TIMEOUT_SECONDS)
        except OSError as e:
            problems.append(f"could not run supervisorctl for {program}: {e}")
            continue
        if result.returncode != 0 and not _is_already(result, _ALREADY_STARTED):
            problems.append(f"could not start {program}: {_answer(result)}")
            continue
        forget(program)
    return problems

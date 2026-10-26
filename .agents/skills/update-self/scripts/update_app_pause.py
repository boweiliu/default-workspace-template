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

# What supervisorctl prints for a program that is already in the state being asked for: ``ERROR
# (not running)`` for a redundant stop, ``ERROR (already started)`` for a redundant start. Either
# is the outcome the caller wanted, so neither is a problem. supervisorctl exits 0 for both (both
# faults are the ignored one for their subcommand), which is what the returncode test catches
# first; this is the belt to that braces, for a supervisorctl that reports them as failures.
_ALREADY_STOPPED = "not running"
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


def _timed_out(result: CompletedCommand) -> bool:
    """Whether the runner gave up waiting rather than hearing a refusal.

    ``update_chat_pause.run_command`` turns a ``subprocess.TimeoutExpired`` into a failed
    ``CompletedProcess`` carrying that exception's text, whose wording is CPython's
    ``Command '...' timed out after N seconds``. There is nothing else to key on, so a runner
    that words a timeout differently reads here as a refusal -- the safe way round for
    ``start_programs``, and for ``stop_programs`` only as safe as not checking at all.
    """
    return "timed out" in _answer(result).lower()


def stop_programs(
    programs: Sequence[str],
    run: CommandRunner,
    record: Callable[[str, bool], None],
) -> list[str]:
    """Stop each program, calling ``record`` for every one this pass may now owe a start.

    ``record`` is called before the next program is touched, so a pass killed partway through
    leaves a record of everything it has already stopped. Its second argument says whether
    supervisorctl confirmed the stop, which a caller that reports the round needs: a timed-out
    stop is recorded without anyone knowing the program is down. Returns one line per program
    that could not be stopped.

    A program is recorded unless supervisorctl plainly refused the stop. A stop that *timed out*
    is recorded as well, and still reported: a timeout says the answer never came, not that the
    program is up, and the asymmetry runs one way. Recording one that turns out to be running
    costs a redundant start the resume forgets; not recording one that is down leaves it stopped
    with nothing to bring it back, which is the whole reason this record exists.
    """
    problems: list[str] = []
    for program in programs:
        try:
            result = run(["supervisorctl", "stop", program], STOP_TIMEOUT_SECONDS)
        except OSError as e:
            problems.append(f"could not run supervisorctl for {program}: {e}")
            continue
        is_stopped = result.returncode == 0 or _is_already(result, _ALREADY_STOPPED)
        if not is_stopped:
            problems.append(f"could not stop {program}: {_answer(result)}")
            if not _timed_out(result):
                continue
        record(program, is_stopped)
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

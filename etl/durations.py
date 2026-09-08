"""How long something took — a run's stamps, and the suite itself.

Split from `etl/probe_ci_history.py` when it passed the 500-line review limit.
Split by SUBJECT: everything there asks what the Actions API SAYS about runs.
This measures DURATIONS, which carries a different hazard — a stamp that will
not parse and a suite that will not finish must both report "unmeasured"
rather than a small number, because in the floor argument a small number is
evidence and an absent one is not.

edtech-kg#109.
"""

from __future__ import annotations

import datetime
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


#: Fallback only, for `--no-time-suite`. The suite is TIMED by default — see
#: `time_the_suite`, which measures ~46s. This was a typed `51`, disclosed as
#: an assertion, and a
#: review was right that disclosure is not measurement: CONTRIBUTING says
#: "every figure in a document is printed by a probe, never typed. If you
#: cannot point at the command, delete the figure", and this is the figure the
#: whole floor argument turns on. If the suite really took 30s the floor would
#: drop toward 40s, the 58s run could have executed tests, and the headline
#: would weaken.
SUITE_SECONDS = 51


#: Set while the probe shells out to pytest, so a probe run started FROM the
#: suite cannot start another one. Without it a test that called `measure()`
#: would fork a suite that forks a suite.
REENTRY = "SAMYAMA_TIMING_THE_SUITE"


def seconds(started: str, ended: str) -> int | None:
    """Wall-clock seconds for one run, or None if either stamp is missing.

    None rather than 0: a run still in flight has no duration, and folding it
    in as zero would drag the floor comparison below toward a conclusion the
    data does not support.
    """
    if not started or not ended:
        return None
    # **Not one hard-coded format.** `%Y-%m-%dT%H:%M:%SZ` matches this
    # instance and nothing else: a fractional second or a `+00:00` offset —
    # both legal ISO-8601 and both emitted by other Gitea builds — returned
    # None, and every None quietly left the duration evidence emptier. The
    # floor argument is a claim about durations, so silently having none is
    # the worst possible failure here.
    #
    # `fromisoformat` handles offsets and fractions. It rejects a trailing
    # `Z` before 3.11, so that is normalised first rather than assumed.
    try:
        elapsed = int((_parse(ended) - _parse(started)).total_seconds())
        if elapsed < 0:
            # `updated_at` before `run_started_at` gave a negative, which
            # flows into the median and can only pull `max_seconds` DOWN —
            # making the floor argument look stronger than the data. Unusable,
            # not small.
            return None
        return elapsed
    except (ValueError, TypeError, AttributeError):
        # TypeError/AttributeError too: a non-string stamp — null, a number, a
        # nested object — raised out of `tally` rather than being read as the
        # unusable timestamp it is.
        return None


def _instant(stamp) -> datetime.datetime | None:
    """A comparable instant, or None if the stamp is unusable."""
    try:
        return _parse(stamp)
    except (ValueError, TypeError, AttributeError):
        return None


def _median(values: list[int]) -> float | None:
    """The middle value, averaging the two middles on an even count."""
    if not values:
        return None
    # `sorted()` is load-bearing: `tally` collects in API order, which is
    # newest-first. Deleting it passed the entire suite because all three
    # median tests fed pre-sorted lists.
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return round((ordered[middle - 1] + ordered[middle]) / 2, 1)


def _parse(stamp: str) -> datetime.datetime:
    """One ISO-8601 timestamp, `Z` or offset, with or without fractions."""
    return datetime.datetime.fromisoformat(
        stamp.replace("Z", "+00:00") if stamp.endswith("Z") else stamp)


def time_the_suite() -> dict:
    """Run the suite and time it. **The floor argument's other half.**

    Shelled out rather than imported: the figure that matters is what a person
    gets from the documented command, and an in-process run would not include
    interpreter start-up or collection, which CI pays for too.

    Returns the seconds AND the command, so the page can point at it. On any
    failure it returns `measured: False` with the reason and the fallback
    constant — a probe must not die because it could not time itself, but it
    must not pass a guess off as a measurement either.
    """
    if os.environ.get(REENTRY):
        return {"seconds": SUITE_SECONDS, "measured": False,
                "why": "re-entered from inside a suite run"}

    # **Deselect the module that reads this record.** Timing the whole suite
    # is circular: `tests/test_ci_history_doc.py` asserts the figure this
    # function is in the middle of producing, so before a first successful run
    # it fails, the exit code is non-zero, and the timing is discarded — the
    # measurement can never bootstrap. The exclusion is recorded, and it is
    # one module of 86 — counted, not estimated: the difference it makes to
    # the figure is far below the run-to-run variance of the figure itself.
    excluded = "tests/test_ci_history_doc.py"
    command = [sys.executable, "-m", "pytest", "-q", "--deselect", excluded]
    # The token is REMOVED. The suite does not need a credential to time
    # itself, and passing the whole environment to a subprocess puts it
    # somewhere it has no reason to be. Output is captured and discarded, so
    # the exposure was small — but small is not a reason to keep it.
    environment = {k: v for k, v in os.environ.items()
                   if k not in ("SAMYAMA_GITEA_TOKEN",)}
    environment[REENTRY] = "1"
    start = time.monotonic()
    try:
        finished = subprocess.run(command, cwd=str(ROOT), env=environment,
                                  capture_output=True, timeout=1800)
    except (OSError, subprocess.SubprocessError) as gone:
        return {"seconds": SUITE_SECONDS, "measured": False, "why": str(gone)}
    elapsed = round(time.monotonic() - start)

    if finished.returncode != 0:
        # A FAILING suite's duration is not the figure the argument wants —
        # pytest can stop early, and a run that died in collection takes no
        # time at all and would drop the floor to nothing.
        return {"seconds": SUITE_SECONDS, "measured": False,
                "why": f"the suite exited {finished.returncode}; a failing "
                       f"run's duration does not bound a passing one",
                "observed_seconds": elapsed}
    return {"seconds": elapsed, "measured": True,
            "command": f"python -m pytest -q --deselect {excluded}",
            "excluded": excluded,
            # COUNTED. The page said "one module of roughly two hundred" and
            # there are 86 — the only figure on it not drawn from the record.
            "of_modules": len(list((ROOT / "tests").glob("test_*.py"))),
            "why_excluded": "it asserts the figure this run produces"}

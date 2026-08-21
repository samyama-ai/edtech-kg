"""Session-level guard: in CI, an unexpected skip fails the run.

`SAMYAMA_REQUIRE_ENGINE=1` already turns an unreachable engine into a failure,
but it only covers the tests that remember to check it. This guard covers the
ones that do not, and every test written from here on, because it works on the
skip itself rather than on the reason a particular file chose to skip.

The failure being guarded against is specific and has happened: a suite reports
green while the tests that would have caught the defect never executed. A skip
is indistinguishable from a pass in every summary line, every badge and every
merge button, so "we run the tests in CI" and "CI proves the tests pass" are
different claims, and only the second one is worth having.

`-rs` in the workflow makes skips VISIBLE. Visible is not enough — nobody reads
a green log. This makes them FAIL.
"""

from __future__ import annotations

import os

# The only skips CI is allowed to have, matched as a substring of the reason.
#
# These four need `data/pwcs` — 960 pages of one district's catalogue. `data/`
# is gitignored by design (KG repos ship loaders, not corpora), so a CI clone
# does not have it, and the alternative is worse than the skip: `read()` walks
# the sitemap and fetches whatever is missing, which from CI means 960 requests
# to a school district on every push.
#
# Deliberately matched on the REASON rather than on test names. A test renamed
# or moved keeps its reason; an allowlist of names would rot into a list that
# exempts tests nobody can find any more.
ALLOWED_SKIPS = ("cached catalogue is incomplete",)

# What the allowlist covers today, measured with no cache present. A cap rather
# than an exact figure: adding a cache-backed test is ordinary work and should
# not need a CI edit, but a jump to 40 means something skipped wholesale and
# that is the case worth failing on.
MAX_ALLOWED_SKIPS = 8

_skipped: list[tuple[str, str]] = []


def pytest_runtest_logreport(report):
    """Record every skip with its reason, wherever it was raised.

    `report.longrepr` for a skip is (path, lineno, "Skipped: <reason>"), and it
    is the same shape whether the skip came from a marker, a `pytest.skip()`
    call inside the test, or a fixture — which is why this hook is used rather
    than inspecting markers at collection time. A fixture-raised skip has no
    marker to find.
    """
    if report.skipped:
        reason = ""
        if isinstance(report.longrepr, tuple) and len(report.longrepr) == 3:
            reason = str(report.longrepr[2])
        _skipped.append((report.nodeid, reason))


def pytest_sessionfinish(session, exitstatus):
    if os.environ.get("SAMYAMA_CI") != "1":
        return

    unexpected = [(nodeid, reason) for nodeid, reason in _skipped
                  if not any(allowed in reason for allowed in ALLOWED_SKIPS)]

    problems = []
    if unexpected:
        problems.append(
            "these tests SKIPPED in CI for a reason that is not on the "
            "allowlist in conftest.py:\n" +
            "\n".join(f"    {nodeid}\n        {reason}" for nodeid, reason in unexpected))
    if len(_skipped) > MAX_ALLOWED_SKIPS:
        problems.append(
            f"{len(_skipped)} tests skipped, which is over the {MAX_ALLOWED_SKIPS} "
            f"this repo expects. Even allowlisted reasons are capped: a jump in "
            f"the count means something stopped running wholesale.")

    if problems:
        # Printed rather than raised: an exception here is reported against the
        # session and reads as a plugin error, which sends the next person to
        # the wrong file.
        print("\n\nCI SKIP GUARD FAILED\n" + "\n\n".join(problems) +
              "\n\nA skip is indistinguishable from a pass in every summary "
              "line. Either make the test run in CI, or add its reason to "
              "ALLOWED_SKIPS with the argument for why it cannot.\n")
        session.exitstatus = 1

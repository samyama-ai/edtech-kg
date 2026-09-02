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
#: A budget PER REASON, not one cap over all of them.
#:
#: A single global cap conflates families that have nothing to do with each
#: other, and it was not doing work at either value it has held. At 8 it was
#: already saturated by the cache family alone — `main` skips 11 and exits 1
#: today, with no changes to it. Raising it to 24 moved the same failure
#: rather than fixing it, and a cap large enough to admit every family is
#: large enough to hide one of them doubling.
#:
#: So each family carries its own number and its own argument. A family that
#: grows fails even when the total does not.
#:
#: MEASURED under CI's conditions and not this machine's: a fresh worktree
#: with no `data/` cache, against an empty engine, with SAMYAMA_REQUIRE_ENGINE
#: and SAMYAMA_CI both set. That distinction is the reason this comment is
#: being rewritten — the previous one claimed the count was taken "with no
#: cache present" and it was not, so the eleven cache skips were invisible to
#: it and the number it recorded could not have been reached in CI.
#:
#: Reproduce with:
#:   git worktree add --detach /tmp/ci origin/main && cd /tmp/ci
#:   SAMYAMA_URL=<empty engine> SAMYAMA_REQUIRE_ENGINE=1 SAMYAMA_CI=1 pytest -q -rs
SKIP_BUDGET = {
    # No `data/` in CI and none wanted: the corpus is a school district's
    # catalogue and the alternative is fetching it on every push.
    #
    # THE ONE FAMILY WITH HEADROOM, and deliberately. 11 is what the tree
    # raises today. The other five sit at exactly their observed count because
    # each is a defect with an issue against it and should shrink to nothing —
    # editing the number down as #133 and #134 land is the point of them. This
    # one is not a defect: adding a cache-gated test is ordinary work, the
    # comment this replaced said so, and a budget of exactly 11 would turn the
    # next such test red for no reason anybody would recognise.
    "cached catalogue is incomplete": 14,
    # `is not re-anchored yet` USED TO LIVE HERE at 6. Tiers 1 to 3 are now a
    # strict xfail rather than a skip — they are not inapplicable, they are
    # known broken, and the two read identically in every summary line. xfail
    # is outside skip accounting entirely, so the entry is gone rather than
    # zeroed: a budget of 0 is a line nothing can ever exceed.
    # Properties of the TIER, not of the run: a tier with no whole-graph
    # statement has none on any machine, loaded district or not. Four tiers,
    # and TWO tests now share the reason — the ratchet half was hoisted out
    # from behind the data gate so it runs with no engine, and it skips the
    # same tiers for the same reason.
    "has no whole-graph statements to check": 8,
    # The three data gates. CI starts a deliberately empty engine, so these
    # cannot run there; `SAMYAMA_REQUIRE_DATA=1` is what turns them into
    # failures in a job that loads a district. Split by reason rather than
    # summed, because they are three different claims about the graph and one
    # of them going quiet should not be absorbed by the other two.
    # Seven, not six: edtech-kg#133 added a test asserting what the inline
    # property map actually does, and it is a statement about the engine, so it
    # is gated like the rest.
    "holds no Course nodes, so a predicate inside a WHERE": 7,
    # Six, which is every tier. Tiers 1 to 3 reached this gate only after
    # edtech-kg#133 fixed them: before that they were strict xfails and left
    # the guard earlier. REPLACING the note that described the state before
    # that rather than adding to it — two justifications stacked on one number
    # leave a reader working out which is live, which is the failure the PR
    # this came from argues against.
    "holds no Course nodes, so no anchor can resolve": 6,
    "holds no prerequisite edges": 2,
}

_skipped: list[tuple[str, str]] = []


def pytest_runtest_logreport(report):
    """Record every skip with its reason, wherever it was raised.

    `report.longrepr` for a skip is (path, lineno, "Skipped: <reason>"), and it
    is the same shape whether the skip came from a marker, a `pytest.skip()`
    call inside the test, or a fixture — which is why this hook is used rather
    than inspecting markers at collection time. A fixture-raised skip has no
    marker to find.
    """
    if not report.skipped:
        return

    # An xfail is reported as skipped too, and it is a DELIBERATE statement that
    # a test is expected to fail — the opposite of a test quietly not running.
    # Its longrepr is a plain string rather than the 3-tuple, so without this it
    # would land here with an empty reason, miss the allowlist, and fail the
    # build with a message pointing nowhere.
    if hasattr(report, "wasxfail"):
        return

    if isinstance(report.longrepr, tuple) and len(report.longrepr) == 3:
        reason = str(report.longrepr[2])
    else:
        # Never blank. An unrecognised shape still has to name itself, or the
        # failure message is an empty line and the next person has nothing to
        # search for.
        reason = str(report.longrepr)
    _skipped.append((report.nodeid, reason))


def budget_problems(skipped) -> list[str]:
    """Every way the skip budget can be violated, as messages.

    Separated from the hook so it can be driven directly. The hook itself sets
    the session exit status, which a test cannot assert on without ending its
    own run.
    """
    problems, counted = [], {key: 0 for key in SKIP_BUDGET}
    unbudgeted, ambiguous = [], []
    for nodeid, reason in skipped:
        matched = [key for key in SKIP_BUDGET if key in reason]
        if not matched:
            unbudgeted.append((nodeid, reason))
        elif len(matched) > 1:
            # AMBIGUOUS IS A FAILURE, not a first-match-wins. Two of these keys
            # are prefixes of the same sentence, and a reason counted against
            # whichever happened to be declared first makes both numbers mean
            # nothing while still adding up.
            ambiguous.append((nodeid, matched))
        else:
            counted[matched[0]] += 1

    if unbudgeted:
        problems.append(
            "these tests SKIPPED in CI for a reason with no entry in "
            "SKIP_BUDGET:\n" +
            "\n".join(f"    {n}\n        {r}" for n, r in unbudgeted))
    if ambiguous:
        problems.append(
            "these skip reasons match more than one SKIP_BUDGET key, so the "
            "counts they feed are arbitrary:\n" +
            "\n".join(f"    {n}\n        matches {m}" for n, m in ambiguous))
    over = [(key, counted[key], SKIP_BUDGET[key])
            for key in SKIP_BUDGET if counted[key] > SKIP_BUDGET[key]]
    if over:
        problems.append(
            "these skip families grew past their budget:\n" +
            "\n".join(f"    {n} skipped, budget {b}    {key!r}"
                       for key, n, b in over))
    return problems


def pytest_sessionfinish(session, exitstatus):
    if os.environ.get("SAMYAMA_CI") != "1":
        return

    problems = budget_problems(_skipped)
    if problems:
        # Printed rather than raised: an exception here is reported against the
        # session and reads as a plugin error, which sends the next person to
        # the wrong file.
        print("\n\nCI SKIP GUARD FAILED\n" + "\n\n".join(problems) +
              "\n\nA skip is indistinguishable from a pass in every summary "
              "line. Either make the test run in CI, or give its reason an "
              "entry in SKIP_BUDGET with the argument for why it cannot.\n")
        session.exitstatus = 1

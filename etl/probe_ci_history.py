"""Every CI run this repo has ever had, read from the Actions API.

edtech-kg#109 asks one question: **can the runner reach the network at all?**
The answer decides whether any repo-side change can turn the tick green, or
whether this belongs to whoever administers the Gitea runner.

The issue's own figures were read off the web UI by hand — "86 runs, zero
successes", "6-15 seconds", "the failing step is `actions/setup-python@v5`".
Two of those three are checkable from the API and are re-measured here. The
third is not: **Gitea exposes no job-log endpoint to a repo-scoped token**, so
which STEP failed cannot be read this way, and nothing below claims it. What
replaces it is a comparison that needs no log at all — see `verdict()`.

Three things are measured:

  * **Every ci.yml run, with its outcome and duration.** A count of successes
    is the whole finding; the durations say whether the suite could even have
    started. The suite is TIMED by the probe (`etl.durations`) rather than
    asserted,
    and CI additionally pulls a container image — so a run that ENDS in 14s
    did not run tests, whatever step it died on.
  * **The diagnostic workflow's outcome.** `runner-diagnostic.yml` (#167) was
    written for this issue with no `uses:` at all — not even
    `actions/checkout` — precisely so that its result isolates one variable.
  * **What each workflow depends on**, read out of the committed YAML rather
    than assumed, so the comparison above is grounded in what the files say.

Reading this needs a token, unlike every other probe here, because the Actions
API is not public on a private repo. `GITEA_TOKEN` or `SAMYAMA_GITEA_TOKEN` — env only, never a flag, so the secret stays out of `/proc/<pid>/cmdline` and shell history. The
record is committed, so the tests read the record and never the network.
"""

from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import sys
import urllib.error
import urllib.request

from etl.identity import USER_AGENT, gitea_token
from etl.provenance import write_record
from etl.durations import (_instant, _median, seconds,
                           time_the_suite, unmeasured_suite)
from etl.ci_history_report import report
from etl.workflow_files import dependencies

ROOT = pathlib.Path(__file__).resolve().parents[1]
RECORD = ROOT / "docs" / "sources" / "ci-history-measured.json"
RECORD_NOTE = ("Measured by `python -m etl.probe_ci_history --record`. Run "
               "outcomes come from the Gitea Actions API; the workflow "
               "dependency counts are read from the committed YAML. Which "
               "STEP failed is NOT measured — see the module docstring.")

API = "https://git.samyama.ai/api/v1/repos/Samyama.ai/edtech-kg"

#: A run that ENDED faster than this cannot have executed the tests, whichever
#: step reported the failure — which is what makes the durations usable
#: without a log.
#:
#: The figure it must clear is `verdict.suite.seconds`, which the probe
#: MEASURES (`etl.durations.time_the_suite`) rather than asserting, plus an
#: untimed container pull. This comment used to justify the floor with a typed
#: `~51s` — the figure that was later measured at 46 and retracted — so the
#: constant's own explanation rested on the number the page exists to reject.
#: `tests/test_ci_history_doc.py` asserts the margin.
FLOOR_SECONDS = 60




class Unreachable(RuntimeError):
    """The API did not answer. Distinct from it answering with no runs."""


def get(url: str, token: str) -> bytes:
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Authorization": f"token {token}"})
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            return response.read()
    except urllib.error.HTTPError as refused:
        raise Unreachable(f"{url}: HTTP {refused.code}") from refused
    except (urllib.error.URLError, TimeoutError, OSError) as gone:
        raise Unreachable(f"{url}: {gone}") from gone




#: Terminal outcomes. A run not in this set has not finished, and its stamps
#: do not describe a completed run.
TERMINAL = {"success", "failure", "cancelled"}








def runs(token: str, limit: int = 250) -> list[dict]:
    """Every run the API will return, newest first — and it must be every one.

    **The count is checked against `total_count`.** "0 successes in 207 runs"
    is only evidence if 207 is the whole history; a page limit silently
    clamped by the server would make the headline vacuously true by not
    looking at the runs that might contradict it. Measured on this instance
    the limit is not clamped — 50, 100 and 250 all returned every run — but a
    finding that rests on a server's pagination behaviour has to assert it
    rather than rely on it.

    The outcome is read from `status`. GitHub-shaped payloads put the terminal
    result in `conclusion` and use `status` for `completed`, which would make
    every run here count as "other" and the zero-success headline true by
    accident. This instance has no `conclusion` key on any run — asserted
    below, so the day one appears the probe stops instead of miscounting.
    """
    # **Paged.** A single `?limit=250` WAS the whole history, so the probe
    # would hard-fail the day it passed 250 — it is at 220 now. Measured: this
    # instance returns every run when no `page` is given and honours `limit`
    # only alongside `page`, which is exactly what hid the missing loop.
    # **DISTINCT runs, keyed on id.** Counting collected items lets a page
    # that repeats a run satisfy the total while a different run is never
    # fetched at all — pages [1,2] then [2] against total 3 gave three items,
    # two of them the same run, and both this loop and the guard below
    # passed. "0 successes in 218 runs" is only evidence if 218 is the whole
    # history, and a duplicate makes it 217 plus a repeat.
    found, seen, page, total = [], set(), 1, None
    while True:
        body = json.loads(
            get(f"{API}/actions/tasks?limit={limit}&page={page}", token))
        batch = body.get("workflow_runs")
        if batch is None:
            raise Unreachable(
                "the Actions API answered without a workflow_runs key")
        if total is None:
            total = body.get("total_count")
        fresh = 0
        for run in batch:
            # Two keyspaces, deliberately: `id` when the API gives one and
            # `run_number` as a fallback. They could in principle collide —
            # and the `total != len(seen)` guard below catches that loudly,
            # which is only true while that guard stays UNCONDITIONAL. It is.
            # `run.get("id", …)` returns None when the key is PRESENT and
            # null, so the fallback never fired and every such run collided on
            # a single None key — silently collapsing the history the
            # deduplication exists to count.
            key = run.get("id")
            if key is None:
                key = run.get("run_number")
            if key is None:
                raise Unreachable(
                    "a run carries neither `id` nor `run_number`, so pages "
                    "cannot be deduplicated and a repeat would read as "
                    "coverage")
            if key not in seen:
                seen.add(key)
                found.append(run)
                fresh += 1
        # No NEW runs on this page means the pager has stopped advancing —
        # a non-empty page of repeats would otherwise loop to the cap.
        if not batch or not fresh or len(seen) >= (total or 0):
            break
        page += 1
        if page > 200:
            raise Unreachable(
                f"stopped after 200 pages with {len(seen)} of {total} runs; "
                f"the pager is not advancing")

    if total is None:
        # **An absent total is a failure, not a pass.** The guard was written
        # `if total is not None and ...`, so the day the key moved — Gitea
        # returns the count in an `X-Total-Count` HEADER on several list
        # endpoints — the assertion the docstring promises would simply stop
        # running, and nothing would say so.
        raise Unreachable(
            "the Actions API answered without a total_count, so the page "
            "cannot be checked for truncation. It may be in an "
            "X-Total-Count header on this build — read it there rather than "
            "deleting this check.")
    if total != len(seen):
        raise Unreachable(
            f"the API reports {total} runs and {len(seen)} distinct ones were "
            f"collected over {page} page(s). Every figure here is a count "
            f"over the whole history, so a short page understates the "
            f"successes as easily as the failures — and a page repeating a "
            f"run would satisfy an item count while leaving another "
            f"unfetched.")

    conclusions = [r for r in found if "conclusion" in r]
    if conclusions:
        raise Unreachable(
            f"{len(conclusions)} run(s) carry a `conclusion` key. This probe "
            f"reads the outcome from `status`; on a GitHub-shaped payload "
            f"`status` is 'completed' and the result is in `conclusion`, so "
            f"reading `status` would count every run as neither success nor "
            f"failure and make '0 successes' true by not looking.")
    unknown = {r.get("status") for r in found} - TERMINAL - {"running", "waiting"}
    if unknown:
        raise Unreachable(f"unrecognised run status(es): {sorted(unknown)}")
    return found


def tally(found: list[dict]) -> dict:
    """Per workflow: how many runs, how many succeeded, and how long they took.

    Keyed by `workflow_id`, which is the filename — so a workflow that is
    renamed reads as a new one rather than silently merging with its old
    history. That is the honest behaviour here: a renamed file is a different
    file to the runner too.
    """
    by_workflow: dict[str, dict] = {}
    for run in found:
        name = run.get("workflow_id") or "(unnamed)"
        seen = by_workflow.setdefault(name, {
            "runs": 0, "success": 0, "failure": 0, "other": 0,
            "durations": [], "first": None, "last": None,
        })
        seen["runs"] += 1
        status = run.get("status")
        seen["success" if status == "success" else
             "failure" if status == "failure" else "other"] += 1
        # **Only finished runs have a duration.** `updated_at` is populated on
        # a run that is still going, so timing one gives however long it has
        # been alive so far — a small number that lands under the floor and
        # counts as evidence that the tests did not run. The floor argument
        # would then be partly built out of runs that had not finished.
        if status in TERMINAL:
            took = seconds(run.get("run_started_at", ""),
                           run.get("updated_at", ""))
            if took is not None:
                seen["durations"].append(took)
        else:
            seen["unfinished"] = seen.get("unfinished", 0) + 1
        started = run.get("run_started_at")
        # Compared as INSTANTS, not strings. String min/max is right for a
        # uniform `…Z` format and silently wrong the moment a stamp carries an
        # offset — the tolerance `_parse` exists for, contradicted two
        # functions later.
        moment = _instant(started)
        if moment is not None:
            if seen["first"] is None or moment < _instant(seen["first"]):
                seen["first"] = started
            if seen["last"] is None or moment > _instant(seen["last"]):
                seen["last"] = started

    for seen in by_workflow.values():
        # Present on every workflow, not only those that had one — an absent
        # key and a zero read the same in a record and mean different things.
        seen.setdefault("unfinished", 0)
        took = sorted(seen.pop("durations"))
        seen["timed"] = len(took)
        # A REAL median. This was `took[len // 2]` — the upper of the two
        # middles — and called a median. The figure reaches a published
        # table, and a name covering two conventions stops being reproducible.
        seen["median_seconds"] = _median(took)
        seen["max_seconds"] = took[-1] if took else None
        # The count that carries the argument: a run cannot have executed a
        # measured suite plus an image pull inside FLOOR_SECONDS.
        # Counted within `took`, which holds only runs whose stamps parsed.
        # The page said "0 of 218 RUNS reached that floor" over a numerator
        # computed across the timed ones — so a run with an unusable stamp
        # dropped out of the evidence while the sentence claimed full
        # coverage. `durations.py` says an absent duration is not a small one;
        # this is where that has to reach the page.
        seen["over_floor"] = sum(1 for t in took if t >= FLOOR_SECONDS)
        seen["untimed"] = seen["runs"] - len(took)
    return by_workflow


def verdict(by_workflow: dict, deps: dict, suite: dict) -> dict:
    """The comparison that answers #109 without reading a single log.

    Two workflows, same runner, same repo, same week. One fetches actions and
    has never once succeeded. One fetches nothing and succeeded first time.
    That isolates the variable to *fetching an action*, and it does so from
    run outcomes alone — which matters, because the job-log endpoint this
    would otherwise need is not available to a repo-scoped token.

    Deliberately returns the EVIDENCE and not a sentence. What to do about it
    is a decision for the issue, and a probe that writes the conclusion into
    the record is a probe whose conclusion nothing can contradict.
    """
    def group(names):
        """Every named workflow's runs added together.

        **This does NOT include `runner-diagnostics.yml`, and that is
        deliberate.** An earlier version of this docstring argued the
        opposite — that reporting 1/1 where the evidence is 2/2 understates
        the comparison — and the file was then changed to exclude it while
        this paragraph was left arguing for the old behaviour. Anyone reading
        it would conclude the exclusion is a bug and put it back.

        The reason for the exclusion: that workflow is no longer in the tree,
        so its `uses:` cannot be read and nothing confirms it fetched no
        actions. It corroborates and it does not verify. `verdict` reports it
        separately under `in_history_but_not_committed`.
        """
        present = [by_workflow[n] for n in names if n in by_workflow]
        if not present:
            return None
        return {
            "workflows": sorted(names),
            "runs": sum(s["runs"] for s in present),
            "success": sum(s["success"] for s in present),
            # FAILURES separately from "not successes". A run cancelled by the
            # concurrency group did not fail, and folding it into the
            # denominator understates a workflow that never failed at all —
            # which is the shape of the whole comparison here.
            "failure": sum(s["failure"] for s in present),
            "other": sum(s["other"] for s in present),
            "uses": sorted({u for n in names
                            for u in deps.get(n, {}).get("uses", [])}),
            "ran_longer_than_the_floor": sum(s["over_floor"] for s in present),
        }

    committed = set(deps)
    action_free = {n for n in committed if deps[n]["count"] == 0}
    # A workflow that ran and is no longer committed cannot have its `uses:`
    # read, so it cannot be classified from the tree. Named rather than
    # dropped: `runner-diagnostics.yml` is one, and silently excluding it is
    # how the 1/1 above happened.
    uncommitted = sorted(set(by_workflow) - committed)

    diagnostic = deps.get("runner-diagnostic.yml", {})
    steps = diagnostic.get("steps", 0)
    tolerant = diagnostic.get("tolerant_steps", 0)

    return {
        "floor_seconds": FLOOR_SECONDS,
        # MEASURED, with the command that measured it — not asserted. The
        # floor below is only a floor if this figure is real.
        "suite": suite,
        "with_actions": group([n for n in committed if deps[n]["count"]]),
        "without_actions": group(action_free),
        "in_history_but_not_committed": uncommitted,
        # **What the diagnostic's SUCCESS does not mean.** Every one of its
        # steps is `continue-on-error`, deliberately, so that one run maps the
        # whole surface instead of stopping at the first broken thing. The
        # cost of that design is that the job reports success whatever its
        # probes found — so "success" here is evidence that the runner
        # SCHEDULED AND RAN a job, and evidence of nothing else. Whether it
        # reached PyPI or the registry is in the log, and the log is not
        # available to a repo-scoped token.
        "diagnostic_outcome_is_informative": bool(steps) and tolerant < steps,
        "diagnostic_steps": steps,
        "diagnostic_tolerant_steps": tolerant,
    }




def measure(token: str, suite_seconds: dict | None = None) -> dict:
    found = runs(token)
    by_workflow = tally(found)
    deps = dependencies()
    return {
        "note": RECORD_NOTE,
        "measured_at": datetime.datetime.now(datetime.timezone.utc)
                               .strftime("%Y-%m-%d"),
        "api": API,
        "runs_returned": len(found),
        "workflows": by_workflow,
        "dependencies": deps,
        "verdict": verdict(by_workflow, deps,
                           suite_seconds or time_the_suite()),
    }




def lost_workflows(measured: dict) -> set[str]:
    """Workflows the committed record names that a new measurement does not.

    Empty when there is no committed record yet — the first run has nothing
    to lose. Otherwise this is a ratchet: the record may gain workflows and
    may only lose them by someone deciding to.
    """
    if not measured.get("workflows"):
        return {"(any workflow at all)"}
    if not RECORD.exists():
        return set()
    committed = json.loads(RECORD.read_text(encoding="utf-8"))
    return set(committed.get("workflows") or {}) - set(measured["workflows"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m etl.probe_ci_history")
    # **No `--token` flag.** It put the secret in `/proc/<pid>/cmdline` and in
    # shell history, and the sibling `etl/probe_review_cost.py` is env-only —
    # two probes against the same host disagreeing about how to take a
    # credential is the drift, one level up from the code.
    
    parser.add_argument("--no-time-suite", action="store_true",
                        help="Skip timing the suite and fall back to the "
                             "recorded constant. The record then says "
                             "measured: false, and the floor argument is "
                             "weaker for it.")
    parser.add_argument("--json", action="store_true",
                        help="Print the measurement instead of writing it — "
                             "what lets someone diff a fresh run against the "
                             "committed record without touching the tree.")
    parser.add_argument("--record", action="store_true",
                        help=f"Write {RECORD.relative_to(ROOT)}.")
    args = parser.parse_args(argv)

    token = gitea_token()
    if not token:
        # NAMED, not a stack trace from a None in a header. Unlike every other
        # probe here this one cannot run against a public endpoint, and the
        # reader deserves to know that is why rather than assuming a bug.
        print("no token: the Actions API is not public on a private repo.\n"
              "  export GITEA_TOKEN=... or SAMYAMA_GITEA_TOKEN=...",
              file=sys.stderr)
        return 2

    try:
        # `--json` implies `--no-time-suite`: a read-only view should not
        # shell out to a 47-second suite run for a figure it only echoes.
        skip = args.no_time_suite or args.json
        measured = measure(
            token,
            suite_seconds=(unmeasured_suite(
                "--no-time-suite" if args.no_time_suite
                else "--json is read-only") if skip else None))
    except Unreachable as gone:
        print(f"unreachable: {gone}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(measured, indent=2, sort_keys=True))
        return 0

    report(measured)
    if args.record:
        # REFUSED on a PARTIAL measurement, not only an empty one. The first
        # guard was `not measured["workflows"]`, so a run returning
        # runner-diagnostic.yml and no ci.yml overwrote the record and exited
        # 0 — and the doc suite then died at COLLECTION on a missing 'ci.yml'
        # key, which is exactly the "reads as a broken test rather than a
        # destroyed artifact" failure the guard was written to close.
        #
        # Reachable without malice: a token scoped to fewer workflows, a
        # renamed ci.yml, or an API blip returning a page that is partial and
        # self-consistent.
        missing = lost_workflows(measured)
        if missing:
            print(f"refusing to --record: the committed record names "
                  f"{sorted(missing)} and this measurement does not. The "
                  f"record is evidence; a partial run must not replace it. "
                  f"If a workflow was genuinely deleted, remove it from the "
                  f"record deliberately.", file=sys.stderr)
            return 4
        # Through the shared writer, so the record carries the commit that
        # produced it (#6). Not `RECORD.write_text` — a record nobody can date
        # to a revision is a figure with no way back to the code behind it.
        write_record(RECORD, measured)
        print(f"  -> {RECORD.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

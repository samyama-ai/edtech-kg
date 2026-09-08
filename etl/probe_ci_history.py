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
    started. The repo's own suite takes ~51s locally against a loaded engine,
    and CI additionally pulls a container image — so a run that ENDS in 14s
    did not run tests, whatever step it died on.
  * **The diagnostic workflow's outcome.** `runner-diagnostic.yml` (#167) was
    written for this issue with no `uses:` at all — not even
    `actions/checkout` — precisely so that its result isolates one variable.
  * **What each workflow depends on**, read out of the committed YAML rather
    than assumed, so the comparison above is grounded in what the files say.

Reading this needs a token, unlike every other probe here, because the Actions
API is not public on a private repo. `SAMYAMA_GITEA_TOKEN` or `--token`. The
record is committed, so the tests read the record and never the network.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

from etl.identity import USER_AGENT
from etl.provenance import write_record
from etl.durations import (SUITE_SECONDS, _instant, _median, seconds,
                           time_the_suite)
from etl.workflow_files import dependencies

ROOT = pathlib.Path(__file__).resolve().parents[1]
RECORD = ROOT / "docs" / "sources" / "ci-history-measured.json"
RECORD_NOTE = ("Measured by `python -m etl.probe_ci_history --record`. Run "
               "outcomes come from the Gitea Actions API; the workflow "
               "dependency counts are read from the committed YAML. Which "
               "STEP failed is NOT measured — see the module docstring.")

API = "https://git.samyama.ai/api/v1/repos/Samyama.ai/edtech-kg"

#: The suite takes ~51s locally with an engine already up. CI additionally
#: pulls a container image and polls for it. A run that ENDED faster than this
#: cannot have executed the tests, whichever step reported the failure — which
#: is what makes the durations usable without a log.
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
            key = run.get("id", run.get("run_number"))
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
        # ~51s suite plus an image pull inside FLOOR_SECONDS.
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

        The first version compared ONE action-free workflow against ci.yml,
        and the history holds two — `runner-diagnostics.yml` preceded
        `runner-diagnostic.yml` and also succeeded. Reporting 1/1 where the
        evidence is 2/2 understates the very comparison the page rests on.
        """
        present = [by_workflow[n] for n in names if n in by_workflow]
        if not present:
            return None
        return {
            "workflows": sorted(names),
            "runs": sum(s["runs"] for s in present),
            "success": sum(s["success"] for s in present),
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


def report(measured: dict) -> None:
    out = measured["workflows"]
    print(f"  {measured['runs_returned']} runs returned by the API\n")
    for name in sorted(out):
        seen = out[name]
        uses = measured["dependencies"].get(name, {}).get("count")
        print(f"  {name}")
        print(f"    {seen['runs']} run(s), {seen['success']} success, "
              f"{seen['failure']} failure, {seen['other']} other")
        print(f"    {seen['first']} .. {seen['last']}")
        print(f"    median {seen['median_seconds']}s, max {seen['max_seconds']}s, "
              f"{seen['over_floor']} run(s) over the {FLOOR_SECONDS}s floor")
        print(f"    uses: {uses if uses is not None else 'not committed here'}")
        print()

    check = measured["verdict"]
    with_actions, without = check["with_actions"], check["without_actions"]
    if with_actions and without:
        print(f"  With actions ({', '.join(with_actions['uses']) or 'none'}): "
              f"{with_actions['success']}/{with_actions['runs']} succeeded")
        print(f"  Without actions "
              f"({', '.join(without['workflows'])}): "
              f"{without['success']}/{without['runs']} succeeded")
    if check["in_history_but_not_committed"]:
        print(f"  ran but not committed, so unclassifiable from the tree: "
              f"{', '.join(check['in_history_but_not_committed'])}")
    # Only when there IS a diagnostic. With the workflow deleted this printed
    # "0 of 0 diagnostic steps are continue-on-error" — a sentence about a
    # file that does not exist.
    if not check["diagnostic_steps"]:
        print("\n  NOTE: no runner-diagnostic.yml is committed, so nothing "
              "here isolates fetching an action as the variable.")
    elif not check["diagnostic_outcome_is_informative"]:
        print(f"\n  NOTE: {check['diagnostic_tolerant_steps']} of "
              f"{check['diagnostic_steps']} diagnostic steps are "
              f"continue-on-error, so its SUCCESS means the job ran — not "
              f"that anything it probed worked. That answer is in the log.")


def gitea_token() -> str | None:
    """The token, from the environment only — the names the sibling uses."""
    for name in ("GITEA_TOKEN", "SAMYAMA_GITEA_TOKEN"):
        if os.environ.get(name):
            return os.environ[name]
    return None


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
        measured = measure(
            token,
            suite_seconds=({"seconds": SUITE_SECONDS, "measured": False,
                            "why": "--no-time-suite"}
                           if args.no_time_suite else None))
    except Unreachable as gone:
        print(f"unreachable: {gone}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(measured, indent=2, sort_keys=True))
        return 0

    report(measured)
    if args.record and not measured["workflows"]:
        # REFUSED. A zero-run measurement overwrote the committed record and
        # exited 0; the doc tests then errored at COLLECTION on a missing key,
        # which reads as a broken test rather than a destroyed artifact — and
        # by then it was already gone. The same principle `durations.py`
        # states for the suite: a probe must not pass an absence off as a
        # measurement.
        print("refusing to --record a measurement with no workflows in it; "
              "the committed record is evidence and this would replace it "
              "with nothing.", file=sys.stderr)
        return 4
    if args.record:
        # Through the shared writer, so the record carries the commit that
        # produced it (#6). Not `RECORD.write_text` — a record nobody can date
        # to a revision is a figure with no way back to the code behind it.
        write_record(RECORD, measured)
        print(f"  -> {RECORD.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

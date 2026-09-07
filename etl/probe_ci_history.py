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
import re
import sys
import urllib.error
import urllib.request

from etl.identity import USER_AGENT
from etl.provenance import write_record

ROOT = pathlib.Path(__file__).resolve().parents[1]
RECORD = ROOT / "docs" / "sources" / "ci-history-measured.json"
RECORD_NOTE = ("Measured by `python -m etl.probe_ci_history --record`. Run "
               "outcomes come from the Gitea Actions API; the workflow "
               "dependency counts are read from the committed YAML. Which "
               "STEP failed is NOT measured — see the module docstring.")

API = "https://git.samyama.ai/api/v1/repos/Samyama.ai/edtech-kg"
WORKFLOWS = ROOT / ".github" / "workflows"

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


def seconds(started: str, ended: str) -> int | None:
    """Wall-clock seconds for one run, or None if either stamp is missing.

    None rather than 0: a run still in flight has no duration, and folding it
    in as zero would drag the floor comparison below toward a conclusion the
    data does not support.
    """
    if not started or not ended:
        return None
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    try:
        return int((datetime.datetime.strptime(ended, fmt)
                    - datetime.datetime.strptime(started, fmt)).total_seconds())
    except ValueError:
        return None


def runs(token: str, limit: int = 250) -> list[dict]:
    """Every run the API will return, newest first."""
    body = json.loads(get(f"{API}/actions/tasks?limit={limit}", token))
    found = body.get("workflow_runs")
    if found is None:
        raise Unreachable("the Actions API answered without a workflow_runs key")
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
        took = seconds(run.get("run_started_at", ""), run.get("updated_at", ""))
        if took is not None:
            seen["durations"].append(took)
        started = run.get("run_started_at")
        if started:
            seen["first"] = min(seen["first"] or started, started)
            seen["last"] = max(seen["last"] or started, started)

    for seen in by_workflow.values():
        took = sorted(seen.pop("durations"))
        seen["timed"] = len(took)
        seen["median_seconds"] = took[len(took) // 2] if took else None
        seen["max_seconds"] = took[-1] if took else None
        # The count that carries the argument: a run cannot have executed a
        # ~51s suite plus an image pull inside FLOOR_SECONDS.
        seen["over_floor"] = sum(1 for t in took if t >= FLOOR_SECONDS)
    return by_workflow


def dependencies() -> dict:
    """What each committed workflow fetches, read from the YAML.

    `uses:` is the line that needs the runner to fetch something from outside.
    A workflow with none of them exercises the runner and nothing else, which
    is what makes `runner-diagnostic.yml`'s outcome mean something.

    Read with a regex rather than a YAML parser on purpose: the suite has no
    third-party dependency beyond pytest, and adding one to count six lines
    would be a heavier price than the parse is worth. The pattern is anchored
    to a list item so a `uses:` inside a comment or a string does not count.
    """
    found = {}
    for path in sorted(WORKFLOWS.glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        uses = re.findall(r"^\s*-?\s*uses:\s*(\S+)", text, re.M)
        found[path.name] = {
            "uses": sorted(set(uses)),
            "count": len(uses),
            # A step marked `continue-on-error` cannot fail its job. Counted
            # because it decides whether the JOB'S OUTCOME carries information
            # at all — see `verdict`.
            "steps": len(re.findall(r"^\s+- name:", text, re.M)),
            "tolerant_steps": len(re.findall(r"continue-on-error:\s*true", text)),
        }
    return found


def verdict(by_workflow: dict, deps: dict) -> dict:
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
    def summary(name):
        seen = by_workflow.get(name)
        if not seen:
            return None
        return {
            "runs": seen["runs"],
            "success": seen["success"],
            "uses": deps.get(name, {}).get("uses", []),
            "median_seconds": seen["median_seconds"],
            "ran_longer_than_the_floor": seen["over_floor"],
        }

    diagnostic = deps.get("runner-diagnostic.yml", {})
    steps = diagnostic.get("steps", 0)
    tolerant = diagnostic.get("tolerant_steps", 0)

    return {
        "floor_seconds": FLOOR_SECONDS,
        "with_actions": summary("ci.yml"),
        "without_actions": summary("runner-diagnostic.yml"),
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


def measure(token: str) -> dict:
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
        "verdict": verdict(by_workflow, deps),
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
        print(f"  Without actions: "
              f"{without['success']}/{without['runs']} succeeded")
    if not check["diagnostic_outcome_is_informative"]:
        print(f"\n  NOTE: {check['diagnostic_tolerant_steps']} of "
              f"{check['diagnostic_steps']} diagnostic steps are "
              f"continue-on-error, so its SUCCESS means the job ran — not "
              f"that anything it probed worked. That answer is in the log.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m etl.probe_ci_history")
    parser.add_argument("--token", default=os.environ.get("SAMYAMA_GITEA_TOKEN"),
                        help="Gitea token; defaults to $SAMYAMA_GITEA_TOKEN.")
    parser.add_argument("--record", action="store_true",
                        help=f"Write {RECORD.relative_to(ROOT)}.")
    args = parser.parse_args(argv)

    if not args.token:
        # NAMED, not a stack trace from a None in a header. Unlike every other
        # probe here this one cannot run against a public endpoint, and the
        # reader deserves to know that is why rather than assuming a bug.
        print("no token: the Actions API is not public on a private repo.\n"
              "  export SAMYAMA_GITEA_TOKEN=... , or pass --token",
              file=sys.stderr)
        return 2

    try:
        measured = measure(args.token)
    except Unreachable as gone:
        print(f"unreachable: {gone}", file=sys.stderr)
        return 1

    report(measured)
    if args.record:
        # Through the shared writer, so the record carries the commit that
        # produced it (#6). Not `RECORD.write_text` — a record nobody can date
        # to a revision is a figure with no way back to the code behind it.
        write_record(RECORD, measured)
        print(f"  -> {RECORD.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

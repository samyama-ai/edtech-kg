"""The CI-history probe's arithmetic, driven without the network.

The probe answers #109 by comparing two workflows' outcomes, so the parts that
must be right are the tally, the duration floor, and the one thing the probe
deliberately refuses to conclude — that a tolerant workflow's success means
anything about what it probed.
"""

from __future__ import annotations

import pytest

from etl import probe_ci_history as probe


def run(workflow="ci.yml", status="failure", started="2026-09-01T05:00:00Z",
        updated="2026-09-01T05:00:07Z"):
    return {"workflow_id": workflow, "status": status,
            "run_started_at": started, "updated_at": updated}


def test_a_run_still_in_flight_has_no_duration_rather_than_zero():
    """None, not 0. Folding an unfinished run in as zero would drag the median
    down toward a conclusion the data does not support — and the whole floor
    argument is a claim about durations."""
    assert probe.seconds("2026-09-01T05:00:00Z", "") is None
    assert probe.seconds("", "2026-09-01T05:00:07Z") is None
    assert probe.seconds("not a date", "2026-09-01T05:00:07Z") is None
    assert probe.seconds("2026-09-01T05:00:00Z", "2026-09-01T05:00:07Z") == 7


def test_the_tally_counts_outcomes_and_keeps_them_apart():
    found = [run(status="failure"), run(status="failure"),
             run(status="success"), run(status="cancelled")]
    tallied = probe.tally(found)["ci.yml"]
    assert (tallied["runs"], tallied["success"], tallied["failure"],
            tallied["other"]) == (4, 1, 2, 1)


def test_a_renamed_workflow_does_not_merge_with_its_own_history():
    """Keyed by filename. A rename reads as a new workflow, which is the
    honest behaviour — it is a different file to the runner too. The repo has
    a real instance: `runner-diagnostics.yml` preceded `runner-diagnostic.yml`.
    """
    tallied = probe.tally([run(workflow="a.yml"), run(workflow="b.yml")])
    assert sorted(tallied) == ["a.yml", "b.yml"]


def test_the_floor_counts_runs_that_could_have_executed_the_suite():
    """The claim "the tests never ran" rests entirely on this count."""
    found = [run(updated="2026-09-01T05:00:07Z"),    # 7s
             run(updated="2026-09-01T05:00:59Z"),    # 59s — under
             run(updated="2026-09-01T05:01:00Z"),    # 60s — at the floor
             run(updated="2026-09-01T05:02:00Z")]    # 120s
    tallied = probe.tally(found)["ci.yml"]
    assert tallied["over_floor"] == 2, (
        f"the floor is {probe.FLOOR_SECONDS}s and it must be inclusive")
    # The UPPER of the two middles on an even count — `took[len // 2]`, not
    # the mean of the pair. Asserted rather than glossed: the figure reaches a
    # published document, and "median" covering two different conventions is
    # how a number becomes unreproducible.
    assert tallied["median_seconds"] == 60
    assert probe.tally(found[:3])["ci.yml"]["median_seconds"] == 59


def test_a_workflow_whose_steps_all_tolerate_failure_reports_nothing_by_succeeding():
    """The finding this probe most needs to get right, and the one it would be
    easiest to overstate.

    `runner-diagnostic.yml` marks every step `continue-on-error`, so it
    reports success whatever its probes found. Reading that success as "the
    runner has network" is precisely the guard-that-cannot-fail this
    repository keeps finding in its own tests.
    """
    deps = {"runner-diagnostic.yml": {"uses": [], "count": 0,
                                      "steps": 8, "tolerant_steps": 8}}
    check = probe.verdict({}, deps, probe.SUITE_SECONDS)
    assert check["diagnostic_outcome_is_informative"] is False

    deps["runner-diagnostic.yml"]["tolerant_steps"] = 7
    assert probe.verdict({}, deps, probe.SUITE_SECONDS)[
        "diagnostic_outcome_is_informative"] is True


def test_a_workflow_with_no_steps_is_not_called_informative():
    """`bool(steps) and ...` — without the guard, 0 tolerant of 0 steps reads
    as informative, and an empty file would be evidence of something."""
    deps = {"runner-diagnostic.yml": {"uses": [], "count": 0,
                                      "steps": 0, "tolerant_steps": 0}}
    assert probe.verdict({}, deps, probe.SUITE_SECONDS)[
        "diagnostic_outcome_is_informative"] is False


def test_dependencies_reads_the_committed_workflows():
    """Read from the YAML, never typed — the `uses:` count is what the whole
    comparison in the document rests on."""
    found = probe.dependencies()
    assert "ci.yml" in found, "ci.yml is not committed"
    assert found["ci.yml"]["count"] >= 2, (
        "ci.yml fetches actions; if it stops doing so the document's "
        "comparison no longer says anything")
    assert "actions/setup-python@v5" in found["ci.yml"]["uses"]


def test_the_diagnostic_still_fetches_nothing():
    """The comparison is only valid while this stays true. If someone adds an
    action to the diagnostic, the two workflows stop differing in one variable
    and the document's conclusion goes with it."""
    found = probe.dependencies()
    if "runner-diagnostic.yml" not in found:
        pytest.skip("the diagnostic has been removed — #109 is closed")
    assert found["runner-diagnostic.yml"]["count"] == 0, (
        "the diagnostic fetches an action now, so its outcome no longer "
        "isolates fetching as the variable")


def test_an_api_answer_without_runs_is_an_error_not_an_empty_history(monkeypatch):
    """A shape change that dropped the key would otherwise read as "this repo
    has never run CI" — which is the finding, arrived at by not looking.

    `{"workflow_runs": []}` is a different thing and must NOT raise: a repo
    with no runs yet is a real state, and conflating it with a broken response
    is the same mistake in the other direction.
    """
    monkeypatch.setattr(probe, "get", lambda url, token: b'{"total_count": 0}')
    with pytest.raises(probe.Unreachable):
        probe.runs("token")

    monkeypatch.setattr(probe, "get", lambda url, token: b'{"workflow_runs": []}')
    assert probe.runs("token") == []


def test_a_truncated_page_is_an_error_not_a_shorter_history(monkeypatch):
    """"0 successes in 211 runs" is only evidence if 211 is the whole history.
    A clamped page would understate the successes as easily as the failures,
    and make the headline true by not looking."""
    monkeypatch.setattr(
        probe, "get",
        lambda url, token: b'{"total_count": 300, "workflow_runs": []}')
    with pytest.raises(probe.Unreachable) as gone:
        probe.runs("token")
    assert "300" in str(gone.value)


def test_a_github_shaped_payload_stops_the_run(monkeypatch):
    """`status` is 'completed' there and the result is in `conclusion`, so
    reading `status` would count every run as neither success nor failure —
    and "0 successes" would be true because nothing was examined."""
    monkeypatch.setattr(
        probe, "get",
        lambda url, token:
        b'{"total_count": 1, "workflow_runs": [{"workflow_id": "ci.yml",'
        b' "status": "completed", "conclusion": "success"}]}')
    with pytest.raises(probe.Unreachable) as gone:
        probe.runs("token")
    assert "conclusion" in str(gone.value)


def test_an_unfinished_run_contributes_no_duration():
    """`updated_at` is populated while a run is still going, so timing one
    gives how long it has been alive — a small number that lands under the
    floor and counts as evidence the tests did not run."""
    found = [run(status="running", updated="2026-09-01T05:00:03Z"),
             run(status="failure", updated="2026-09-01T05:00:07Z")]
    tallied = probe.tally(found)["ci.yml"]
    assert tallied["timed"] == 1, "the running job was timed"
    assert tallied["unfinished"] == 1
    assert tallied["median_seconds"] == 7


def test_steps_and_tolerant_steps_are_counted_the_same_way():
    """They must not drift in opposite directions. `^\\s+- name:` saw only
    steps whose first key is `name` — missing `- uses:` and `- run:` — while
    an unanchored `continue-on-error: true` matched comments and job-level
    keys, so `tolerant < steps` could invert on an unchanged workflow.
    """
    workflow = """
jobs:
  test:
    steps:
      - uses: actions/checkout@v4
      - name: Something
        run: echo hi
      - run: echo bare
        continue-on-error: true
      # continue-on-error: true   <- a comment, not a step
  other:
    continue-on-error: true
"""
    counted = probe.step_counts(workflow)
    assert counted["steps"] == 3, "a step leading with uses: or run: is a step"
    assert counted["tolerant_steps"] == 1, (
        "only the real key indented under a step counts — not the comment, "
        "and not the job-level one")


def test_the_action_free_comparison_uses_every_action_free_workflow():
    """The history holds two diagnostics — the singular and an earlier plural
    — and both succeeded. Reporting 1/1 where the evidence is 2/2 understates
    the comparison the whole page rests on."""
    by_workflow = {
        "ci.yml": {"runs": 211, "success": 0, "over_floor": 0,
                   "median_seconds": 7},
        "a.yml": {"runs": 1, "success": 1, "over_floor": 0, "median_seconds": 5},
        "b.yml": {"runs": 3, "success": 3, "over_floor": 0, "median_seconds": 6},
    }
    deps = {"ci.yml": {"uses": ["actions/checkout@v4"], "count": 1,
                       "steps": 7, "tolerant_steps": 0},
            "a.yml": {"uses": [], "count": 0, "steps": 8, "tolerant_steps": 8},
            "b.yml": {"uses": [], "count": 0, "steps": 2, "tolerant_steps": 0}}
    check = probe.verdict(by_workflow, deps, 51)
    assert check["without_actions"]["runs"] == 4
    assert check["without_actions"]["success"] == 4
    assert check["without_actions"]["workflows"] == ["a.yml", "b.yml"]


def test_a_workflow_that_ran_and_is_not_committed_is_named_not_dropped():
    """Its `uses:` cannot be read, so it cannot be classified from the tree.
    Silently excluding it is how the 1/1 above happened."""
    check = probe.verdict(
        {"ci.yml": {"runs": 1, "success": 0, "over_floor": 0,
                    "median_seconds": 7},
         "deleted.yml": {"runs": 1, "success": 1, "over_floor": 0,
                         "median_seconds": 6}},
        {"ci.yml": {"uses": ["x"], "count": 1, "steps": 1,
                    "tolerant_steps": 0}}, 51)
    assert check["in_history_but_not_committed"] == ["deleted.yml"]

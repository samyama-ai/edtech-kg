"""The CI-history probe's arithmetic, driven without the network.

The probe answers #109 by comparing two workflows' outcomes, so the parts that
must be right are the tally, the duration floor, and the one thing the probe
deliberately refuses to conclude — that a tolerant workflow's success means
anything about what it probed.
"""

from __future__ import annotations

import pytest

from etl import probe_ci_history as probe
# The YAML reading lives in its own module since the split — imported
# from where it lives rather than re-exported through the probe.
from etl import durations
from etl import workflow_files


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
    # A REAL median: the mean of the two middles on an even count. This was
    # `took[len // 2]` — the upper of the two — and called a median. The
    # figure reaches a published table, and a name covering two different
    # conventions is how a number stops being reproducible.
    assert tallied["median_seconds"] == 59.5
    assert probe.tally(found[:3])["ci.yml"]["median_seconds"] == 59.0


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
    found = workflow_files.dependencies()
    assert "ci.yml" in found, "ci.yml is not committed"
    assert found["ci.yml"]["count"] >= 2, (
        "ci.yml fetches actions; if it stops doing so the document's "
        "comparison no longer says anything")
    assert "actions/setup-python@v5" in found["ci.yml"]["uses"]


def test_the_diagnostic_still_fetches_nothing():
    """The comparison is only valid while this stays true. If someone adds an
    action to the diagnostic, the two workflows stop differing in one variable
    and the document's conclusion goes with it."""
    found = workflow_files.dependencies()
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

    # `total_count` is required now, so an empty history states it as 0.
    monkeypatch.setattr(
        probe, "get",
        lambda url, token: b'{"total_count": 0, "workflow_runs": []}')
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
        b'{"total_count": 1, "workflow_runs": [{"id": 1,'
        b' "workflow_id": "ci.yml", "status": "completed",'
        b' "conclusion": "success"}]}')
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


def test_a_timestamp_this_instance_does_not_use_still_parses():
    """A fractional second or a `+00:00` offset — both legal ISO-8601, both
    emitted by other Gitea builds — returned None, and every None quietly left
    the duration evidence emptier. The floor argument is a claim ABOUT
    durations, so silently having none is the worst failure available here."""
    pairs = [("2026-09-01T05:00:00Z", "2026-09-01T05:00:07Z"),
             ("2026-09-01T05:00:00.123Z", "2026-09-01T05:00:07.456Z"),
             ("2026-09-01T05:00:00+00:00", "2026-09-01T05:00:07+00:00"),
             ("2026-09-01T10:30:00+05:30", "2026-09-01T05:00:07+00:00")]
    for started, ended in pairs:
        assert probe.seconds(started, ended) == 7, (started, ended)
    assert probe.seconds("not a date", "2026-09-01T05:00:07Z") is None


def test_a_missing_total_count_fails_rather_than_skipping_the_guard(monkeypatch):
    """`if total is not None and ...` meant the day the key moved — Gitea
    returns it in an X-Total-Count header on several list endpoints — the
    truncation assertion the docstring promises would stop running, silently.
    """
    monkeypatch.setattr(probe, "get",
                        lambda url, token: b'{"workflow_runs": []}')
    with pytest.raises(probe.Unreachable) as gone:
        probe.runs("token")
    assert "X-Total-Count" in str(gone.value), (
        "the failure must point at where the count probably moved to")




def test_the_suite_timing_refuses_to_pass_off_a_failed_run(monkeypatch):
    """A failing suite can stop early, and a run that died in collection takes
    no time at all — which would drop the floor to nothing and make "0 runs
    reached the floor" true by arithmetic rather than by measurement."""
    class Finished:
        returncode = 1
    monkeypatch.setattr(durations.subprocess, "run", lambda *a, **k: Finished())
    monkeypatch.delenv(durations.REENTRY, raising=False)
    timed = durations.time_the_suite()
    assert timed["measured"] is False
    assert "exited 1" in timed["why"]


def test_the_probe_cannot_fork_a_suite_from_inside_one(monkeypatch):
    """Without the guard, a test that called `measure()` would fork a suite
    that forks a suite."""
    monkeypatch.setenv(durations.REENTRY, "1")
    timed = durations.time_the_suite()
    assert timed["measured"] is False
    assert "re-entered" in timed["why"]


def test_the_history_is_paged_not_one_request(monkeypatch):
    """A single `?limit=250` WAS the whole history, so the probe hard-failed
    the day it passed 250, and the history was already past 200 when this was
    written. This instance returns every run
    when no `page` is given and honours `limit` only alongside it, which is
    exactly what hid the missing loop."""
    pages = {
        1: b'{"total_count": 5, "workflow_runs": ['
           b'{"id":1,"workflow_id":"ci.yml","status":"failure"},'
           b'{"id":2,"workflow_id":"ci.yml","status":"failure"}]}',
        2: b'{"total_count": 5, "workflow_runs": ['
           b'{"id":3,"workflow_id":"ci.yml","status":"failure"},'
           b'{"id":4,"workflow_id":"ci.yml","status":"failure"}]}',
        3: b'{"total_count": 5, "workflow_runs": ['
           b'{"id":5,"workflow_id":"ci.yml","status":"success"}]}',
    }
    asked = []

    def fake(url, token):
        page = int(url.split("page=")[1])
        asked.append(page)
        return pages[page]

    monkeypatch.setattr(probe, "get", fake)
    found = probe.runs("token")
    assert len(found) == 5, "the loop stopped before the history did"
    assert asked == [1, 2, 3], asked
    # The success on the LAST page is the point: a single-request probe would
    # have reported 0 successes over 2 runs and called it the whole history.
    assert sum(1 for r in found if r["status"] == "success") == 1


def test_a_pager_that_does_not_advance_is_stopped():
    """A server that ignores `page` would otherwise loop until the process is
    killed, accumulating the same batch."""
    seen = {"n": 0}

    def stuck(url, token):
        seen["n"] += 1
        # The SAME run every page — a server ignoring `page`. This is what the
        # duplicate-key stop catches; it used to loop to the 200-page cap.
        return (b'{"total_count": 999, "workflow_runs": ['
                b'{"id":1,"workflow_id":"a","status":"failure"}]}')

    import etl.probe_ci_history as mod
    old = mod.get
    mod.get = stuck
    try:
        with pytest.raises(probe.Unreachable, match="distinct"):
            probe.runs("token")
    finally:
        mod.get = old
    assert seen["n"] <= 3, (
        f"asked for {seen['n']} pages; a page with no NEW runs must stop the "
        f"loop rather than running to the cap")


def test_the_median_is_a_median():
    """It was `took[len // 2]` — the upper of the two middles — and called a
    median. The figure reaches a published table."""
    assert durations._median([7, 59, 60, 120]) == 59.5
    assert durations._median([7, 59, 60]) == 59.0
    assert durations._median([]) is None


def test_timestamps_are_compared_as_instants_not_strings():
    """String min/max is right for a uniform `…Z` format and silently wrong
    the moment a stamp carries an offset — the tolerance `_parse` exists for,
    contradicted two functions later."""
    # 10:30+05:30 is 05:00Z — EARLIER than 06:00Z, though it sorts later.
    found = [run(started="2026-09-01T06:00:00Z", updated="2026-09-01T06:00:07Z"),
             run(started="2026-09-01T10:30:00+05:30",
                 updated="2026-09-01T05:00:07+00:00")]
    tallied = probe.tally(found)["ci.yml"]
    assert tallied["first"] == "2026-09-01T10:30:00+05:30", (
        "the earlier instant lost to string comparison")


def test_a_non_string_stamp_does_not_raise_out_of_the_tally():
    """`seconds()` caught only ValueError, so a null or numeric stamp raised
    AttributeError/TypeError out of `tally` instead of being read as the
    unusable timestamp it is."""
    assert durations.seconds(None, "2026-09-01T05:00:07Z") is None
    assert durations.seconds(12345, "2026-09-01T05:00:07Z") is None
    probe.tally([{"workflow_id": "ci.yml", "status": "failure",
                  "run_started_at": None, "updated_at": 42}])








def test_the_median_sorts_what_it_is_given():
    """Deleting `sorted()` passed the ENTIRE suite, because all three median
    cases fed pre-sorted lists — and `tally` collects in API order, which is
    newest-first."""
    assert durations._median([120, 7, 60, 59]) == 59.5
    assert durations._median([9]) == 9.0
    assert durations._median([5, 5, 5, 5]) == 5.0


def test_a_run_whose_stamps_run_backwards_has_no_duration():
    """`updated_at` before `run_started_at` gave a negative, which flows into
    the median and can only pull `max_seconds` DOWN — making the floor
    argument look stronger than the data supports."""
    assert durations.seconds("2026-09-01T05:01:00Z",
                             "2026-09-01T05:00:00Z") is None


def test_the_cli_refuses_without_a_token(monkeypatch, capsys):
    monkeypatch.delenv("GITEA_TOKEN", raising=False)
    monkeypatch.delenv("SAMYAMA_GITEA_TOKEN", raising=False)
    assert probe.main([]) == 2
    assert "not public on a private repo" in capsys.readouterr().err


def test_the_cli_reports_an_unreachable_api(monkeypatch, capsys):
    monkeypatch.setenv("GITEA_TOKEN", "x")
    monkeypatch.setattr(probe, "measure",
                        lambda *a, **k: (_ for _ in ()).throw(
                            probe.Unreachable("the host said no")))
    assert probe.main([]) == 1
    assert "the host said no" in capsys.readouterr().err


def test_the_cli_refuses_to_record_a_measurement_with_no_workflows(
        monkeypatch, capsys, tmp_path):
    """**A zero-run measurement overwrote the committed record and exited 0.**

    The doc tests then errored at COLLECTION on a missing key, which reads as
    a broken test rather than a destroyed artifact — and by then it was gone.
    """
    monkeypatch.setenv("GITEA_TOKEN", "x")
    monkeypatch.setattr(probe, "measure", lambda *a, **k: {
        "workflows": {}, "runs_returned": 0, "dependencies": {},
        "verdict": {"floor_seconds": 60, "suite": {"seconds": 1},
                    "with_actions": None, "without_actions": None,
                    "in_history_but_not_committed": [],
                    "diagnostic_steps": 0, "diagnostic_tolerant_steps": 0,
                    "diagnostic_outcome_is_informative": False}})
    before = probe.RECORD.read_bytes()
    assert probe.main(["--record"]) == 4
    assert "refusing to --record" in capsys.readouterr().err
    assert probe.RECORD.read_bytes() == before, "the record was overwritten"


def test_the_cli_prints_json_without_writing(monkeypatch, capsys):
    """`--json` is what lets someone diff a fresh measurement against the
    committed record without touching the tree — 22 of 24 sibling probes have
    it."""
    monkeypatch.setenv("GITEA_TOKEN", "x")
    monkeypatch.setattr(probe, "measure", lambda *a, **k: {"workflows": {"a": 1}})
    before = probe.RECORD.read_bytes()
    assert probe.main(["--json"]) == 0
    assert '"workflows"' in capsys.readouterr().out
    assert probe.RECORD.read_bytes() == before


def test_report_says_so_when_no_diagnostic_is_committed(capsys):
    """It printed "0 of 0 diagnostic steps are continue-on-error" — a sentence
    about a file that does not exist."""
    probe.report({
        "runs_returned": 0, "workflows": {}, "dependencies": {},
        "verdict": {"floor_seconds": 60, "with_actions": None,
                    "without_actions": None,
                    "in_history_but_not_committed": [],
                    "diagnostic_steps": 0, "diagnostic_tolerant_steps": 0,
                    "diagnostic_outcome_is_informative": False}})
    printed = capsys.readouterr().out
    assert "no runner-diagnostic.yml is committed" in printed
    assert "0 of 0" not in printed


def test_the_cli_refuses_to_record_a_partial_measurement(monkeypatch, capsys):
    """**Not only an empty one.** The first guard was `not
    measured["workflows"]`, so a run returning `runner-diagnostic.yml` and no
    `ci.yml` overwrote the record and exited 0 — and the doc suite then died
    at COLLECTION on a missing key, which is the "reads as a broken test
    rather than a destroyed artifact" failure the guard exists to close.

    Reachable without malice: a token scoped to fewer workflows, a renamed
    `ci.yml`, or an API blip returning a partial-but-self-consistent page.
    """
    monkeypatch.setenv("GITEA_TOKEN", "x")
    monkeypatch.setattr(probe, "measure", lambda *a, **k: {
        "workflows": {"runner-diagnostic.yml": {
            "runs": 1, "success": 1, "failure": 0, "other": 0,
            "first": "2026-09-01T05:00:00Z", "last": "2026-09-01T05:00:00Z",
            "median_seconds": 5.0, "max_seconds": 5, "over_floor": 0,
            "timed": 1, "unfinished": 0, "untimed": 0}},
        "runs_returned": 1, "dependencies": {},
        "verdict": {"floor_seconds": 60, "suite": {"seconds": 1},
                    "with_actions": None, "without_actions": None,
                    "in_history_but_not_committed": [],
                    "diagnostic_steps": 0, "diagnostic_tolerant_steps": 0,
                    "diagnostic_outcome_is_informative": False}})
    before = probe.RECORD.read_bytes()
    assert probe.main(["--record"]) == 4
    said = capsys.readouterr().err
    assert "ci.yml" in said, "the refusal must name what would be lost"
    assert probe.RECORD.read_bytes() == before, "the record was overwritten"


def test_the_first_run_has_nothing_to_lose(tmp_path, monkeypatch):
    """A ratchet that refused when no record exists yet could never write
    one."""
    monkeypatch.setattr(probe, "RECORD", tmp_path / "absent.json")
    assert probe.lost_workflows({"workflows": {"a.yml": {}}}) == set()
    assert probe.lost_workflows({"workflows": {}}) == {"(any workflow at all)"}


def test_the_token_never_reaches_the_pytest_subprocess(monkeypatch):
    """**Both names.** The filter stripped SAMYAMA_GITEA_TOKEN while
    `gitea_token()` reads GITEA_TOKEN first, so the ordinary path handed the
    credential straight through. They come from one tuple now."""
    seen = {}

    class Finished:
        returncode = 0

    def fake_run(command, **kwargs):
        seen.update(kwargs.get("env") or {})
        return Finished()

    for name in durations.TOKEN_NAMES:
        monkeypatch.setenv(name, "LEAKY")
    monkeypatch.delenv(durations.REENTRY, raising=False)
    monkeypatch.setattr(durations.subprocess, "run", fake_run)
    durations.time_the_suite()

    leaked = [n for n in durations.TOKEN_NAMES if n in seen]
    assert not leaked, f"{leaked} reached the subprocess"
    assert seen.get(durations.REENTRY) == "1", "the re-entry guard was dropped"

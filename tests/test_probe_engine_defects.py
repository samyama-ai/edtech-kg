"""The defect probe's verdicts, driven without an engine.

Every `still_defective` here is a boolean that decides whether an engine
upgrade is reported as a fix or passes unnoticed, so the arithmetic behind
each one is checked against fabricated readings rather than against whatever
the local engine happens to do today.
"""

from __future__ import annotations

import pytest

from etl.engine import Refused
from etl import engine_bench as bench
from etl import probe_engine_defects as probe
from etl import scratch_engine as guard


class Fake:
    """An engine that answers from a script, and records what it was asked."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.asked = []

    def run(self, cypher):
        self.asked.append(cypher)
        return self.answers.pop(0) if self.answers else {"records": []}


def test_a_bare_aggregate_row_is_not_read_as_a_value():
    """The engine returns one row over an empty graph, so `records != []` is
    not an emptiness check. `scalar` must read the cell, not count the row."""
    assert probe.scalar(Fake([{"records": [[None]]}]), "q") is None
    assert probe.scalar(Fake([{"records": []}]), "q") is None
    assert probe.scalar(Fake([{"records": [[7]]}]), "q") == 7


def test_merge_degrading_alone_is_not_the_finding():
    """MERGE slowing while MATCH slows too is a slow engine, not this bug.
    The verdict requires MERGE to fall and MATCH to hold."""
    def points(first_merge, last_merge, first_match, last_match):
        return [{"nodes_at_start": 1000, "nodes_at_end": 1360, "merge_per_sec": first_merge,
                 "create_per_sec": 800.0, "match_per_sec": first_match},
                {"nodes_at_start": 16000, "nodes_at_end": 16360, "merge_per_sec": last_merge,
                 "create_per_sec": 800.0, "match_per_sec": last_match}]

    # THE PROBE'S OWN function, not a copy of its rule. The first version of
    # this test reimplemented the verdict and so agreed with itself whatever
    # the probe did.
    verdict = bench.merge_is_still_defective

    # The real shape: MERGE collapses, MATCH holds.
    assert verdict(points(640.0, 68.0, 750.0, 740.0)) is True
    # Everything slowed — a loaded machine, not an ignored index.
    assert verdict(points(640.0, 68.0, 750.0, 90.0)) is False
    # MERGE held — the defect is fixed and must be reported as fixed.
    assert verdict(points(640.0, 600.0, 750.0, 740.0)) is False
    # And no points at all is not evidence of a defect.
    assert verdict([]) is False


def test_the_probe_refuses_a_loaded_engine(monkeypatch):
    """It writes tens of thousands of nodes and cannot remove them — that
    inability is one of the defects. Running against a loaded graph corrupts
    it, which is how :8200 came to hold four copies of one district."""
    # **The real guard runs.** Stubbing `refuse_unless_scratch` here would
    # test the stub's message, which is how a guard passes its own test while
    # doing nothing.
    monkeypatch.setattr(guard, "api",
                        lambda url, path, *a, **k:
                        (200, {"storage": {"nodes": 4392}, "version": "1.7.0"}))
    monkeypatch.setattr(guard, "Engine", lambda url: Engine(0))
    monkeypatch.setattr(probe, "api",
                        lambda url, path, *a, **k:
                        (200, {"storage": {"nodes": 4392}, "version": "1.7.0"}))
    with pytest.raises(guard.Unusable) as refused:
        probe.measure("http://localhost:9999")
    assert "4392" in str(refused.value)
    assert "did not write" in str(refused.value)
    assert "scratch" in str(refused.value)


def test_a_graph_holding_only_a_previous_run_is_cleared_not_refused(monkeypatch):
    """The probe wrote ~33,000 nodes and then refused to start against them,
    so re-measuring meant destroying the container. Zero left after clearing
    its own labels means the graph was its own last run."""
    held = iter([33000, 0])
    monkeypatch.setattr(guard, "api",
                        lambda url, path, *a, **k:
                        (200, {"storage": {"nodes": next(held, 0)},
                               "version": "1.7.0"}))
    monkeypatch.setattr(guard, "Engine", lambda url: Engine(0))
    monkeypatch.setattr(probe, "api",
                        lambda url, path, *a, **k:
                        (200, {"storage": {"nodes": 0}, "version": "1.7.0"}))
    monkeypatch.setattr(probe, "remove_is_a_no_op", lambda e: {"ok": 1})
    monkeypatch.setattr(probe, "tenant_is_ignored", lambda u, e: {"ok": 1})
    monkeypatch.setattr(probe, "merge_ignores_the_index",
                        lambda e, sizes, repeats: {"ok": 1})
    measured = probe.measure("http://localhost:9999")
    assert measured["remove"] == {"ok": 1}, "the run was refused"


def test_an_engine_that_does_not_answer_status_is_refused(monkeypatch):
    monkeypatch.setattr(guard, "api", lambda *a, **k: (503, None))
    with pytest.raises(guard.Unusable):
        probe.measure("http://localhost:9999")


def test_a_tenant_api_that_stops_accepting_the_call_stops_the_run(monkeypatch):
    """The probe's own worst failure mode, guarded.

    Its first version sent only `id`, got a 422, and would have recorded the
    API as REFUSING these calls — reporting #149 as absent when it is
    present. A status other than 201 now stops the run rather than being
    stored as a finding.
    """
    monkeypatch.setattr(probe, "api",
                        lambda url, path, method="GET", payload=None:
                        (422, None) if path == "/api/tenants" else (200, None))
    with pytest.raises(guard.Unusable) as refused:
        probe.tenant_is_ignored("http://localhost:9999",
                                Fake([{"records": [[1]]}] * 8))
    assert "422" in str(refused.value)
    assert "re-recording" in str(refused.value)


def test_the_warmup_is_not_inside_the_timing():
    """At a batch of 40 with no warm-up, MERGE measured FASTER at 2,000 nodes
    than at 500 — the opposite of the finding, because the first call of a
    statement shape pays for parsing and planning that none of the rest do."""
    engine = Fake([{"records": []}] * (bench.WARMUP + 5))
    bench.rate(engine, lambda i: f"CREATE (n {{i: {i}}})", 5)
    assert len(engine.asked) == bench.WARMUP + 5, (
        "the warm-up must run, and must not be counted in the batch")
    assert bench.WARMUP > 0 and bench.BATCH >= 100, (
        "a batch this small is dominated by warm-up; 40 gave a non-monotonic "
        "table that reversed the finding")


def test_the_verdict_does_not_require_the_row_to_have_lost_the_key():
    """**The case #163 originally described must not report FIXED.**

    Requiring `row_no_longer_holds_it` did exactly that: an engine where the
    row keeps the property and every read is stale — the issue's own wording —
    came out as fixed. That is the milder version of this defect and it is
    still the defect. What the row did is a refinement recorded beside the
    finding, not a gate on it.
    """
    before = {"projection": "keep", "count_by_value": 1,
              "row_has_the_key": True, "row_value": "keep"}

    # The issue's original claim: nothing changed anywhere.
    unchanged = dict(before)
    assert probe.reads_disagree_with_the_row(before, unchanged) is True

    # What 1.1.0 actually does: the row loses the key, the reads do not.
    row_cleared = {"projection": "keep", "count_by_value": 1,
                   "row_has_the_key": False, "row_value": None}
    assert probe.reads_disagree_with_the_row(before, row_cleared) is True

    # Genuinely fixed: the reads follow the write.
    fixed = {"projection": None, "count_by_value": 0,
             "row_has_the_key": False, "row_value": None}
    assert probe.reads_disagree_with_the_row(before, fixed) is False


def test_a_probe_run_can_follow_another_on_the_same_engine():
    """It wrote ~33,000 nodes and then refused to start against them, so
    re-measuring meant destroying the container. Its own labels are cleared;
    anything else is still refused."""
    assert probe.LABEL in probe.OUR_LABELS
    assert all(lbl for lbl in probe.OUR_LABELS), "an unnamed label survives a reset"


def test_a_ratio_with_an_unmeasured_end_is_none_not_zero():
    """`rate()` returns 0.0 when the clock reports no elapsed time. Only the
    denominator was guarded, so a 0.0 numerator gave `merge_fell_by: 0.0` — a
    number that reads as "it did not fall" and means "nothing was measured"."""
    assert bench.ratio(0.0, 500.0) is None
    assert bench.ratio(500.0, 0.0) is None
    assert bench.ratio(640.0, 80.0) == 8.0


def test_the_fresh_label_control_is_declared_too(monkeypatch):
    """Without the constraint the "identical MERGE" differed in two variables
    — label size AND index presence — so a fast result could mean either. It
    is an isolating control only if the one difference is label size."""
    import inspect
    source = inspect.getsource(bench.merge_ignores_the_index)
    assert "declare_constraint(engine, f\"{LABEL}Fresh\")" in source, (
        "the fresh control label is measured without a uniqueness constraint")


def test_a_refused_constraint_is_recorded_rather_than_swallowed():
    """The old `except Refused: pass` carried a comment saying it was
    "recorded, not swallowed", and nothing was written and no field existed."""
    class Refuses:
        def run(self, cypher):
            raise Refused(400, "constraint already declared")

    said = bench.declare_constraint(Refuses(), "X")
    assert said.startswith("refused: "), said

    class Accepts:
        def run(self, cypher):
            return {"records": []}

    assert bench.declare_constraint(Accepts(), "X") == "declared"


class Api:
    """/api/tenants and /api/query, scripted, with a scriptable query status."""

    def __init__(self, count=1, query_status=200, create=201):
        self.count, self.query_status, self.create = count, query_status, create
        self.bodies = []

    def __call__(self, url, path, method="GET", body=None):
        if path == "/api/status":
            return 200, {"storage": {"nodes": 0}}
        if path.startswith("/api/tenants"):
            return (self.create if method == "POST" else 200), {}
        self.bodies.append(body)
        if self.query_status != 200:
            return self.query_status, {}
        return 200, {"records": [[self.count]]}


class Engine:
    def __init__(self, count=1):
        self.count = count

    def run(self, cypher):
        return {"records": [[self.count]]}


def test_the_query_statuses_are_recorded_beside_the_counts(monkeypatch):
    """A count of None means "refused" or "zero" and the record could not say
    which."""
    monkeypatch.setattr(probe, "api", Api())
    found = probe.tenant_is_ignored("http://engine.test", Engine())
    assert set(found["query_status_by_tenant"]) == {
        "default", "probe-scratch", "nonexistent-tenant-xyz"}
    assert all(s == 200 for s in found["query_status_by_tenant"].values())


def test_a_nonsense_field_is_the_control_for_tenant_being_ignored(monkeypatch):
    """**Blocker 3. `still_defective` could not report anything else.**

    A field named `zzz_not_a_field` produces a byte-identical response: the
    engine discards unknown body fields wholesale, and `etl/engine.py` already
    records that /api/query accepts only `query` and `graph`. So "tenant is
    ignored" read true forever — including on an engine with perfect
    isolation. Unfalsifiable, and contradicting a fact this repo has measured.

    With the control, the finding sharpens into the better-supported claim:
    there is no `tenant` parameter on /api/query at all.
    """
    api = Api()
    monkeypatch.setattr(probe, "api", api)
    found = probe.tenant_is_ignored("http://engine.test", Engine())
    assert any("zzz_not_a_field" in (b or {}) for b in api.bodies), (
        "no null control was sent, so 'tenant is ignored' cannot be told "
        "from 'tenant is not a parameter'")
    assert found["unknown_body_fields_are_discarded"] is True
    assert found["reads_as_no_tenant_parameter"] is True


def test_a_rate_is_the_median_of_its_repeats():
    """**One draw put the #169 verdict inside its own noise band.** On a live
    1.1.0: MERGE fell 8.0x and MATCH fell 1.9x, against a rule requiring MATCH
    to fall under 2.0x — a 5% margin, unrepeated, on an idle laptop. On a
    busier machine it flips and the probe reports #169 FIXED, which is the one
    outcome it exists never to produce.

    A median rather than a mean: the failure mode is a single slow draw from
    something else on the machine, and a mean carries it.
    """
    from etl import engine_bench

    draws = iter([100.0, 5.0, 110.0])   # the middle one is the interloper

    class Clocked:
        def run(self, cypher):
            return {"records": []}

    calls = []
    original = engine_bench.rate
    try:
        engine_bench.rate = lambda e, s, c: (calls.append(1), next(draws))[1]
        assert engine_bench.repeated(Clocked(), lambda i: "x", 1, 3) == 100.0
    finally:
        engine_bench.rate = original
    assert len(calls) == 3, "the rate was not measured three times"


def test_record_measures_each_rate_more_than_once(monkeypatch):
    """A record is what a page quotes. `--record` takes three unless told
    otherwise; a quick look may take one."""
    seen = {}
    monkeypatch.setattr(probe, "measure",
                        lambda url, full, image, repeats: seen.update(
                            repeats=repeats) or {"remove": {}, "tenant": {},
                                                 "merge": {}})
    monkeypatch.setattr(probe, "write_record", lambda path, payload: None)
    monkeypatch.setattr(probe, "report", lambda measured: None)
    probe.main(["--record"])
    assert seen["repeats"] == 3, seen
    seen.clear()
    probe.main([])
    assert seen["repeats"] == 1, seen
    seen.clear()
    probe.main(["--repeats", "5"])
    assert seen["repeats"] == 5, seen


def test_the_help_warns_that_a_run_leaves_the_graph_populated():
    """`--help` printed only "A SCRATCH engine. It will be written to", which
    reads as ordinary write access. Measured: 16,542 nodes remain afterwards
    and the engine cannot remove them — that inability is one of the three
    defects. The difference decides whether a `--url` typo is recoverable."""
    import contextlib
    import io

    out = io.StringIO()
    with contextlib.redirect_stdout(out), pytest.raises(SystemExit):
        probe.main(["--help"])
    printed = out.getvalue()
    assert "LEAVES THE GRAPH POPULATED" in printed, printed
    assert "cannot remove them" in printed


def test_a_record_is_refused_against_another_build(monkeypatch, capsys):
    """Rewriting `engine_version_reported` to `9.9.9-someone-elses-build` and
    `image_asserted` to a foreign registry left the whole suite green — so a
    record could describe an engine this repo has never measured while every
    figure in it read as 1.1.0's.

    `probe_engine_capability.py` already refuses that and pins it in its doc
    test; the same rule belongs here.
    """
    written = []
    monkeypatch.setattr(probe, "write_record",
                        lambda path, payload: written.append(payload))
    monkeypatch.setattr(probe, "report", lambda measured: None)

    monkeypatch.setattr(probe, "measure", lambda url, full, image, repeats: {
        "engine_version_reported": "9.9.9-someone-elses-build",
        "image_asserted": probe.DEFAULT_IMAGE})
    assert probe.main(["--record"]) == 4
    assert "9.9.9" in capsys.readouterr().err
    assert not written

    monkeypatch.setattr(probe, "measure", lambda url, full, image, repeats: {
        "engine_version_reported": probe.ENGINE_VERSION,
        "image_asserted": "registry.example.test/somebody/else:latest"})
    assert probe.main(["--record"]) == 4
    assert not written, "a record was written against an unpinned image"

    monkeypatch.setattr(probe, "measure", lambda url, full, image, repeats: {
        "engine_version_reported": probe.ENGINE_VERSION,
        "image_asserted": probe.DEFAULT_IMAGE})
    assert probe.main(["--record"]) == 0
    assert written, "the pinned build was refused"


def test_a_leaked_tenant_is_deleted_and_retried_not_blamed_on_the_engine(
        monkeypatch):
    """An interrupted run leaks `probe-scratch`, and the next run's 409 hit
    the refusal — which tells the operator that #149 "needs re-stating, not
    re-recording", sending them to rewrite an issue when the cause is their
    own half-finished run."""
    calls = []

    def api(url, path, method="GET", body=None):
        calls.append((method, path))
        if path.startswith("/api/tenants") and method == "POST":
            return (409 if len([c for c in calls
                                if c == ("POST", "/api/tenants")]) == 1
                    else 201), {}
        if path.startswith("/api/tenants"):
            return 204, {}
        return 200, {"records": [[1]]}

    monkeypatch.setattr(probe, "api", api)
    found = probe.tenant_is_ignored("http://engine.test", Engine())
    assert found["create_status"] == 201, found
    assert ("DELETE", "/api/tenants/probe-scratch") in calls, (
        "the leftover tenant was not deleted before retrying")


def test_a_refused_query_is_not_read_as_the_defect_being_fixed(monkeypatch):
    """**Blocker 4.** The 422 guard covered the tenant CREATE and stopped one
    call short: `status` was unpacked from the query calls and never checked.

    Driven with /api/tenants at 201 and /api/query at 400, all three counts
    came back None, `len(seen) == 1` held, and the probe reported #149 FIXED —
    the same false-absence the guard exists for, one call along, with nothing
    in the record to reveal it.
    """
    monkeypatch.setattr(probe, "api", Api(query_status=400))
    with pytest.raises(guard.Unusable, match="refused"):
        probe.tenant_is_ignored("http://engine.test", Engine())

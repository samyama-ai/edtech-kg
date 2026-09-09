"""The guard that decides whether an engine is safe to write to.

Split from `tests/test_probe_engine_defects.py` at the 500-line review limit,
and split by SUBJECT the way the modules already are: that file asks what the
engine answers WRONGLY, this one asks whether it is somebody else's graph.
They fail differently — a wrong measurement is a wrong number, and a wrong
decision here is somebody's loaded graph.

**This guard has failed open twice**, both times with something unmeasurable
reading as "empty" rather than as "unknown". Every test below is one of those.
"""

from __future__ import annotations

import pytest

from etl import probe_engine_defects as probe
from etl import scratch_engine as guard


class Status:
    """An /api/status the guard can be driven against."""

    def __init__(self, payload, code=200):
        self.payload, self.code = payload, code

    def __call__(self, url, path, method="GET", body=None):
        if path == "/api/status":
            return self.code, self.payload
        return 200, {"records": [[0]]}


def test_a_status_without_a_node_count_refuses_rather_than_reads_as_empty(
        monkeypatch):
    """**Blocker 1. The guard failed open.** A 200 at /api/status carrying no
    `storage.nodes` key left `nodes` as None, so the whole `if nodes:` block
    was skipped and the probe wrote ~16,400 unremovable nodes into whatever it
    was pointed at.

    This is the guard between a `--url` typo and the :8200 accident the probe
    exists because of. `probe_engine_capability.py` raises for a missing
    version rather than recording "unknown"; the same rule belongs here.
    """
    monkeypatch.setattr(guard, "api", Status({"storage": {}}))
    with pytest.raises(guard.Unusable, match="storage.nodes"):
        probe.measure("http://engine.test")
    monkeypatch.setattr(guard, "api", Status({}))
    with pytest.raises(guard.Unusable, match="storage.nodes"):
        probe.measure("http://engine.test")


def test_an_unmeasurable_cleanup_refuses_rather_than_reports_empty(monkeypatch):
    """**Blocker 1, the other half.** `clear_our_own` ended
    `return scalar(...) or 0`, so "I could not measure this" became "the graph
    is empty" — and with `storage.nodes` at 50,000 the probe proceeded."""
    monkeypatch.setattr(guard, "api", Status({"storage": {}}, code=500))
    with pytest.raises(guard.Unusable):
        guard.still_held("http://engine.test")


def test_the_refusal_rests_on_an_instance_wide_count(monkeypatch):
    """**Blocker 2. The guard's safety depended on a defect holding still.**
    The leftover count ran under `graph="default"` while this repo loads its
    district under `graph="edtech"`. It saw that data only because graph
    scoping does not work — the same class of defect this probe measures for
    `tenant`. An engine build that FIXED scoping would report an empty default
    on a loaded instance and let the probe run.

    `/api/status` is instance-wide, so the decision no longer rests on the
    defect it is measuring.
    """
    asked = []

    def api(url, path, method="GET", body=None):
        asked.append((path, (body or {}).get("graph")))
        return 200, {"storage": {"nodes": 50_000}}

    monkeypatch.setattr(guard, "api", api)
    assert guard.still_held("http://engine.test") == 50_000
    assert asked == [("/api/status", None)], (
        "the count went through a graph-scoped query, which is the defect "
        "this probe measures")


def test_a_non_numeric_node_count_refuses_rather_than_crashes(monkeypatch):
    """`int(held)` raised an uncaught ValueError on
    `{"storage": {"nodes": "many"}}`, so the probe exited 1 with a traceback
    instead of 2 with a refusal.

    A traceback out of a safety guard reads as a bug in the probe rather than
    as "this engine is not safe to write to" — and the difference decides
    whether the operator points it somewhere else or reports it as broken.
    """
    monkeypatch.setattr(guard, "api", Status({"storage": {"nodes": "many"}}))
    with pytest.raises(guard.Unusable, match="not a count"):
        guard.still_held("http://engine.test")


def test_a_foreign_engine_is_refused_before_anything_is_deleted(monkeypatch):
    """Whenever the count was truthy the probe issued three `DETACH DELETE`
    statements and only THEN decided whether to refuse — so on a foreign
    loaded instance it wrote first and declined afterwards.

    They touch only this probe's own labels, so the risk was small. "Refuse
    without touching it" is the stronger property and costs one reordering.
    """
    written = []

    class Watched:
        def run(self, cypher):
            written.append(cypher)
            return {"records": [[0]]}

    monkeypatch.setattr(guard, "Engine", lambda url: Watched())
    monkeypatch.setattr(guard, "api", Status({"storage": {"nodes": 0}}))
    guard.refuse_unless_scratch("http://engine.test", ("A", "B"))
    assert written == [], "an empty engine was written to before the decision"

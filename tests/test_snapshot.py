"""The snapshot, and the counts an import has to reproduce.

edtech-kg#25. A demo that begins with a load begins with ten minutes of
nothing; a snapshot makes it seconds. What makes that safe is the check
afterwards, and the check is the part with a trap in it.

**`/api/status` IS THE WRONG PLACE TO READ EDGE COUNTS**, and it is the
obvious place. Measured on 1.1.0, two engines side by side holding the same
graph — one built by Cypher `CREATE`, one imported from the snapshot taken
from it:

    /api/status edges     Cypher-loaded 2,834      imported 1,417
    per-type Cypher       both 1,417 (240 + 723 + 316 + 138)

So a verification that trusted `/api/status` would call a correct import a
failure, or a half-imported graph a success, depending on which side it read.
Everything here counts per type.

Nothing in this file needs an engine except the round trip, which is gated.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from etl import snapshot
from etl.snapshot import EDGE_TYPES, NODE_LABELS, Refused

ROOT = pathlib.Path(__file__).resolve().parents[1]
RECORD = ROOT / "docs" / "sources" / "snapshot-measured.json"


class Graph:
    """An engine answering fixed counts, so `counts` can be driven."""

    def __init__(self, held=None):
        self.held = held or {}
        self.asked = []

    def run(self, statement):
        self.asked.append(statement)
        for name, n in self.held.items():
            if f":{name})" in statement or f":{name}]" in statement:
                return {"records": [[n]]}
        return {"records": [[0]]}


def test_counts_never_ask_api_status():
    """**The trap.** `/api/status` reports 2,834 edges for a graph holding
    1,417 when that graph was built by Cypher, and 1,417 for the same graph
    imported from a snapshot. Either number is right about something; neither
    is right about both, so the check cannot use it.
    """
    engine = Graph({"Course": 791, "REQUIRES": 240})
    snapshot.counts(engine)
    assert engine.asked, "counts asked the engine nothing"
    for statement in engine.asked:
        assert "status" not in statement.lower()
        assert statement.startswith("MATCH"), statement


def test_every_label_and_edge_type_is_counted_separately():
    """A total can be right while two types are wrong in opposite
    directions. The record stores the shape, not the sum."""
    engine = Graph()
    held = snapshot.counts(engine)
    assert set(held) == set(NODE_LABELS) | set(EDGE_TYPES)


def test_verify_names_what_disagrees_rather_than_saying_no():
    """A demo that will not open needs to say which part of the graph is
    missing — "verification failed" sends someone to re-import blind."""
    engine = Graph({"Course": 791, "REQUIRES": 100})
    original, snapshot.Engine = snapshot.Engine, lambda url: engine
    try:
        problems = snapshot.verify("http://engine.test",
                                   {"Course": 791, "REQUIRES": 240})
    finally:
        snapshot.Engine = original
    assert len(problems) == 1
    assert "REQUIRES" in problems[0] and "240" in problems[0] and "100" in problems[0]


def test_exporting_an_empty_graph_is_refused(monkeypatch):
    """**An empty snapshot published as a demo is the worst artefact here.**
    It imports in no time, verifies against nothing, and shows a blank graph
    in front of a customer."""
    monkeypatch.setattr(snapshot, "Engine", lambda url: Graph())
    with pytest.raises(Refused, match="holds nothing"):
        snapshot.export("http://engine.test", ROOT / "data" / "unused.sgsnap")


def test_importing_into_a_loaded_engine_is_refused(monkeypatch, tmp_path):
    """It merges rather than replaces, so the result is neither graph."""
    monkeypatch.setattr(snapshot, "Engine",
                        lambda url: Graph({"Course": 791}))
    target = tmp_path / "x.sgsnap"
    target.write_bytes(b"not really a snapshot")
    with pytest.raises(Refused, match="already holds"):
        snapshot.load("http://engine.test", target)


def test_the_snapshot_is_not_committed():
    """`data/` is gitignored and this ships as a release asset. A graph
    artefact is not source, and #6's house rule is that no raw data can be
    committed by accident."""
    import subprocess
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT,
                             capture_output=True, text=True).stdout
    assert ".sgsnap" not in tracked, "a snapshot is committed"


def test_the_record_says_what_an_import_must_reproduce():
    if not RECORD.exists():
        pytest.skip("no committed record yet")
    found = json.loads(RECORD.read_text(encoding="utf-8"))
    for name in NODE_LABELS + EDGE_TYPES:
        assert name in found["counts"], f"{name} is not in the record"
    assert found["import"]["in_graph"] == found["counts"], (
        "the recorded import did not reproduce the graph it was taken from")
    assert found["snapshot"]["bytes"] > 0
    assert found["code"]["dirty"] is False

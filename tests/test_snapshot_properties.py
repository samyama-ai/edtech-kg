"""What the nodes CARRY, held to the snapshot that produced them.

Split out of `tests/test_snapshot.py` at the 500-line review limit, by
SUBJECT: that file drives the round trip — export, import, hashes, refusals —
and this one drives the question that round trip cannot answer by counting.

**Cardinality is not content.** A snapshot reproducing every node and every
edge and dropping every property verified clean, and `demo/ready.sh` runs
`verify` as its gate. Worse, the expectation was first measured on the
IMPORTED graph, so an engine that dropped values would have had
`Course.name: 0` written into the record as the published expectation — the
check certifying the state it exists to detect.
"""

from __future__ import annotations

import json
import pathlib

from etl import snapshot
from tests.graph_stub import Graph

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_a_graph_of_nameless_nodes_does_not_verify(monkeypatch):
    """**Cardinality is not content.** `verify` compared counts per label and
    per edge type only, so a snapshot that reproduced every node and every
    edge and dropped every PROPERTY passed — and `demo/ready.sh` runs this as
    its gate, so it stands between a bad import and a customer-facing
    walkthrough.

    Worse than it sounds: `etl/engine.py:208-220` records that properties are
    effectively unremovable on 1.1.0, so a graph in this state cannot be
    repaired in place. It has to be rebuilt.
    """
    class Nameless(Graph):
        def scalar(self, statement):
            if "IS NOT NULL" in statement:
                return 0                      # nodes arrived, values did not
            return super().scalar(statement)

    monkeypatch.setattr(snapshot, "Engine", lambda url, graph=None: Nameless(
        {"Course": 791, "Subject": 127, "Pathway": 42, "Requirement": 138}))
    counts = {"Course": 791, "Subject": 127, "Pathway": 42, "Requirement": 138}
    props = {"Course.name": 791, "Subject.name": 127,
             "Pathway.name": 42, "Requirement.text": 138}

    assert verify_ok(counts), "the counts alone should still agree"
    wrong = snapshot.verify("http://engine.test", counts,
                            expect_properties=props)
    assert wrong, "a graph carrying no property values verified clean"
    assert any("the values did not" in line for line in wrong), wrong
    assert len(wrong) == len(props), (
        f"only {len(wrong)} of {len(props)} missing properties were named")


def verify_ok(counts):
    return not snapshot.verify("http://engine.test", counts)


def test_properties_are_counted_per_label_and_key(monkeypatch):
    """Named per label and property, so a report says WHICH values are gone
    rather than that something is."""
    engine = Graph({"Course": 791, "Subject": 127, "Pathway": 42,
                    "Requirement": 138})
    held = snapshot.properties(engine)
    assert set(held) == {f"{label}.{prop}"
                         for label, prop in snapshot.REQUIRED_PROPERTIES}
    for statement in engine.asked:
        assert "IS NOT NULL" in statement, statement


def test_a_record_written_before_property_counts_still_verifies_clean(
        monkeypatch):
    """An older record carries no `property_counts`. That is a record without
    the MEASUREMENT, not a graph without the values, so it must not read as
    every property missing.

    Driven rather than asserted on the signature: `verify.__defaults__[-1] is
    None` passed on any unrelated trailing keyword and failed on a refactor
    that changed nothing observable, and it never exercised the claim.
    """
    class Nameless(Graph):
        def scalar(self, statement):
            if "IS NOT NULL" in statement:
                return 0
            return super().scalar(statement)

    monkeypatch.setattr(snapshot, "Engine", lambda url, graph=None: Nameless(
        {"Course": 791}))
    # No `expect_properties` — the shape an old record produces.
    assert snapshot.verify("http://engine.test", {"Course": 791}) == []


def test_record_refuses_a_round_trip_that_drops_property_values(
        monkeypatch, tmp_path, capsys):
    """**The check could certify the state it exists to detect.**
    `property_counts` was measured on the IMPORTED graph while every other
    figure came from the source, and the round-trip gate compared counts
    only. So against an engine whose import dropped values, `record` passed,
    promoted the candidate to `data/edtech-kg.sgsnap`, and wrote
    `Course.name: 0` into the record as the published expectation — after
    which every `demo/ready.sh` verified the nameless graph as clean.

    Now the properties come from the source and gate the round trip.
    """
    target = tmp_path / "x.sgsnap"
    record = tmp_path / "snapshot-measured.json"
    monkeypatch.setattr(snapshot, "RECORD", record)
    monkeypatch.setattr(snapshot, "export", lambda url, into, graph=None: (
        into.write_bytes(b"snapshot"),
        {"file": "data/x.sgsnap", "bytes": 8, "sha256": "beef",
         "taken_from": {"Course": 791},
         "properties": {"Course.name": 791}})[1])   # the SOURCE carried them
    monkeypatch.setattr(snapshot, "reproducibility",
                        lambda url, times=3: {"byte_identical": False})
    monkeypatch.setattr(snapshot, "load", lambda url, path, graph=None,
                        expect_sha256=None: {"seconds": 0.02, "bytes": 8,
                                             "engine_said": {},
                                             "in_graph": {"Course": 791}})

    class Nameless(Graph):
        """The import kept every node and dropped every value."""
        def scalar(self, statement):
            if "IS NOT NULL" in statement:
                return 0
            return super().scalar(statement)

    monkeypatch.setattr(snapshot, "Engine",
                        lambda url, graph=None: Nameless({"Course": 791}))
    assert snapshot.main(["record", "--file", str(target),
                          "--url", "http://a.test",
                          "--from-url", "http://b.test"]) == 4
    said = capsys.readouterr().err
    assert "the values did not" in said, said
    assert not record.exists(), (
        "a round trip that dropped every property value was recorded")
    assert not target.exists(), (
        "the lossy snapshot was promoted to the path ready.sh imports")


def test_export_records_the_properties_the_SOURCE_carried(monkeypatch,
                                                          tmp_path):
    """Measured on the engine being exported FROM, beside `taken_from`.
    Every other figure in the record comes from the source; this one came
    from the freshly imported graph, which is what made the expectation
    self-fulfilling."""
    asked = []

    class Source(Graph):
        def scalar(self, statement):
            asked.append(statement)
            if "IS NOT NULL" in statement:
                return 791
            return super().scalar(statement)

    monkeypatch.setattr(snapshot, "Engine",
                        lambda url, graph=None: Source({"Course": 791}))
    monkeypatch.setattr(snapshot, "post", lambda *a, **k: (200, b"bytes"))
    taken = snapshot.export("http://source.test", tmp_path / "x.sgsnap")
    assert taken["properties"], "export recorded no property counts"
    assert taken["properties"]["Course.name"] == 791
    assert any("IS NOT NULL" in q for q in asked), (
        "export never asked the source what its nodes carry")


def test_import_checks_the_recorded_properties(monkeypatch, tmp_path,
                                               capsys):
    """`demo/ready.sh` runs `import` then `verify`. The import action reads
    the record itself, so it has to make the same check — otherwise a lossy
    import is only caught one command later, after it has already merged."""
    record = tmp_path / "snapshot-measured.json"
    record.write_text(json.dumps({
        "counts": {"Course": 791},
        "property_counts": {"Course.name": 791},
        "snapshot": {"sha256": None}}), encoding="utf-8")
    monkeypatch.setattr(snapshot, "RECORD", record)
    monkeypatch.setattr(snapshot, "load", lambda url, path, graph=None,
                        expect_sha256=None: {"seconds": 0.02, "bytes": 8,
                                             "engine_said": {},
                                             "in_graph": {"Course": 791}})

    class Nameless(Graph):
        def scalar(self, statement):
            if "IS NOT NULL" in statement:
                return 0
            return super().scalar(statement)

    monkeypatch.setattr(snapshot, "Engine",
                        lambda url, graph=None: Nameless({"Course": 791}))
    target = tmp_path / "x.sgsnap"
    target.write_bytes(b"snapshot")
    assert snapshot.main(["import", "--file", str(target),
                          "--url", "http://engine.test"]) == 4
    assert "the values did not" in capsys.readouterr().err


def test_the_key_properties_match_the_ones_the_loader_checks():
    """`REQUIRED_PROPERTIES` and the pair list in `etl/load_pwcs.py:427-428`
    are the same decision made twice — what a node is worthless without.

    Not merged into one import: the loader is core and this module is demo
    tooling, so importing this into `load_pwcs` points the dependency the
    wrong way. Pinned instead, so they cannot drift apart silently.
    """
    import re
    loader = (ROOT / "etl" / "load_pwcs.py").read_text(encoding="utf-8")
    block = re.search(r"for label, prop in \((.*?)\):", loader, re.S)
    assert block, "the loader's property check has moved; re-point this test"
    theirs = set(re.findall(r'\("(\w+)", "(\w+)"\)', block.group(1)))
    assert theirs == set(snapshot.REQUIRED_PROPERTIES), (
        f"etl/load_pwcs.py checks {sorted(theirs)} and etl/snapshot.py "
        f"checks {sorted(snapshot.REQUIRED_PROPERTIES)} — the same decision, "
        f"drifted")

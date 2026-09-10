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

Nothing here needs an engine: every test drives a stub. There is no
engine-backed round trip in this file — an earlier version of this line
said there was one and gated, and there was neither.
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
    """An engine answering fixed counts, so `counts` can be driven.

    `scalar` as well as `run`: `counts` reads through `Engine.scalar` now, so
    that "I could not measure this" and "the graph holds none of these" stay
    apart — the pre-import guard is built on it.
    """

    def __init__(self, held=None, url="http://engine.test"):
        self.held = held or {}
        self.asked = []
        self.url = url

    def run(self, statement):
        self.asked.append(statement)
        for name, n in self.held.items():
            if f":{name})" in statement or f":{name}]" in statement:
                return {"records": [[n]]}
        return {"records": [[0]]}

    def scalar(self, statement):
        rows = self.run(statement).get("records") or []
        return rows[0][0] if rows and rows[0] else None


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
    original, snapshot.Engine = snapshot.Engine, lambda url, graph=None: engine
    try:
        problems = snapshot.verify("http://engine.test",
                                   {"Course": 791, "REQUIRES": 240})
    finally:
        snapshot.Engine = original
    assert len(problems) == 1
    assert "REQUIRES" in problems[0] and "240" in problems[0] and "100" in problems[0]


def test_exporting_an_empty_graph_is_refused(monkeypatch, tmp_path):
    """**An empty snapshot published as a demo is the worst artefact here.**
    It imports in no time, verifies against nothing, and shows a blank graph
    in front of a customer."""
    monkeypatch.setattr(snapshot, "Engine", lambda url, graph=None: Graph())
    with pytest.raises(Refused, match="holds nothing"):
        snapshot.export("http://engine.test", tmp_path / "unused.sgsnap")


def test_importing_into_a_loaded_engine_is_refused(monkeypatch, tmp_path):
    """It merges rather than replaces, so the result is neither graph."""
    monkeypatch.setattr(snapshot, "Engine",
                        lambda url, graph=None: Graph({"Course": 791}))
    monkeypatch.setattr(snapshot, "still_held", lambda url: 1098)
    sent = []
    monkeypatch.setattr(snapshot, "post",
                        lambda *a, **k: sent.append(a) or (200, b"{}"))
    target = tmp_path / "x.sgsnap"
    target.write_bytes(b"not really a snapshot")
    with pytest.raises(Refused, match="already holds"):
        snapshot.load("http://engine.test", target)
    # **Refused BEFORE, not after.** Relocating the guard below the POST kept
    # this test passing on any machine where the POST happened to succeed;
    # only this line catches it. The import is a MERGE and is not undoable.
    assert sent == [], "the guard refused after already posting the snapshot"


def test_an_engine_holding_labels_this_module_never_heard_of_is_not_empty(
        monkeypatch, tmp_path):
    """**The guard failed open on everything it does not know about.**

    "Holds something" was `sum(counts(engine).values())`, and `counts` knows
    four district labels and four district edge types. An engine holding the
    Virginia spine — `Institution`, `Programme`, `Completion` from
    `etl/load_education.py` — summed to zero and read as empty, and the same
    goes for every declared-and-unloaded label on the dataset card. The
    import is a MERGE, so it is not undoable.

    `still_held` asks `/api/status`, which is instance-wide, so a graph full
    of labels this module has never heard of is still a graph.
    """
    monkeypatch.setattr(snapshot, "Engine",
                        lambda url, graph=None: Graph())   # counts -> all zero
    monkeypatch.setattr(snapshot, "still_held", lambda url: 58_317)
    sent = []
    monkeypatch.setattr(snapshot, "post",
                        lambda *a, **k: sent.append(a) or (200, b"{}"))
    target = tmp_path / "x.sgsnap"
    target.write_bytes(b"snapshot")
    with pytest.raises(Refused, match="58,317"):
        snapshot.load("http://engine.test", target)
    assert sent == []


def test_an_unmeasurable_engine_is_refused_rather_than_read_as_empty(
        monkeypatch, tmp_path):
    """`etl/scratch_engine.py` documents this guard failing open twice, both
    times by letting something unmeasurable read as zero. A refusal is the
    only safe reading."""
    def cannot(url):
        raise snapshot.Unusable(f"{url} answered without a storage.nodes count")
    monkeypatch.setattr(snapshot, "still_held", cannot)
    target = tmp_path / "x.sgsnap"
    target.write_bytes(b"snapshot")
    with pytest.raises(Refused, match="storage.nodes"):
        snapshot.load("http://engine.test", target)


def test_the_snapshot_is_not_committed():
    """`data/` is gitignored and this ships as a release asset. A graph
    artefact is not source, and #6's house rule is that no raw data can be
    committed by accident."""
    import subprocess
    listed = subprocess.run(["git", "ls-files"], cwd=ROOT,
                            capture_output=True, text=True)
    # `check=True` and a non-empty listing: without them a subprocess that
    # failed for any reason returns empty stdout and the assertion below
    # passes vacuously — a test that reports success when nothing ran.
    assert listed.returncode == 0, f"git ls-files failed: {listed.stderr}"
    assert listed.stdout.strip(), "git ls-files listed nothing"
    assert ".sgsnap" not in listed.stdout, "a snapshot is committed"


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


def test_the_record_says_the_snapshot_is_not_byte_reproducible():
    """**Three exports of an unchanged graph give three different files.**
    Measured over three exports; the sizes and the spread are in the record
    under `snapshot.reproducible` and are deliberately not repeated here —
    the three figures this docstring used to quote had drifted from it.

    Two things follow, and both are decisions rather than trivia:

      * a published snapshot cannot be verified by re-exporting and comparing
        — its integrity has to be checked against the hash of the file that
        was actually published;
      * an exact byte count on a page is a figure that drifts on every export,
        which is why the dataset card rounds it.

    Written as this repo's belief about 1.1.0. If exports become
    deterministic, this fails and the card can start quoting an exact size.
    """
    if not RECORD.exists():
        pytest.skip("no committed record yet")
    found = json.loads(RECORD.read_text(encoding="utf-8"))
    repro = found["snapshot"]["reproducible"]
    assert repro["byte_identical"] is False, (
        "exports are byte-identical now; the card may quote an exact size and "
        "a download may be checked by re-export")
    assert repro["bytes_spread"] > 0
    assert repro["exports_compared"] >= 2


def test_the_card_rounds_the_snapshot_size():
    """A page carrying an exact byte count for an artefact that changes size
    on every export is a page that goes stale by itself."""
    card = (ROOT / "DATASET-CARD.md").read_text(encoding="utf-8")
    if not RECORD.exists():
        pytest.skip("no committed record yet")
    exact = json.loads(RECORD.read_text(encoding="utf-8"))["snapshot"]["bytes"]
    assert f"{exact:,} bytes" not in card, (
        "the card quotes an exact byte count, which the next export changes")


def test_import_checks_the_graph_against_the_record_not_against_itself(
        monkeypatch, tmp_path, capsys):
    """**The check that could only pass.** `import` verified against
    `found["in_graph"]` — `counts(engine)` read from the same engine moments
    earlier — so it compared the graph to itself. A half-import, the failure
    this module exists to catch, sailed through it.

    Here the engine comes back holding one Course where the record wants 791.
    Against itself that agrees; against the record it does not.
    """
    monkeypatch.setattr(snapshot, "Engine", lambda url, graph=None: Graph({"Course": 1}))
    handed = {}
    monkeypatch.setattr(snapshot, "load",
                        lambda url, path, graph=None, expect_sha256=None: (
                            handed.update(sha256=expect_sha256),
                            {"seconds": 0.01, "bytes": 10, "engine_said": {},
                             "in_graph": {"Course": 1}})[1])
    target = tmp_path / "x.sgsnap"
    target.write_bytes(b"snapshot")
    assert snapshot.main(["import", "--file", str(target),
                          "--url", "http://engine.test"]) == 4
    # The `import` action's hash wiring mutated green: it reads the published
    # digest out of the record and hands it to `load`, and nothing checked it
    # arrived.
    recorded = json.loads(snapshot.RECORD.read_text(encoding="utf-8"))
    assert handed["sha256"] == recorded["snapshot"]["sha256"]
    said = capsys.readouterr().err
    assert "Course" in said, (
        f"the import failed without naming what disagreed:\n{said}")


def test_the_record_carries_no_absolute_path(monkeypatch, tmp_path):
    """A committed document carrying somebody's home directory. `export`
    recorded `str(into)`, so `snapshot-measured.json` shipped
    `/Users/.../edtech-kg/data/edtech-kg.sgsnap`."""
    monkeypatch.setattr(snapshot, "Engine", lambda url, graph=None: Graph({"Course": 791}))
    monkeypatch.setattr(snapshot, "post",
                        lambda *a, **k: (200, b"snapshot-bytes"))
    into = ROOT / "data" / "written-by-a-test.sgsnap"
    try:
        found = snapshot.export("http://engine.test", into)
    finally:
        into.unlink(missing_ok=True)
    assert found["file"] == "data/written-by-a-test.sgsnap"
    assert not pathlib.Path(found["file"]).is_absolute()


def test_a_round_trip_that_does_not_reproduce_the_graph_is_not_recorded(
        monkeypatch, tmp_path, capsys):
    """**The guard protecting every other figure here, and it had no test.**
    Changing `if wrong:` to `if False:` left the full suite green at 1,844
    passing — so a snapshot that did not reproduce its source could become
    the record everything else is measured against.
    """
    target = tmp_path / "x.sgsnap"
    record = tmp_path / "snapshot-measured.json"
    monkeypatch.setattr(snapshot, "RECORD", record)
    monkeypatch.setattr(snapshot, "export", lambda url, into, graph=None: (
        into.write_bytes(b"snapshot"),
        {"file": "data/x.sgsnap", "bytes": 8, "sha256": "deadbeef",
         "taken_from": {"Course": 791},
         "properties": {"Course.name": 791}})[1])
    monkeypatch.setattr(snapshot, "reproducibility",
                        lambda url, times=3: {"byte_identical": False})
    monkeypatch.setattr(snapshot, "load", lambda url, path, graph=None,
                        expect_sha256=None: {"seconds": 0.02, "bytes": 8,
                                             "engine_said": {},
                                             "in_graph": {"Course": 790}})
    # the imported graph disagrees with what the export was taken from
    monkeypatch.setattr(snapshot, "Engine",
                        lambda url, graph=None: Graph({"Course": 790}))
    assert snapshot.main(["record", "--file", str(target),
                          "--url", "http://a.test",
                          "--from-url", "http://b.test"]) == 4
    assert "Course" in capsys.readouterr().err
    assert not record.exists(), (
        "a round trip that did not reproduce the graph was still recorded")
    # and the bad export did not land at the path demo/ready.sh reads
    assert not target.exists(), (
        f"the failed export was left at {target.name}, which is the file "
        f"`demo/ready.sh` imports by default")


def test_a_snapshot_that_does_not_match_the_published_hash_is_refused(
        monkeypatch, tmp_path):
    """`DATASET-CARD.md` promises a download is checked against the published
    file's hash. Before this, `reproducibility` computed digests and threw
    them away, `export` recorded none, and `load` posted whatever it read —
    a documented guarantee with nothing behind it, on the one path where a
    binary from a Releases page reaches an engine."""
    monkeypatch.setattr(snapshot, "still_held", lambda url: 0)
    sent = []
    monkeypatch.setattr(snapshot, "post",
                        lambda *a, **k: sent.append(a) or (200, b"{}"))
    target = tmp_path / "x.sgsnap"
    target.write_bytes(b"not the published bytes")
    with pytest.raises(Refused, match="hashes to"):
        snapshot.load("http://engine.test", target,
                      expect_sha256="0" * 64)
    assert sent == [], "posted a snapshot whose hash did not match"


def test_a_snapshot_matching_the_published_hash_is_imported(monkeypatch,
                                                            tmp_path):
    """The other direction, so the check cannot be satisfied by always
    refusing."""
    import hashlib
    monkeypatch.setattr(snapshot, "still_held", lambda url: 0)
    monkeypatch.setattr(snapshot, "Engine", lambda url, graph=None: Graph())
    monkeypatch.setattr(snapshot, "post", lambda *a, **k: (200, b"{}"))
    target = tmp_path / "x.sgsnap"
    target.write_bytes(b"the published bytes")
    digest = hashlib.sha256(b"the published bytes").hexdigest()
    assert snapshot.load("http://engine.test", target,
                         expect_sha256=digest)["bytes"] == 19


def test_an_unreadable_count_is_a_refusal_not_a_zero():
    """**`or 0` is how this guard fails open**, and `etl/scratch_engine.py`
    records it happening twice. `counts` read
    `int(rows[0][0]) if rows and rows[0] else 0`, so an engine that answered
    nothing to a count read as a graph holding none of that label — and the
    pre-import guard is built on this function, so an unmeasurable engine read
    as an empty one and got merged into.
    """
    class Silent(Graph):
        def scalar(self, statement):
            return None
    with pytest.raises(Refused, match="could not be measured"):
        snapshot.counts(Silent())


def test_a_count_that_is_not_a_number_is_a_refusal():
    """The engine returning a count as text crashed the formatting rather
    than reporting the graph it found — `etl/engine.py` documents that
    answers come back typed however the engine felt like typing them."""
    class Wordy(Graph):
        def scalar(self, statement):
            return "seven hundred and ninety-one"
    with pytest.raises(Refused, match="not a number"):
        snapshot.counts(Wordy())


def test_the_graph_is_named_and_it_is_the_one_everything_else_uses():
    """**The graph-naming fix had no test.** All three mutations were green
    at 1,851 passing:

        DEFAULT_GRAPH = "edtech" -> "default"
        Engine(url, graph=graph) -> Engine(url)
        --graph default          -> "default"

    because every stub here was `lambda url, graph=None: ...` — accepting the
    argument and discarding it. The failure that fix exists for is the import
    landing in `edtech` while `verify` reads `default` and finds zeros.
    """
    assert snapshot.DEFAULT_GRAPH == "edtech"
    # Tied to the walkthrough's own default, so the two cannot drift apart —
    # a snapshot imported into a graph `demo.demo` does not open is a demo
    # that opens on nothing.
    walkthrough = (ROOT / "demo" / "demo.py").read_text(encoding="utf-8")
    assert f'"--graph", default="{snapshot.DEFAULT_GRAPH}"' in walkthrough, (
        "demo/demo.py and etl/snapshot.py disagree about the default graph")


def test_export_reads_the_graph_it_was_told_to(monkeypatch, tmp_path):
    """The stub captures the graph rather than swallowing it."""
    seen = []
    monkeypatch.setattr(snapshot, "Engine",
                        lambda url, graph=None: seen.append(graph)
                        or Graph({"Course": 791}))
    monkeypatch.setattr(snapshot, "post", lambda *a, **k: (200, b"bytes"))
    snapshot.export("http://engine.test", tmp_path / "x.sgsnap")
    assert seen == ["edtech"], f"export read graph {seen}"


def test_load_and_verify_work_in_the_named_graph(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(snapshot, "Engine",
                        lambda url, graph=None: seen.append(graph) or Graph())
    monkeypatch.setattr(snapshot, "still_held", lambda url: 0)
    monkeypatch.setattr(snapshot, "post", lambda *a, **k: (200, b"{}"))
    target = tmp_path / "x.sgsnap"
    target.write_bytes(b"snapshot")
    snapshot.load("http://engine.test", target)
    snapshot.verify("http://engine.test", {"Course": 0})
    assert seen == ["edtech", "edtech"], f"worked in graph {seen}"


def test_the_command_line_defaults_to_the_named_graph(monkeypatch, tmp_path):
    """`--graph`'s DEFAULT mutated green: changing it to `"default"` left the
    suite passing, because every other test passes the graph explicitly or
    calls the functions directly. This is the path an operator actually
    takes — `python -m etl.snapshot export --url ...` with no `--graph`."""
    seen = []
    monkeypatch.setattr(snapshot, "Engine",
                        lambda url, graph=None: seen.append(graph)
                        or Graph({"Course": 791}))
    monkeypatch.setattr(snapshot, "post", lambda *a, **k: (200, b"bytes"))
    assert snapshot.main(["export", "--file", str(tmp_path / "x.sgsnap"),
                          "--url", "http://engine.test"]) == 0
    assert seen == ["edtech"], (
        f"a bare `export` worked in graph {seen}, not the one this repo loads")


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

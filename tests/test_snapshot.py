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
from tests.graph_stub import Graph

ROOT = pathlib.Path(__file__).resolve().parents[1]
RECORD = ROOT / "docs" / "sources" / "snapshot-measured.json"


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


def test_reproducibility_reports_exports_that_differ(monkeypatch):
    """**The function behind the non-reproducibility claim, never executed.**

    Its result drives two decisions on the dataset card: that the size is
    quoted ROUNDED, and that a download is checked against the published hash
    rather than by re-exporting. The only test touching it flipped
    `byte_identical` in the committed JSON — which goes red with no code
    change at all, so it pinned the artefact and said nothing about the code.

    Three bodies of different lengths, stubbed at `post`.
    """
    bodies = [b"a" * 100, b"b" * 118, b"c" * 103]
    handed = iter(bodies)
    monkeypatch.setattr(snapshot, "post",
                        lambda *a, **k: (200, next(handed)))
    found = snapshot.reproducibility("http://engine.test", times=3)

    assert found["exports_compared"] == 3
    assert found["bytes_min"] == 100
    assert found["bytes_max"] == 118
    assert found["bytes_spread"] == 18
    assert found["byte_identical"] is False
    assert len(found["sha256"]) == 3
    assert len(set(found["sha256"])) == 3, "three different bodies, one digest"
    import hashlib
    assert found["sha256"] == [hashlib.sha256(b).hexdigest() for b in bodies]


def test_reproducibility_says_so_when_exports_ARE_identical(monkeypatch):
    """The other direction, so `byte_identical` cannot be satisfied by always
    answering False. If a future engine made exports deterministic, this is
    what would notice — the record-reading test could not, because it only
    fires when somebody re-runs `record` and commits the result."""
    monkeypatch.setattr(snapshot, "post",
                        lambda *a, **k: (200, b"identical every time"))
    found = snapshot.reproducibility("http://engine.test", times=3)
    assert found["byte_identical"] is True
    assert found["bytes_spread"] == 0
    assert len(set(found["sha256"])) == 1


def test_reproducibility_refuses_an_engine_that_stops_answering(monkeypatch):
    """A non-200 part-way through leaves a comparison over fewer exports than
    it claims, which would understate the spread."""
    answers = iter([(200, b"first"), (503, b""), (200, b"third")])
    monkeypatch.setattr(snapshot, "post", lambda *a, **k: next(answers))
    with pytest.raises(Refused, match="503"):
        snapshot.reproducibility("http://engine.test", times=3)

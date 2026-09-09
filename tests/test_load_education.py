"""The national-spine loader, driven without an engine.

edtech-kg#7. Two things decide whether this load is trustworthy and neither
is visible from the input: the Completion key, and whether a second run
creates anything. Both were wrong first — the key omitted `majornum` and the
edges were not idempotent — so both are asserted here rather than described.
"""

from __future__ import annotations

import json

import pytest

from etl import load_education as loader
from etl.engine import Refused


class Recorder:
    """Every statement the loader would send, in order, with scripted answers."""

    def __init__(self, answers=None):
        self.sent: list[str] = []
        self.answers = answers or {}

    def run(self, statement: str):
        self.sent.append(statement)
        for fragment, reply in self.answers.items():
            if fragment in statement:
                return reply
        return {"records": []}


def row(**over):
    base = {"unitid": 231624, "cipcode_6digit": 110701, "award_level": 5,
            "majornum": 1, "race": 1, "sex": 1, "awards_6digit": 3}
    return {**base, **over}


def test_the_completion_key_separates_a_first_major_from_a_second():
    """**The defect the first load found.** IPEDS publishes a `majornum`, and
    the schema's five-part key omitted it — so two real completions at one
    institution, CIP, award level and demographic merged into one node and a
    count was lost. Measured over the Virginia 2022 slice: 3,524 groups where
    more than one `majornum` has a non-zero award."""
    first, second = row(majornum=1), row(majornum=2)
    assert loader.completion_id(first) != loader.completion_id(second), (
        "a first-major and a second-major completion share a key; loading "
        "them merges two facts and loses one")


def test_every_component_of_the_key_changes_it():
    """Six parts. A component that does not move the key is not in it, and
    the schema names all six."""
    base = row()
    for field, other in (("unitid", 999999), ("cipcode_6digit", 220101),
                         ("award_level", 7), ("majornum", 2),
                         ("race", 2), ("sex", 2)):
        assert loader.completion_id(base) != \
            loader.completion_id(row(**{field: other})), field


def test_the_key_is_stable_across_runs():
    """A key derived from anything but the row would re-create every node on
    every load."""
    assert loader.completion_id(row()) == loader.completion_id(row())


def test_a_node_that_is_already_there_is_not_created_again():
    """The lookup half of lookup-then-create. `MERGE` is not used — #169
    measured it ignoring the constraint's index and scanning, which is
    quadratic over this slice."""
    engine = Recorder({"MATCH (n:Programme)": {"records": [["110701"]]}})
    writer = loader.Writer(engine)
    writer.node("Programme", "cip_code", "110701", {"cip_code": "110701"})
    assert writer.created == 0
    assert writer.already_there == 1
    assert not any("CREATE" in s for s in engine.sent)


def test_a_node_that_is_absent_is_created():
    """The negative must be reachable only by looking — a writer that never
    created anything would pass the test above on any input."""
    engine = Recorder()
    writer = loader.Writer(engine)
    writer.node("Programme", "cip_code", "110701", {"cip_code": "110701"})
    assert writer.created == 1
    assert any(s.startswith("CREATE (n:Programme") for s in engine.sent)


def test_an_edge_that_is_already_there_is_not_created_again():
    """**The loader was NOT idempotent for edges, and its own report caught
    it.** A second run over the same slice created 2,000 duplicate AT and IN
    edges: the nodes were idempotent and the edges were not.

    An edge `MERGE` would not fix it either — #163 records edge `MERGE`
    ignoring its property map on 1.1.0.
    """
    engine = Recorder({"-[r:AT]->": {"records": [[1]]}})
    writer = loader.Writer(engine)
    writer.edge("AT", ("Completion", "id", "abc"),
                ("Institution", "unitid", "231624"))
    assert writer.created == 0
    assert writer.already_there == 1
    assert not any("CREATE (a)-" in s for s in engine.sent)


def test_an_edge_that_is_absent_is_created():
    engine = Recorder({"-[r:AT]->": {"records": [[0]]}})
    writer = loader.Writer(engine)
    writer.edge("AT", ("Completion", "id", "abc"),
                ("Institution", "unitid", "231624"))
    assert writer.created == 1
    assert any("CREATE (a)-[:AT]->(b)" in s for s in engine.sent)


def test_an_edge_introduces_both_endpoints_fresh():
    """**A MATCH whose endpoints are BOTH already bound does not filter on
    1.1.0** — it is silently ignored, which `docs/engine-behaviours.md`
    records. So the write pattern gives each side its own WHERE."""
    engine = Recorder({"-[r:AT]->": {"records": [[0]]}})
    writer = loader.Writer(engine)
    writer.edge("AT", ("Completion", "id", "abc"),
                ("Institution", "unitid", "231624"))
    written = [s for s in engine.sent if "CREATE (a)-" in s][0]
    assert written.count("WHERE") == 2, (
        "an endpoint was bound without its own WHERE, which does not filter")


def test_a_value_that_cannot_be_quoted_is_refused_not_mangled():
    """1.1.0 has no escape sequence inside a string literal, so a value
    carrying a quote cannot be written at all. A silently truncated
    institution name is a wrong answer that looks like a right one."""
    with pytest.raises(Refused):
        loader.quote('St. Mary"s College')
    with pytest.raises(Refused):
        loader.quote("back\\slash")
    assert loader.quote("Virginia Tech") == '"Virginia Tech"'


def test_a_missing_download_says_which_command_produces_it(tmp_path,
                                                           monkeypatch):
    """`data/` is gitignored, so a fresh clone has none of it. A stack trace
    from a missing file sends the reader nowhere."""
    monkeypatch.setattr(loader, "CACHE", tmp_path)
    with pytest.raises(loader.Missing, match="download_education"):
        loader.held("completions")


def test_counts_come_from_the_graph_not_from_the_input(monkeypatch):
    """**A loader reporting what it issued has reported its own
    intentions.** On this engine the two differ: a unique constraint does not
    reject a duplicate, so a double-issued CREATE leaves two nodes and no
    error."""
    engine = Recorder({
        "MATCH (n:Institution)": {"records": [[147]]},
        "MATCH (n:Programme)": {"records": [[121]]},
        "MATCH (n:Completion)": {"records": [[2000]]},
        "[r:AT]": {"records": [[4000]]},
        "[r:IN]": {"records": [[2000]]},
    })
    counts = loader.in_the_graph(engine)
    assert counts["AT"] == 4000, "the read-back did not come from the graph"
    lines = "\n".join(loader.report({
        "seconds": 1.0, "statements_issued": 10, "nodes_and_edges_created": 5,
        "already_present": 5, "institutions_in": 147, "programmes_in": 121,
        "completions_in": 2000, "rows_skipped_zero_awards": 0,
        "duplicate_rows_skipped": 0}, counts))
    assert "+2,000" in lines, (
        "a gap between issued and held was not reported; that gap is the "
        "only thing that catches a non-idempotent write")


def test_every_count_interposes_a_with(monkeypatch):
    """An aggregate directly over a multi-node MATCH is only correct when the
    WHERE constrains the aggregated variable — `engine-behaviours.md`
    measured 3,280 where 19,716 was due."""
    engine = Recorder()
    loader.in_the_graph(engine)
    for statement in engine.sent:
        if statement.startswith("MATCH (n:"):
            assert "WITH n RETURN count(n)" in statement, statement


def test_a_partial_load_is_refused_as_a_record(monkeypatch, tmp_path):
    """**A record of a partial load, filed where the card reads the whole
    one, is a wrong figure that looks measured.** `--limit 100` and the full
    slice write the same filename, and nothing downstream could tell them
    apart. Refused rather than written with a caveat nobody reads."""
    monkeypatch.setattr(loader, "RECORD", tmp_path / "spine.json")
    monkeypatch.setattr(loader, "load", lambda *a, **k: {
        "seconds": 1.0, "statements_issued": 1, "nodes_and_edges_created": 1,
        "already_present": 0, "institutions_in": 1, "programmes_in": 1,
        "completions_in": 1, "rows_skipped_zero_awards": 0,
        "duplicate_rows_skipped": 0})
    monkeypatch.setattr(loader, "in_the_graph", lambda e: {})
    monkeypatch.setattr(loader, "Engine", lambda url: Recorder())
    for partial in (["--dry-run"], ["--limit", "100"], ["--all-rows"]):
        assert loader.main(["--record", *partial]) == 4, partial
        assert not (tmp_path / "spine.json").exists()


def test_the_record_keeps_issued_and_held_apart(monkeypatch, tmp_path):
    """Two figures, stored separately, because they are two claims. Merged
    into one, the gap that caught the non-idempotent edge writes could not be
    reconstructed by anyone reading the record later."""
    written = {}
    monkeypatch.setattr(loader, "RECORD", tmp_path / "spine.json")
    monkeypatch.setattr(loader, "write_record",
                        lambda path, payload: written.update(payload))
    monkeypatch.setattr(loader, "load", lambda *a, **k: {
        "seconds": 2.0, "statements_issued": 9, "nodes_and_edges_created": 6,
        "already_present": 3, "institutions_in": 1, "programmes_in": 1,
        "completions_in": 2, "rows_skipped_zero_awards": 4,
        "duplicate_rows_skipped": 0})
    monkeypatch.setattr(loader, "in_the_graph", lambda e: {
        "Institution": 1, "Programme": 1, "Completion": 2, "AT": 2, "IN": 2})
    monkeypatch.setattr(loader, "Engine", lambda url: Recorder())
    assert loader.main(["--record"]) == 0
    assert written["issued"]["completions_in"] == 2
    assert written["in_graph"]["Completion"] == 2
    assert written["engine_version_reported"], (
        "the record does not say which engine answered, so a figure taken "
        "from a different build reads as one from this one")


def test_the_rate_curve_is_sampled_from_the_run_that_reports_it(monkeypatch,
                                                               tmp_path):
    """**The curve used to come from a different load than the record.**

    A second process polled the graph once a minute while a load ran, and the
    doc then printed that curve beside a record written by a LATER run — two
    loads quoted as one. Nothing said so, and nothing could have caught it:
    both numbers were real, and neither described the other's run.

    The loader already knows how many completions it has written and when it
    started, so the curve costs no extra query.
    """
    monkeypatch.setattr(loader, "CURVE_EVERY", 0)   # sample every row
    monkeypatch.setattr(loader, "CACHE", tmp_path)
    rows = [{"unitid": 1, "cipcode_6digit": 110701 + i, "award_level": 5,
             "majornum": 1, "race": 1, "sex": 1, "awards_6digit": 1}
            for i in range(4)]
    (tmp_path / f"institutions-{loader.FIPS}-{loader.YEAR}.json").write_text(
        json.dumps({"rows": [{"unitid": 1, "inst_name": "X",
                              "state_abbr": "VA"}]}), encoding="utf-8")
    (tmp_path / f"completions-{loader.FIPS}-{loader.YEAR}.json").write_text(
        json.dumps({"rows": rows}), encoding="utf-8")

    summary = loader.load(Recorder())
    curve = summary["rate_curve"]
    assert curve, "the run reported no curve at all"
    assert curve[-1]["completions_held"] == summary["completions_in"], (
        "the curve's last sample and the run's own total disagree, so they "
        "are not describing one load")
    assert all(point["seconds"] <= summary["seconds"] for point in curve)

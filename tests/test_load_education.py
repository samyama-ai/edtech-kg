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


def slice_on_disk(tmp_path, rows, institutions=None):
    """Write a cache this loader will read, and return its directory."""
    (tmp_path / f"institutions-{loader.FIPS}-{loader.YEAR}.json").write_text(
        json.dumps({"rows": institutions if institutions is not None
                    else [{"unitid": 1, "inst_name": "X", "state_abbr": "VA"}]}),
        encoding="utf-8")
    (tmp_path / f"completions-{loader.FIPS}-{loader.YEAR}.json").write_text(
        json.dumps({"rows": rows}), encoding="utf-8")
    return tmp_path


def completions(n, first=0, **over):
    """`n` rows with DISTINCT keys, starting at `first`.

    `first` exists because a fixture that reused CIP codes across two calls
    made the zero-award rows collide with the awarded ones — so a test about
    zero-award skipping was measuring duplicate-key skipping as well, and
    passed for the wrong reason.
    """
    return [{"unitid": 1, "cipcode_6digit": 110701 + first + i,
             "award_level": 5, "majornum": 1, "race": 1, "sex": 1,
             "awards_6digit": 1, **over}
            for i in range(n)]


def test_the_rate_curve_closes_on_the_run_even_with_no_periodic_sample(
        monkeypatch, tmp_path):
    """**The interval is LONGER than the run**, so no periodic sample fires
    and the closing sample is the only thing that can produce a curve.

    That is the whole of the claim, and the previous version could not test
    it: with `CURVE_EVERY` at 0.001 a sample fired on nearly every row, so
    `curve[-1]["completions_held"] == completions_in` held whatever the
    closing logic did. Setting a tiny interval to test a closing sample tests
    the sampling instead.
    """
    monkeypatch.setattr(loader, "CURVE_EVERY", 3600)
    summary = loader.load(Recorder(),
                          cache=slice_on_disk(tmp_path, completions(4)))
    curve = summary["rate_curve"]
    assert len(curve) == 1, (
        f"a run shorter than one interval should record exactly the closing "
        f"sample, not {len(curve)}")
    assert curve[0]["completions_held"] == summary["completions_in"] == 4


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
    # A very short interval, so several samples fire. It is not a realistic
    # one — an earlier comment here claimed it was — and the case that
    # matters is the opposite, which the test above covers.
    monkeypatch.setattr(loader, "CURVE_EVERY", 0.0001)
    summary = loader.load(Recorder(),
                          cache=slice_on_disk(tmp_path, completions(6)))
    curve = summary["rate_curve"]
    assert len(curve) > 1, "no periodic sample fired at all"
    assert curve[-1]["completions_held"] == summary["completions_in"]
    assert all(point["seconds"] <= summary["seconds"] for point in curve)
    held = [point["completions_held"] for point in curve]
    assert held == sorted(held), "the curve goes backwards"


def test_rows_recording_zero_awards_are_skipped_and_counted(tmp_path):
    """69% of this slice says nobody finished, and dropping them is a SCOPE
    decision — so the count of what was dropped is reported either way, or
    the slice can be mistaken for the whole."""
    rows = completions(3) + completions(2, first=3, awards_6digit=0)
    summary = loader.load(Recorder(), cache=slice_on_disk(tmp_path, rows))
    assert summary["rows_skipped_zero_awards"] == 2
    assert summary["completions_in"] == 3


def test_all_rows_loads_the_zero_award_rows_it_otherwise_skips(tmp_path):
    """A zero row is a real IPEDS observation. The flag exists because this
    is a scope decision and not a filter, and a flag nothing exercises is a
    flag that has stopped working."""
    rows = completions(3) + completions(2, first=3, awards_6digit=0)
    summary = loader.load(Recorder(), only_awarded=False,
                          cache=slice_on_disk(tmp_path, rows))
    assert summary["rows_skipped_zero_awards"] == 0
    assert summary["completions_in"] == 5


def test_rows_collapsing_onto_one_key_are_skipped_and_counted(tmp_path):
    """The API returns rows that reduce to one key — 169 of them in this
    slice. Skipping them in the walk rather than leaving them to the lookup
    keeps the issued count honest, and the count of them is reported."""
    row = completions(1)[0]
    summary = loader.load(Recorder(),
                          cache=slice_on_disk(tmp_path, [row, dict(row), row]))
    assert summary["completions_in"] == 1
    assert summary["duplicate_rows_skipped"] == 2


def test_a_dry_run_counts_what_it_would_send_and_sends_nothing(tmp_path):
    """**A dry run used to count every node twice** — once as a lookup and
    once as a create — so `statements_issued` came out roughly double and the
    figure could not be compared with the real run it exists to predict.

    One statement per object: three lookups per completion, plus the
    institution and the programme.
    """
    engine = Recorder()
    rows = completions(2)
    summary = loader.load(engine, dry_run=True,
                          cache=slice_on_disk(tmp_path, rows))
    assert engine.sent == [], "a dry run sent statements to the engine"
    assert summary["nodes_and_edges_created"] == 0
    # 1 institution + 2 programmes + 2 completions + 2 AT + 2 IN.
    assert summary["statements_issued"] == 9


def test_limit_zero_loads_nothing_rather_than_everything(tmp_path):
    """`if limit:` read `--limit 0` as "no limit" and loaded the whole slice
    — the opposite of what was asked, on the flag whose purpose is to bound
    the write."""
    rows = completions(5)
    assert loader.load(Recorder(), limit=0,
                       cache=slice_on_disk(tmp_path, rows))["completions_in"] == 0
    assert loader.load(Recorder(), limit=2,
                       cache=slice_on_disk(tmp_path, rows))["completions_in"] == 2
    assert loader.load(Recorder(),
                       cache=slice_on_disk(tmp_path, rows))["completions_in"] == 5


def test_a_value_that_cannot_be_written_is_refused_before_anything_is(tmp_path):
    """**There is no transaction to roll back to.** A `quote()` refusal used
    to raise part-way through, leaving a graph half loaded — one unwritable
    institution name in a 58,317-row load would have left tens of thousands
    of nodes behind and a non-zero exit, which is the worst of both.
    """
    engine = Recorder()
    cache = slice_on_disk(
        tmp_path, completions(3),
        institutions=[{"unitid": 1, "inst_name": 'St. Mary"s',
                       "state_abbr": "VA"}])
    with pytest.raises(Refused):
        loader.load(engine, cache=cache)
    assert engine.sent == [], (
        "the load wrote before discovering it could not finish")


def test_the_report_compares_against_what_the_graph_already_held(tmp_path):
    """**A whole-graph count against this run's issued count reports
    pre-existing data as a gap this run caused.** Another year's completions,
    another state's, would show as tens of thousands of unexplained nodes.

    On an empty engine the two readings agree, which is exactly why the wrong
    one survived — every run so far has been on a fresh container.
    """
    loaded = {"seconds": 1.0, "statements_issued": 3,
              "nodes_and_edges_created": 3, "already_present": 0,
              "institutions_in": 1, "programmes_in": 1, "completions_in": 1,
              "rows_skipped_zero_awards": 0, "duplicate_rows_skipped": 0,
              "created_by": {"Institution": 1, "Completion": 1, "AT": 1}}
    before = {"Institution": 40, "Programme": 0, "Completion": 900,
              "AT": 900, "IN": 0}
    after = {"Institution": 41, "Programme": 0, "Completion": 901,
             "AT": 901, "IN": 0}
    printed = "\n".join(loader.report(loaded, after, before))
    assert "+" not in printed, (
        f"a graph that already held data was reported as a gap:\n{printed}")

    lost = "\n".join(loader.report(loaded, {**after, "Completion": 900},
                                   before))
    assert "-1" in lost, "a node that did not arrive was not reported"


def test_the_record_carries_the_idempotence_run_not_just_the_first(monkeypatch,
                                                                   tmp_path):
    """**The page claimed "175,762 statements, zero created" and that figure
    was in no record.** It came from a run done by hand, on a page whose
    opening sentence says every figure was substituted from the record.

    A second pass is the only way that claim can be true, and it is the claim
    the loader's whole design rests on — the first version created 2,000
    duplicate edges on a second run and only the gap column showed it.
    """
    written = {}
    monkeypatch.setattr(loader, "RECORD", tmp_path / "spine.json")
    monkeypatch.setattr(loader, "write_record",
                        lambda path, payload: written.update(payload))
    monkeypatch.setattr(loader, "Engine", lambda url: Recorder())

    runs = iter([
        {"seconds": 10.0, "statements_issued": 6, "nodes_and_edges_created": 3,
         "already_present": 0, "institutions_in": 1, "programmes_in": 1,
         "completions_in": 1, "rows_skipped_zero_awards": 0,
         "duplicate_rows_skipped": 0, "created_by": {}, "rate_curve": []},
        {"seconds": 4.0, "statements_issued": 3, "nodes_and_edges_created": 0,
         "already_present": 3, "institutions_in": 1, "programmes_in": 1,
         "completions_in": 1, "rows_skipped_zero_awards": 0,
         "duplicate_rows_skipped": 0, "created_by": {}, "rate_curve": []},
    ])
    monkeypatch.setattr(loader, "load", lambda *a, **k: next(runs))
    monkeypatch.setattr(loader, "in_the_graph", lambda e: {"Completion": 1})

    assert loader.main(["--record"]) == 0
    assert "second_run" in written, (
        "the record describes one pass, so the idempotence figure the page "
        "quotes has no run behind it")
    assert written["second_run"]["nodes_and_edges_created"] == 0
    assert written["second_run"]["statements_issued"] == 3

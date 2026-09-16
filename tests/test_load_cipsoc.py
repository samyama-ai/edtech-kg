"""The CIP-SOC loader, driven without an engine.

edtech-kg#196. The crosswalk is a published CLAIM with a revision history, not
a fact, so the edition rides on every edge and is read off the workbook's own
column headings rather than its filename — a downloaded copy can be renamed.

The load is deliberately asymmetric: occupations are the published vocabulary
and load whole, while an edge is only issued when its `Programme` is already
in the graph. Writing one otherwise is a no-op that `Writer.edge` still counts
as created, so the gap would be invisible in the issued figure and visible
only in the graph.
"""

from __future__ import annotations

import pytest

from etl import load_cipsoc as loader
from etl import probe_cipsoc
from etl.engine import Refused
from tests.education_fixtures import Recorder

HEADER = ["CIP2020Code", "CIP2020Title", "SOC2018Code", "SOC2018Title"]

SHEET = [
    HEADER,
    ["01.0000", "Agriculture, General.", "19-1011", "Animal Scientists"],
    ["01.0000", "Agriculture, General.", "19-1012", "Food Scientists"],
    ["51.3801", "Registered Nursing.", "29-1141", "Registered Nurses"],
    ["99.9999", "Unmatched.", "99-9999", "NO MATCH"],
    ["", "", "29-1141", "Registered Nurses"],
]


@pytest.fixture
def crosswalk(monkeypatch):
    monkeypatch.setattr(probe_cipsoc, "sheets", lambda book: {"CIP-SOC": "x"})
    monkeypatch.setattr(probe_cipsoc, "rows", lambda book, part: SHEET)
    # A context manager, because `mappings()` closes the workbook now —
    # `probe_cipsoc.probe()` already used a `with` and this did not.
    class Book:
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(loader.zipfile, "ZipFile", lambda path: Book())


def test_the_edition_comes_from_the_headings_not_the_filename():
    """A downloaded copy can be renamed; the headings cannot change without
    the reader failing loudly."""
    assert loader.edition(HEADER) == "CIP2020-SOC2018"
    assert loader.edition(["CIP2030Code", "SOC2028Code"]) == "CIP2030-SOC2028"


def test_headings_that_name_no_vocabulary_are_refused():
    with pytest.raises(Refused):
        loader.edition(["A", "B", "C"])


def test_no_match_rows_are_not_loaded_as_occupations(crosswalk):
    """`99-9999` is the crosswalk's own sentinel for "this programme maps to
    no occupation". Loading it would create an occupation that is the
    absence of one."""
    read, _ = loader.mappings()
    assert probe_cipsoc.NO_MATCH_SOC not in {r["soc_code"] for r in read}


def test_a_row_blank_on_either_side_is_not_a_mapping(crosswalk):
    read, _ = loader.mappings()
    assert all(r["cip_code"] and r["soc_code"] for r in read)
    assert len(read) == 3, read


def test_the_crosswalks_dotted_codes_are_normalised(crosswalk):
    """The crosswalk publishes `01.0000`; the graph keys on `010000`. The
    join normalises on the way in — which is the whole of #201."""
    read, _ = loader.mappings()
    assert {r["cip_code"] for r in read} == {"010000", "513801"}


def test_an_edge_is_not_issued_for_a_programme_the_graph_lacks(crosswalk):
    """**The gap is scope, not loss** — the crosswalk covers every CIP code
    and this graph holds only the programmes Virginia awarded. Counted rather
    than silently dropped, because a no-op CREATE is still counted as created
    by `Writer.edge`."""
    engine = Recorder({"p.cip_code": {"records": [["513801"]]}})
    summary = loader.load(engine)
    assert summary["edges_issued"] == 1
    assert summary["mappings_without_a_programme"] == 2
    assert summary["programmes_with_an_occupation"] == 1
    assert "010000" not in " ".join(
        s for s in engine.sent if "PREPARES_FOR" in s)


def test_a_graph_with_no_programmes_is_refused_not_reported_as_scope(crosswalk):
    """**The one query whose emptiness changes the meaning of the whole run.**

    With no programmes loaded, every mapping is skipped,
    `mappings_without_a_programme` reads the full count, and the report prints
    "scope, not loss" over a graph that holds no programmes at all — exit 0,
    and a record that looks like a successful load.

    `in_the_graph` in this same module already refuses when a count comes back
    `None` for exactly this reason, and this file names the pattern two tests
    down: "`or 0` is how this class of guard fails open". It was inconsistent
    that the query carrying the most meaning was the one that failed open.
    """
    engine = Recorder({"p.cip_code": {"records": []}})
    with pytest.raises(Refused, match="no Programme nodes"):
        loader.load(engine)
    assert not [s for s in engine.sent if "CREATE" in s], (
        "wrote occupations into a graph with no spine")


def test_the_edition_rides_on_every_edge(crosswalk):
    """`schema/edtech_kg.cypher` puts it there so Q43 can ask which edition
    said a programme prepares you for an occupation. An edge `MERGE` would
    not carry it — #163 records edge MERGE ignoring its property map."""
    engine = Recorder({"p.cip_code": {"records": [["513801"]]}})
    loader.load(engine)
    edges = [s for s in engine.sent if "CREATE (a)-[:PREPARES_FOR" in s]
    assert edges, engine.sent
    for statement in edges:
        assert "source_edition: 'CIP2020-SOC2018'" in statement, statement


def test_a_dry_run_writes_nothing(crosswalk):
    engine = Recorder({"p.cip_code": {"records": [["513801"]]}})
    summary = loader.load(engine, dry_run=True)
    assert summary["nodes_and_edges_created"] == 0
    assert not [s for s in engine.sent if "CREATE" in s]


def test_an_unwritable_value_is_refused_before_anything_is(crosswalk,
                                                           monkeypatch):
    """No transaction to roll back to. Discovering it at occupation 800
    leaves 799 behind and a non-zero exit."""
    # **The unwritable row is LAST.** First, the load raises on row one
    # whether or not the pre-flight ran, so "nothing was written" holds
    # either way — removing the pre-flight entirely stayed green until this
    # was reordered.
    monkeypatch.setattr(probe_cipsoc, "rows", lambda book, part: [
        HEADER,
        ["51.3801", "Registered Nursing.", "29-1141", "Registered Nurses"],
        ["01.0000", "Agriculture, General.", "19-1011", "Animal Scientists"],
        ["01.0001", "Bad.", "19-9999", """both " and ' quotes"""]])
    engine = Recorder({"p.cip_code": {"records": [["513801"]]}})
    with pytest.raises(Refused):
        loader.load(engine)
    assert not [s for s in engine.sent if "CREATE" in s], (
        f"wrote before discovering it could not finish: "
        f"{[s for s in engine.sent if 'CREATE' in s][:2]}")


def test_record_and_dry_run_are_refused_together(capsys):
    assert loader.main(["--record", "--dry-run"]) == 2
    assert "needs a real load" in capsys.readouterr().err


def test_an_unmeasurable_graph_is_refused_rather_than_read_as_empty():
    """`or 0` is how this class of guard fails open — `etl/scratch_engine.py`
    records it happening twice."""
    class Silent(Recorder):
        def scalar(self, statement):
            return None
    with pytest.raises(Refused, match="did not answer"):
        loader.in_the_graph(Silent())


def test_a_future_edition_is_read_not_silently_empty(crosswalk, monkeypatch):
    """**The edition was read dynamically; the columns were not.**
    `edition()` handles a CIP2030 workbook, but `mappings()` then looked up
    the literal `CIP2020Code` against that same header row, so every row fell
    out blank: `mappings_read: 0`, zero occupations, zero edges, **exit 0**,
    and a record saying the load succeeded against a named new edition.

    That inverted the claim that "the headings cannot change without the
    reader failing loudly". Columns are matched by MEANING now, through the
    probe's own `column_at`, which raises on a reshaped file for free.
    """
    future = [["CIP2030Code", "CIP2030Title", "SOC2028Code", "SOC2028Title"],
              ["01.0000", "Agriculture, General.", "19-1011", "Animal Scientists"],
              ["51.3801", "Registered Nursing.", "29-1141", "Registered Nurses"]]
    monkeypatch.setattr(probe_cipsoc, "rows", lambda book, part: future)
    read, which = loader.mappings()
    assert which == "CIP2030-SOC2028"
    assert len(read) == 2, "a future edition read as empty"
    assert {r["cip_code"] for r in read} == {"010000", "513801"}
    assert read[0]["soc_title"] == "Animal Scientists", "titles went missing"


def test_a_sheet_that_parses_to_nothing_is_refused(crosswalk, monkeypatch):
    """Mirrors `probe_cipsoc.measure()`, which refuses rather than reporting
    a zero it cannot explain."""
    monkeypatch.setattr(probe_cipsoc, "rows", lambda book, part: [
        ["CIP2020Code", "CIP2020Title", "SOC2018Code", "SOC2018Title"]])
    with pytest.raises(Refused, match="no mappings at all"):
        loader.mappings()


def test_a_reshaped_sheet_raises_rather_than_counting_the_wrong_column(
        crosswalk, monkeypatch):
    """`column_at` is the probe's own matcher and it raises when no column
    names a code. Returning `[]` would have been the quiet answer."""
    monkeypatch.setattr(probe_cipsoc, "rows", lambda book, part: [
        ["Something", "Else", "Entirely", "Here"], ["a", "b", "c", "d"]])
    with pytest.raises(Exception):
        loader.mappings()


def test_a_second_edition_creates_its_own_edge(crosswalk):
    """**The decision, pinned.** `Writer.edge`'s lookup was (tail, kind, head)
    only, so loading a later crosswalk edition found every overlapping pair,
    counted it `already_there`, and never wrote the new `source_edition` — it
    did not replace, it declined, which is the same loss wearing a different
    surprise.

    The property map participates in the check now: an edge carrying a
    different edition is a different edge, which is what
    `schema/edtech_kg.cypher` wants so Q43 can ask which edition said so.
    """
    from etl.graph_writer import Writer
    engine = Recorder({"count(r)": {"records": [[0]]}})
    writer = Writer(engine)
    writer.edge("PREPARES_FOR", ("Programme", "cip_code", "513801"),
                ("Occupation", "soc_code", "29-1141"),
                {"source_edition": "CIP2030-SOC2028"})
    lookups = [s for s in engine.sent if "count(r)" in s]
    assert lookups, engine.sent
    assert "r.source_edition = 'CIP2030-SOC2028'" in lookups[0], (
        f"the existence check ignores the edition, so a second edition would "
        f"be declined: {lookups[0]}")


def test_an_edge_with_no_properties_still_dedupes_on_endpoints(crosswalk):
    """The other direction — `load_education`'s AT and IN edges carry no
    properties and must keep matching on endpoints alone, or the spine load
    stops being idempotent."""
    from etl.graph_writer import Writer
    engine = Recorder({"count(r)": {"records": [[1]]}})
    writer = Writer(engine)
    writer.edge("AT", ("Completion", "id", "abc"), ("Institution", "unitid", "1"))
    assert writer.already_there == 1, "an unpropertied edge stopped matching"
    assert not [s for s in engine.sent if "CREATE" in s]

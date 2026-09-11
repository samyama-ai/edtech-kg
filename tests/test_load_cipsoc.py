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
    monkeypatch.setattr(loader.zipfile, "ZipFile", lambda path: None)


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


def test_every_occupation_loads_even_without_a_programme(crosswalk):
    """The occupations are the published vocabulary and stand on their own."""
    engine = Recorder({"p.cip_code": {"records": []}})
    summary = loader.load(engine)
    assert summary["occupations_in"] == 3
    assert summary["edges_issued"] == 0
    assert "29-1141" in " ".join(engine.sent)


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

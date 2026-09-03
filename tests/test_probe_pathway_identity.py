"""The pathway-identity probe, and the record it writes.

#85 asks which property can key `Pathway` once a second publisher exists. The
probe answers it by measuring, so these tests are about the measurement being
trustworthy rather than about the verdict: a probe that counted the wrong unit
would produce a confident number and a wrong schema decision behind it.

Every test drives stubbed transport. Nothing here reaches the network — the
figures in `docs/sources/pathway-identity-measured.json` came from a real run,
and a test that re-ran it would be measuring the Registry's uptime.
"""

import json
import pathlib

import pytest

from etl import probe_pathway_identity as probe
from etl.registry_read import MalformedSource
from tests.registry_stubs import paged, pathway

ROOT = pathlib.Path(__file__).resolve().parent.parent
RECORD = json.loads((ROOT / "docs" / "sources"
                     / "pathway-identity-measured.json").read_text("utf-8"))


# --- one(): the CTDL value shapes -------------------------------------------

@pytest.mark.parametrize("value, want", [
    ("https://x.test/a", "https://x.test/a"),           # bare
    (["https://x.test/a", "https://x.test/b"], "https://x.test/a"),
    ({"en-US": "https://x.test/a"}, "https://x.test/a"),
    ({"en": "https://x.test/a"}, "https://x.test/a"),
    ({"fr": "https://x.test/a"}, "https://x.test/a"),   # any language beats none
    ([{"en-US": "https://x.test/a"}], "https://x.test/a"),
    (None, None),
    ([], None),
    ({}, None),
    ("", None),
    ("   ", None),      # whitespace is absence, not a distinct key
    (7, None),          # a number is not an identifier
])
def test_one_reads_every_shape_a_ctdl_value_arrives_in(value, want):
    assert probe.one(value) == want


def test_a_blank_webpage_counts_as_absent_not_as_a_shared_key():
    """The trap this exists for: `""` is falsy but it is also EQUAL to itself.

    Counted as present, two blank webpages are one repeated value — so a field
    that is merely empty would be reported as evidence of a merge, which is the
    finding the verdict rests on.
    """
    nodes = [{"ceterms:subjectWebpage": ""} for _ in range(3)]
    got = probe.fitness(nodes, probe.WEBPAGE)
    assert (got["present"], got["absent"], got["collides"]) == (0, 3, 0)


# --- pathways(): what gets read ---------------------------------------------

def test_the_pathway_is_taken_by_type_not_by_position(monkeypatch):
    """Each record's `@graph` holds components alongside the pathway."""
    paged(monkeypatch, {1: [pathway(name="Welding", ctid="ce-a")]}, x_total=1)
    found = probe.pathways()
    assert [n["@type"] for n in found] == ["ceterms:Pathway"]
    assert found[0]["ceterms:ctid"] == "ce-a"


def test_every_page_is_read_and_accumulated(monkeypatch):
    """A stub that ignored the page number once made a twelve-page walk
    indistinguishable from reading one page twelve times."""
    paged(monkeypatch, {1: [pathway(ctid=f"ce-{i}") for i in range(50)],
                        2: [pathway(ctid=f"ce-b{i}") for i in range(48)]},
          x_total=98)
    assert len({n["ceterms:ctid"] for n in probe.pathways()}) == 98


def test_the_walk_stops_on_an_empty_page(monkeypatch):
    paged(monkeypatch, {1: [pathway(ctid="ce-a")], 2: []}, x_total=1)
    assert len(probe.pathways()) == 1


def test_a_body_that_is_not_a_list_is_reported_not_silently_skipped(monkeypatch):
    paged(monkeypatch, {1: {"error": "nope"}}, x_total=1)
    with pytest.raises(MalformedSource, match="page 1"):
        probe.pathways()


# --- fitness(): the unit the number counts ----------------------------------

def test_collides_counts_records_lost_not_values_repeated():
    """Kalyan's class, and the one this probe is most able to get wrong.

    Four pages published as 3, 2, 4 and 2 pathways means FOUR repeated values
    and SEVEN records lost to a merge. Reporting 4 would understate what is at
    stake by nearly half, and the verdict in the schema quotes this number.
    """
    shared = []
    for page, count in (("p1", 3), ("p2", 2), ("p3", 4), ("p4", 2)):
        shared += [{probe.WEBPAGE: f"https://x.test/{page}"}] * count
    got = probe.fitness(shared, probe.WEBPAGE)
    assert got["present"] == 11
    assert got["distinct"] == 4
    assert got["collides"] == 7, "must count records lost, not values repeated"
    assert got["shared_values"] == 4, "and the pages themselves are 4, not 7"


def test_absent_and_collides_are_independent():
    nodes = [{probe.WEBPAGE: "https://x.test/a"},
             {probe.WEBPAGE: "https://x.test/a"},
             {}]
    got = probe.fitness(nodes, probe.WEBPAGE)
    assert (got["records"], got["present"], got["absent"], got["collides"]) \
        == (3, 2, 1, 1)


@pytest.mark.parametrize("nodes, usable", [
    ([{"k": "a"}, {"k": "b"}], True),
    ([{"k": "a"}, {"k": "a"}], False),      # repeated
    ([{"k": "a"}, {}], False),              # absent
    ([{"k": "a"}, {"k": "a"}, {}], False),  # both
])
def test_usable_as_key_needs_present_on_all_and_distinct(nodes, usable):
    assert probe.fitness(nodes, "k")["usable_as_key"] is usable


def test_an_empty_population_is_not_reported_as_a_usable_key():
    """Vacuous truth: with no records, present == records == distinct == 0.

    A source that went dark would otherwise report both candidates as perfect
    keys and read as confirmation of whichever the schema already used.
    """
    assert probe.fitness([], "k")["usable_as_key"] is False


# --- hosts() ----------------------------------------------------------------

def test_hosts_are_lower_cased_so_one_host_is_not_two():
    nodes = [{probe.WEBPAGE: "https://Catalog.HCCS.edu/a"},
             {probe.WEBPAGE: "https://catalog.hccs.edu/b"},
             {}]
    assert probe.hosts(nodes) == {"distinct": 1,
                                  "top": {"catalog.hccs.edu": 2}}


# --- the record -------------------------------------------------------------

def test_the_record_carries_both_candidates_and_its_provenance():
    assert set(RECORD) >= {"_", "retrieved_at", "pathways", "candidates",
                           "webpage_hosts"}
    assert set(RECORD["candidates"]) == {probe.CTID, probe.WEBPAGE}


def test_the_recorded_arithmetic_closes():
    """Each block has to be internally consistent, or a hand-edit went in."""
    for name, got in RECORD["candidates"].items():
        assert got["present"] + got["absent"] == got["records"], name
        assert got["collides"] == got["present"] - got["distinct"], name
        # A merge needs at least one shared value per lost record at the
        # extreme, and never more shared values than lost records.
        assert got["shared_values"] <= got["collides"], name
        assert bool(got["shared_values"]) == bool(got["collides"]), name
        assert got["records"] == RECORD["pathways"], name


def test_the_record_still_says_neither_single_property_keys_both():
    """The one finding the schema decision rests on.

    If a future refresh shows `subjectWebpage` present and distinct on all of
    them, the composite key is no longer forced and #85 should be reopened
    rather than the record quietly updated.
    """
    webpage = RECORD["candidates"][probe.WEBPAGE]
    assert webpage["usable_as_key"] is False, (
        "subjectWebpage now keys every Registry pathway — reopen #85 rather "
        "than leaving the schema's reasoning resting on a stale record.")


def test_the_probe_writes_the_record_it_is_read_from(tmp_path, monkeypatch):
    """`--record` must write the shape the tests above read, and `_` must come
    from the writer rather than being carried over from an existing file."""
    paged(monkeypatch, {1: [pathway(ctid="ce-a", webpage="https://x.test/a")]},
          x_total=1)
    target = tmp_path / "written.json"
    monkeypatch.setattr(probe, "RECORD", target)
    assert probe.main(["--record"]) == 0

    written = json.loads(target.read_text("utf-8"))
    assert list(written)[:2] == ["_", "retrieved_at"]
    assert written["pathways"] == 1
    assert written["candidates"][probe.CTID]["usable_as_key"] is True


def test_an_unreachable_source_exits_two_and_writes_nothing(tmp_path,
                                                            monkeypatch):
    def dead(*a, **k):
        raise RuntimeError("no route to host")
    monkeypatch.setattr(probe, "pathways", dead)
    target = tmp_path / "unwritten.json"
    monkeypatch.setattr(probe, "RECORD", target)
    assert probe.main(["--record"]) == 2
    assert not target.exists(), "a failed run must not leave a record behind"

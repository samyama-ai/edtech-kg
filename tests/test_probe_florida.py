"""The Florida probe, and the census/sample distinction it rests on.

#55's answer is "zero courses", and the strength of that answer is entirely in
it being a CENSUS — fourteen `x-total` reads that reconcile to zero
unattributed — rather than a sample that happened to contain no courses. So
most of what follows tests the reconciliation and the refusals around it.

The field profile IS a sample and is reported as one; the test that matters
there is that the pages are drawn at a stride, because `fdoe`'s two publishers
differ and reading the first N pages gives a confidently wrong answer.

Nothing here reaches the network.
"""

import json
import pathlib

import pytest

from etl import probe_florida as probe
from etl.registry_read import MalformedSource
from tests.registry_stubs import paged

ROOT = pathlib.Path(__file__).resolve().parents[1]
RECORD = json.loads((ROOT / "docs" / "sources"
                     / "florida-registry-measured.json").read_text("utf-8"))


def totals(monkeypatch, whole, by_type):
    monkeypatch.setattr(
        probe, "total",
        lambda path, **k: whole if path.count("/") == 2
        else by_type.get(path.split("/")[2], 0))


# --- the census, and its reconciliation -------------------------------------

def test_the_breakdown_must_close_against_the_whole(monkeypatch):
    totals(monkeypatch, 10578, {"credential": 10241, "organization": 336,
                                "collection": 1})
    got = probe.census()
    assert got["records"] == 10578
    assert got["unattributed"] == 0
    assert got["by_type"]["course"] == 0


def test_an_unexplained_remainder_is_reported_not_hidden(monkeypatch):
    """A type nobody asked about must be loud.

    Reporting the parts as if they were the whole is the failure this repo
    keeps finding — the breakdown would still sum to something plausible.
    """
    totals(monkeypatch, 10578, {"credential": 10000})
    assert probe.census()["unattributed"] == 578


def test_a_type_that_answers_with_a_string_refuses_the_whole_breakdown(
        monkeypatch):
    """`total()` returns "secured" or "error 500" as strings. A breakdown with
    a hole in it must not be reported as a census."""
    monkeypatch.setattr(probe, "total",
                        lambda path, **k: 10578 if path.count("/") == 2
                        else ("secured" if "credential" in path else 0))
    with pytest.raises(RuntimeError, match="refusing to report a breakdown"):
        probe.census()


def test_a_community_with_no_reported_total_refuses(monkeypatch):
    monkeypatch.setattr(probe, "total", lambda path, **k: "no x-total header")
    with pytest.raises(RuntimeError, match="did not report a total"):
        probe.census()


def test_every_search_path_the_registry_exposes_is_asked_about():
    """The list is exhaustive on purpose: a type left out lands in
    `unattributed`, which is loud, rather than being silently absent."""
    assert "course" in probe.TYPES and "credential" in probe.TYPES
    assert len(probe.TYPES) >= 14
    assert len(set(probe.TYPES)) == len(probe.TYPES), "a duplicate double-counts"


# --- the sample, and why the stride matters ---------------------------------

@pytest.mark.parametrize("pages, wanted", [(205, 8), (100, 8), (9, 8), (3, 8)])
def test_the_sample_spreads_across_the_whole_result_set(pages, wanted):
    read = probe.spread(pages, wanted)
    assert read == sorted(set(read)), "pages must be unique and ordered"
    assert min(read) >= 1 and max(read) <= pages
    if pages > wanted:
        assert max(read) > pages // 2, (
            "reading the head is a sample of whatever sorts first — fdoe's "
            "page 1 is one publisher and carries none of ceterms:requires")


def test_a_short_result_set_is_read_whole():
    assert probe.spread(3, 8) == [1, 2, 3]


def test_the_profile_counts_nodes_not_envelopes(monkeypatch):
    envelope = {"decoded_resource": {"@graph": [
        {"@type": "ceterms:Certificate", "ceterms:ctid": "a",
         "ceterms:instructionalProgramType": [{"ceterms:codedNotation": "51.0904"}]},
        {"@type": "ceterms:Certificate", "ceterms:ctid": "b"}]}}
    paged(monkeypatch, {1: [envelope]}, x_total=2)
    got = probe.profile(population=2, sample_pages=1)
    assert got["sampled"] == 2
    assert got["field_coverage"]["ceterms:instructionalProgramType"] == 1


def test_a_node_without_a_ctid_is_not_counted(monkeypatch):
    """A `@graph` carries Place and ValueProfile nodes alongside the
    credential; counting them would inflate the denominator and deflate every
    coverage share."""
    envelope = {"decoded_resource": {"@graph": [
        {"@type": "ceterms:Certificate", "ceterms:ctid": "a"},
        {"@type": "ceterms:Place", "ceterms:postalCode": "32955"}]}}
    paged(monkeypatch, {1: [envelope]}, x_total=1)
    assert probe.profile(population=1, sample_pages=1)["sampled"] == 1


def test_an_empty_result_set_refuses_rather_than_reporting_zero_coverage(
        monkeypatch):
    paged(monkeypatch, {1: []}, x_total=0)
    with pytest.raises(ValueError, match="refusing to report coverage"):
        probe.profile(population=50, sample_pages=1)


def test_a_malformed_page_is_reported(monkeypatch):
    paged(monkeypatch, {1: {"error": "no"}}, x_total=50)
    with pytest.raises(MalformedSource, match="page 1"):
        probe.profile(population=50, sample_pages=1)


# --- the record, and the finding it carries ---------------------------------

def test_the_recorded_census_reconciles():
    assert RECORD["unattributed"] == 0
    assert sum(RECORD["by_type"].values()) == RECORD["records"]


def test_the_record_still_says_florida_published_no_courses():
    """The finding #55 rests on and `docs/scope.md` §3 depends on.

    If a refresh ever shows courses here, that is a genuinely new source and
    #55 should be reopened rather than the record quietly updated.
    """
    assert RECORD["by_type"]["course"] == 0, (
        "Florida now publishes courses to the Registry — reopen #55 and "
        "re-check docs/scope.md §3 rather than updating this record silently.")
    assert RECORD["by_type"]["learning_opportunity_profile"] == 0


def test_the_record_carries_the_cip_coverage_the_doc_quotes():
    got = RECORD["profile"]
    assert got["field_coverage"]["ceterms:instructionalProgramType"] == \
        got["sampled"], "the doc claims 100% CIP coverage over the sample"
    assert got["sampled"] >= 200, "too small a sample to quote a share from"

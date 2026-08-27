"""What a district's catalogue can join to — the measurement, not the sources.

Split out of `tests/test_probe_sced.py` when it passed the 500-line review
limit, alongside `etl/sced_reach.py`. Everything here drives a title against a
code; reading NCES's workbook and New York's export stays next door.

Both blockers this half has had were the same shape: which code a normalised
title resolves to. `normalise` collapses `Geometry` and `Geometry (Common
Core)` onto one key, and the answer used to be whichever row the sheet listed
last — so a New York state extension could be published as the SCED code a
district reaches, in the page's own list of matching courses.
"""

from __future__ import annotations

import pytest

from etl import sced_reach as probe


def test_programme_markers_are_stripped_so_the_match_is_a_best_case():
    """The reachability figure is the one the document leads with, so it must
    not understate what SCED could reach. `AICE Biology (AS Level)` gets its
    best chance against `Biology`."""
    assert probe.normalise("AICE Biology (AS Level)") == probe.normalise("Biology")
    assert probe.normalise("AP U.S. History") == probe.normalise("U S History")


def test_a_district_with_no_code_field_is_reported_as_carrying_none(monkeypatch):
    """The figure the whole probe exists for, and it had no test at all.

    The zero is what the schema recommendation rests on, so it has to mean
    "there is no field for a SCED code" and not "no text happened to be five
    digits". The earlier version scanned every string value on the record, so
    a course *titled* `12345` would have counted as a district publishing SCED
    — the right answer by the wrong route.
    """
    catalogue = {"courses": [
        {"title": "Algebra I", "url": "https://x/algebra-1"},
        # A title that is five digits. Under the old check this counted as a
        # published SCED code.
        {"title": "12345", "url": "https://x/12345"},
    ]}
    monkeypatch.setattr("etl.pwcs_source.read", lambda *a, **k: catalogue)
    got = probe.district_reach({"Algebra I": "02052"})

    assert got["sced_code_fields"] == [], (
        "a field was treated as a SCED code column when the record has none")
    assert got["publishes_sced_code"] == 0, (
        "a five-digit title was counted as a published SCED code")
    assert got["district_courses"] == 2
    assert got["reachable_by_name"] == 1


def test_two_courses_sharing_a_title_are_counted_once_each_way(monkeypatch):
    """`reachable_by_name` and `district_courses` must count the same thing.
    Keying the match on the raw title made the numerator a count of distinct
    titles and the denominator a count of rows, so the percentage disagreed
    with itself the moment a catalogue repeated a name."""
    catalogue = {"courses": [
        {"title": "Algebra I", "url": "https://x/a"},
        {"title": "Algebra I", "url": "https://x/b"},
    ]}
    monkeypatch.setattr("etl.pwcs_source.read", lambda *a, **k: catalogue)
    got = probe.district_reach({"Algebra I": "02052"})
    assert got["district_courses"] == 2
    assert got["reachable_by_name"] == 2, (
        "the second course with the same title vanished from the numerator "
        "while staying in the denominator")
    assert got["distinct_titles_matched"] == 1


def test_an_empty_catalogue_is_refused_rather_than_divided_by(monkeypatch):
    """The reach is printed as a percentage of the catalogue. An empty one gave
    a ZeroDivisionError traceback, where every other zero-result path in this
    file refuses with a message."""
    monkeypatch.setattr("etl.pwcs_source.read", lambda *a, **k: {"courses": []})
    with pytest.raises(probe.MalformedSource, match="refusing to report a"):
        probe.district_reach({"Algebra I": "02052"})


def test_a_course_with_two_code_fields_is_counted_once(monkeypatch):
    """`published` summed over (course × field) pairs while being reported as a
    count of courses, so a record carrying two code fields counted twice.

    The figure is the one the schema recommendation rests on, and it is a
    count of DISTRICTS PUBLISHING A CODE — the same units problem this figure
    was introduced to fix, one line down.
    """
    catalogue = {"courses": [
        {"title": "Algebra I", "sced_code": "02052", "state_code": "02052"},
        {"title": "Biology", "url": "https://x/bio"},
    ]}
    monkeypatch.setattr("etl.pwcs_source.read", lambda *a, **k: catalogue)
    got = probe.district_reach({"Algebra I": "02052"})

    assert sorted(got["sced_code_fields"]) == ["sced_code", "state_code"]
    assert got["publishes_sced_code"] == 1, (
        f"a course carrying two code fields was counted "
        f"{got['publishes_sced_code']} times in a figure reported as courses")


def test_a_state_extension_never_wins_a_title_a_sced_code_also_carries():
    """`Geometry` resolved to `02072CC` — a New York extension, not SCED.

    `normalise` strips parentheticals, so `Geometry` and `Geometry (Common
    Core)` collapse to one key, and the old dict comprehension was last-wins:
    whichever row came later in the sheet won. New York's `CC` and `L` codes
    are the state ADDING to the taxonomy, which the page says would overstate
    the reach if counted as alignment — and `Geometry` was in the page's own
    published list of matching courses.
    """
    resolved, ambiguous = probe.resolve_titles(
        {"Geometry": "02072", "Geometry (Common Core)": "02072CC"},
        {"02072CC"})

    assert resolved["geometry"] == "02072", (
        "a state extension was reported as the SCED code a district reaches")
    assert ambiguous == [], "one SCED code and one extension is not a tie"


def test_the_order_of_the_sheet_does_not_decide_which_code_a_title_gets():
    """Row order is not a measurement, and it decided this.

    Thirty-one of New York's normalised titles carry more than one code even
    after preferring the SCED one. Which one the published examples list
    reports was whichever row the sheet happened to put last.
    """
    one_way = probe.resolve_titles({"Art": "05151", "Art (Studio)": "05152"}, set())
    other_way = probe.resolve_titles({"Art (Studio)": "05152", "Art": "05151"}, set())

    assert one_way == other_way, "the answer depends on the order of the rows"
    assert one_way[0]["art"] == "05151", "the tie is not broken deterministically"
    assert one_way[1] == ["art"], (
        "a title with two SCED codes behind it was resolved silently rather "
        "than reported as ambiguous")


def test_the_strict_comparison_is_printed_rather_than_typed_into_the_page(monkeypatch):
    """`docs/sources/sced.md` quoted "58 rather than 67" as typed text, on a
    page whose first line says nothing on it is typed.

    The figure was correct — confirmed by hand-patching `normalise` — and
    nothing produced or regenerated it, so it could not go stale visibly. The
    probe measures both now.
    """
    from etl import pwcs_source

    monkeypatch.setattr(pwcs_source, "read", lambda: {"courses": [
        {"title": "Biology (AS Level)"}, {"title": "Chemistry"}]})

    got = probe.district_reach(
        {"Biology": "03051", "Chemistry": "03101"}, set())

    assert got["reachable_by_name"] == 2, (
        "the lenient rule should reach both, which is what makes it lenient")
    assert got["reachable_without_the_parenthetical_rule"] == 1, (
        "the strict comparison is not measured, so the page's claim that the "
        "headline is deliberately generous rests on nothing it prints")

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


def test_every_code_published_under_a_title_reaches_the_resolver():
    """The fix used to sit downstream of the thing that broke it.

    `new_york()["titles"]` was `{title: code}`, so New York's 2,012 rows
    collapsed to 1,839 entries and 173 codes were discarded before
    `resolve_titles` — the function whose whole job is choosing between the
    codes behind one title — could see any of them. A rule cannot be applied
    to a value the dict feeding it already threw away.
    """
    resolved, ambiguous = probe.resolve_titles(
        {"Geometry": ["02072", "02072CC"], "Algebra": ["02052"]}, {"02072CC"})

    assert resolved["geometry"] == "02072", (
        "the extension won, so the list of codes is not reaching the rule")
    assert resolved["algebra"] == "02052"
    assert ambiguous == [], "one SCED code and one extension is not a tie"


def test_a_title_that_normalises_to_nothing_is_dropped_not_bucketed():
    """`normalise` can return `""` — a title that is only a parenthetical or
    only programme markers, like `(Common Core)` or `AP`.

    An empty key matches every other title that normalises to empty, so it
    becomes a bucket that anything shaped like it falls into, and the code the
    bucket happens to hold is reported as the match.
    """
    resolved, _ = probe.resolve_titles(
        {"(Common Core)": ["01003CC"], "AP": ["99999"], "Biology": ["03051"]},
        set())

    assert "" not in resolved, (
        "an empty normalised title became a key, so any other title that "
        "normalises to empty now matches whatever code it holds")
    assert resolved == {"biology": "03051"}


def test_a_camelcase_code_field_is_not_missed():
    """The zero the schema recommendation rests on.

    Markers were matched against `f.lower()`, so `scedCode` matched via
    "sced" and `courseCode` did not — `"coursecode"` is not `"course_code"`.
    A district publishing its codes under a camelCase field would have been
    reported as publishing none, which is the finding the whole page turns on.
    """
    from etl import pwcs_source

    for field in ("courseCode", "course_code", "state-code", "SCED Code"):
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(pwcs_source, "read", lambda f=field: {"courses": [
                {"title": "Algebra I", f: "02052"}]})
            got = probe.district_reach({"Algebra I": ["02052"]}, set())
            assert got["sced_code_fields"] == [field], (
                f"{field!r} was not recognised as a code field, so a district "
                f"publishing SCED codes would report as publishing none")
            assert got["publishes_sced_code"] == 1


def test_a_catalogue_this_module_cannot_read_is_refused_at_every_level():
    """`c["title"]` raised KeyError from inside a comprehension. Every other
    failure in this module is a MalformedSource with a message.

    Three shapes, because the guard covered the innermost one only: a missing
    `courses` key, a course with no `title`, and a course whose title is
    blank. The last is the quiet one — a blank title normalises to the empty
    string, which matches every other blank title, so it does not fail, it
    over-matches.
    """
    from etl import pwcs_source

    for catalogue, expected in (
            ({"rows": []}, "no `courses` key"),
            ({"courses": [{"url": "x"}]}, "missing or empty `title`"),
            ({"courses": [{"title": "   "}]}, "missing or empty `title`"),
            ({"courses": [{"title": None}]}, "missing or empty `title`")):
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(pwcs_source, "read", lambda c=catalogue: c)
            with pytest.raises(probe.MalformedSource, match=expected):
                probe.district_reach({"Algebra I": ["02052"]}, set())


def test_the_two_meanings_of_a_zero_are_told_apart():
    """`publishes_sced_code: 0` means two different things and the schema
    recommendation rests on one of them.

    No field exists that could carry a code — the district has no concept of
    one — versus a field exists and every value in it fails to be a code,
    which is a district that has the concept and leaves it blank. Those are
    different arguments and the page makes only the first.
    """
    from etl import pwcs_source

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pwcs_source, "read",
                   lambda: {"courses": [{"title": "Algebra I"}]})
        got = probe.district_reach({"Algebra I": ["02052"]}, set())
    assert got["publishes_sced_code"] == 0 and got["no_field_to_carry_one"]

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pwcs_source, "read", lambda: {"courses": [
            {"title": "Algebra I", "sced_code": ""}]})
        got = probe.district_reach({"Algebra I": ["02052"]}, set())
    assert got["publishes_sced_code"] == 0, "an empty value is not a code"
    assert not got["no_field_to_carry_one"], (
        "a district with a SCED field it leaves blank was reported the same "
        "as one with no such field — a different finding entirely")


def test_a_field_that_describes_a_code_is_not_one():
    """`"coursecode" in flat` also matched `coursecodedescription` and
    `state_code_note`. A description landing in `code_fields` makes the count
    report a course as publishing a code it does not have."""
    from etl import pwcs_source

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pwcs_source, "read", lambda: {"courses": [
            {"title": "Algebra I", "coursecodedescription": "02052",
             "state_code_note": "02052"}]})
        got = probe.district_reach({"Algebra I": ["02052"]}, set())
    assert got["sced_code_fields"] == [], (
        f"{got['sced_code_fields']} describe a code rather than carrying one")
    assert got["publishes_sced_code"] == 0

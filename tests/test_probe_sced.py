"""The SCED probe, and the document that quotes it.

Two failures matter here and neither is a crash. The first is a probe that
reports a taxonomy as empty because the layout changed — an .xlsx served as an
HTML error page parses to zero rows and looks like a small answer. The second
is the document going stale: every figure on `docs/sources/sced.md` comes from
this probe, and a page that quotes a number the probe no longer produces is
worse than one that quotes nothing.

Built against workbooks constructed in the test, so no network and no committed
sample file — the same pattern as `tests/test_probe_cipsoc.py`.
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import pytest

from etl import probe_sced as probe
from tests.test_probe_cipsoc import workbook as cipsoc_workbook

DOC = Path(__file__).resolve().parents[1] / "docs" / "sources" / "sced.md"


def workbook(sheets: dict[str, list[list[str]]]) -> bytes:
    """The smallest valid .xlsx carrying the given sheets, as bytes.

    Delegated to `tests.test_probe_cipsoc.workbook` rather than built again
    here — the same reason the probe now calls that module's reader instead of
    carrying its own. That builder OMITS a cell whose value is `""`, which is
    what Excel does for a blank; the builder this file used to carry emitted
    every cell, so no fixture here could reach the reader's placement rule.
    """
    buffer = io.BytesIO()
    cipsoc_workbook(buffer, sheets)
    return buffer.getvalue()


class _Response:
    """The two methods `fetch` uses of a urlopen result."""

    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self) -> bytes:
        return self._payload


def test_a_page_served_as_html_is_refused_not_read_as_an_empty_taxonomy(monkeypatch):
    """A 200 carrying an error page is the failure that would otherwise be
    reported as "SCED has no courses" — a plausible-looking small number."""
    monkeypatch.setattr(probe.urllib.request, "urlopen",
                        lambda *a, **k: _Response(b"<!DOCTYPE html><html>404"))
    with pytest.raises(probe.MalformedSource, match="did not return a workbook"):
        probe.fetch(probe.MASTER)


def test_a_renamed_sheet_is_refused_with_what_it_did_find(monkeypatch):
    """NCES changing the layout must stop the probe, not shrink its answer."""
    book = workbook({"Overview": [["x"]], "Something Else": [["y"]]})
    monkeypatch.setattr(probe, "fetch", lambda url: book)
    with pytest.raises(probe.MalformedSource, match="no course sheet"):
        probe.master()


def test_a_sheet_that_parses_to_zero_rows_is_refused(monkeypatch):
    """An empty taxonomy is not a measurement."""
    book = workbook({"SCED 13.0": [["Course Title", "SCED Course Code"]]})
    monkeypatch.setattr(probe, "fetch", lambda url: book)
    # "no data rows" rather than "zero rows": a header-only sheet is caught by
    # the length guard now, which fires first and says what is missing. The
    # zero-rows message still covers a sheet with rows that all fail the
    # non-empty check.
    with pytest.raises(probe.MalformedSource, match="no data rows|zero rows"):
        probe.master()


def test_sheets_are_resolved_through_relationships_not_filename_order():
    """`sheet1.xml` is not reliably the first sheet. A reordered workbook would
    otherwise be read as a different one, silently."""
    book = zipfile.ZipFile(io.BytesIO(workbook(
        {"Overview": [["a"]], "SCED 13.0": [["Course Title"], ["Algebra"]]})))
    found = probe.sheets(book)
    assert set(found) == {"Overview", "SCED 13.0"}
    assert probe.rows(book, found["SCED 13.0"])[1] == ["Algebra"]


def test_a_state_suffix_is_not_counted_as_a_sced_code(monkeypatch):
    """New York publishes eleven codes with its own suffix — `01003CC` is a
    Common Core variant, New York extending SCED rather than using it.
    Counting them as aligned would overstate how portable a Course is, which is
    the one figure this probe exists to keep honest."""
    book = workbook({"All courses": [
        ["Course Code (Course ID)", "Course Code Description"],
        ["01001", "ELA I"],
        ["01003CC", "ELA III (Common Core)"],
    ]})
    monkeypatch.setattr(probe, "fetch", lambda url: book)
    got = probe.new_york()
    assert got["courses"] == 2
    assert got["sced_codes"] == 1, "the state extension was counted as a SCED code"
    assert got["state_extensions"] == ["01003CC"]


def test_a_sequence_column_would_be_reported_if_a_state_published_one(monkeypatch):
    """The claim on the page is that no state publishes the sequence element.
    A test that only ever sees files without one proves nothing, so this drives
    the case the data does not have."""
    book = workbook({"All courses": [
        ["Course Code (Course ID)", "Course Code Description", "Sequence of Course"],
        ["01001", "ELA I", "1 of 2"],
    ]})
    monkeypatch.setattr(probe, "fetch", lambda url: book)
    assert probe.new_york()["publishes_sequence"] is True


def test_programme_markers_are_stripped_so_the_match_is_a_best_case():
    """The reachability figure is the one the document leads with, so it must
    not understate what SCED could reach. `AICE Biology (AS Level)` gets its
    best chance against `Biology`."""
    assert probe.normalise("AICE Biology (AS Level)") == probe.normalise("Biology")
    assert probe.normalise("AP U.S. History") == probe.normalise("U S History")


def test_a_row_that_omits_a_cell_does_not_shift_the_columns(monkeypatch):
    """Excel omits a blank cell rather than writing an empty one, so a course
    with no title arrives as `<c r="A3">…</c><c r="C3">…</c>`. A reader that
    appends in document order would put column C's value where column B is
    read, and `sced_codes`, the extensions list and the title map would all
    stay plausible and be wrong, with nothing raising.

    This is why the probe uses `probe_cipsoc.rows`, which places cells by
    their `r` attribute, rather than a reader of its own.
    """
    book = workbook({"All courses": [
        ["Course Code (Course ID)", "Course Code Description", "Course Description"],
        ["01001", "ELA I", "an English course"],
        # No title. `01003CC` must still be read as the code, and the long
        # description must not slide into the title column.
        ["01003CC", "", "another English course"],
    ]})
    monkeypatch.setattr(probe, "fetch", lambda url: book)
    got = probe.new_york()
    assert got["courses"] == 2
    assert got["state_extensions"] == ["01003CC"], (
        "the untitled row's code was misread — the reader is placing cells by "
        "document order again")
    assert "another English course" not in got["titles"], (
        "the long description was read as a course title")


def test_a_reordered_export_is_refused_rather_than_read_positionally(monkeypatch):
    """The code and title are read by position, so the position is checked.
    New York restructuring its export would otherwise be read in silence and
    every figure below would be a count of the wrong column."""
    book = workbook({"All courses": [
        ["Course Code Description", "Course Code (Course ID)"],
        ["ELA I", "01001"],
    ]})
    monkeypatch.setattr(probe, "fetch", lambda url: book)
    with pytest.raises(probe.MalformedSource, match="has been restructured"):
        probe.new_york()


def test_the_element_split_is_read_from_the_sheets_own_banner_rows(monkeypatch):
    """What a SCED record may carry — and the failure that hid inside it.

    The previous version matched a hand-written set of prefixes and produced a
    right-looking count over the wrong members: it filed `Course Description`
    as an element when the sheet files it under attributes, and it missed
    `Available Carnegie Unit Credit` entirely. It missed ` Course Title` too,
    because that cell carries a leading space and the match was an exact
    equality.

    The fixture reproduces both traps.
    """
    book = workbook({
        "SCED 13.0": [["Course Title", "SCED Course Code"], ["Algebra I", "02052"]],
        "Elements and Attributes": [
            ["SCED Elements and Attributes"],
            ["Element Name", "Definition"],
            ["School Courses for the Exchange of Data Course Code", "The five-digit code."],
            ["Available Carnegie Unit Credit", "Measured in Carnegie units."],
            ["School Courses for the Exchange of Data Sequence of Course",
             "Where a course lies when it is part of a consecutive sequence of courses."],
            ["Attribute Name", "Definition"],
            [" Course Title", "The descriptive name given to a course."],
            ["Course Description", "A description of the course content."],
        ]})
    monkeypatch.setattr(probe, "fetch", lambda url: book)
    got = probe.master()

    assert got["elements"] == [
        "School Courses for the Exchange of Data Course Code",
        "Available Carnegie Unit Credit",
        "School Courses for the Exchange of Data Sequence of Course",
    ], "the element list is not the sheet's own"
    assert "Available Carnegie Unit Credit" in got["elements"], (
        "an element with no SCED prefix was dropped")
    assert "Course Description" in got["attributes"], (
        "an attribute was counted as an element")
    assert "Course Title" in got["attributes"], (
        "the leading space on ' Course Title' lost the row again")
    assert got["sequence_element"] and "consecutive sequence" in got["sequence_element"]


def test_an_elements_sheet_whose_banners_changed_is_refused(monkeypatch):
    """The split rests on two banner rows. If NCES renames them the answer is
    not "zero elements" — it is that the layout changed."""
    book = workbook({
        "SCED 13.0": [["Course Title", "SCED Course Code"], ["Algebra I", "02052"]],
        "Elements and Attributes": [["Field"], ["Something", "else"]]})
    monkeypatch.setattr(probe, "fetch", lambda url: book)
    with pytest.raises(probe.MalformedSource, match="banner rows"):
        probe.master()


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


def test_the_document_quotes_only_figures_the_probe_produces():
    """Every figure on `docs/sources/sced.md` comes from the probe. The ones
    that would go stale first are the version and the two counts the argument
    rests on, so those are pinned by name rather than by value — a changed
    figure fails here instead of being quoted for another month."""
    page = DOC.read_text(encoding="utf-8")
    # ANCHORED. `"791"` matched `**1,791**` on the version row, so the figure
    # it meant to guard — `PWCS courses loaded | **791**` — was unpinned: the
    # assertion passed on a different number entirely. Same for the bare
    # `2,012` and `2,001`, which the rows below now pin in place.
    for claim in ("SCED 13.0",
                  "| Courses | **1,791** |",
                  "| Rows in the sheet | **2,012** |",
                  "| Five-digit SCED codes | **2,001** |",
                  "| PWCS courses loaded | **791** |",
                  "67 — 8%",
                  # The element/attribute split. Pinned because the page now
                  # quotes the two counts, and a figure on the page that
                  # nothing guards is the drift this test exists to stop.
                  "Elements a record may carry | **6**",
                  "Attributes it may also carry | **17**"):
        assert claim in page, f"the page no longer states {claim!r}"
    assert "Publishing a SCED code | **0**" in page, (
        "the page no longer states that the district publishes no SCED code — "
        "which is the finding the schema decision rests on")


def test_the_document_does_not_claim_sced_solves_prerequisites():
    """The sequence element's name invites exactly that conclusion, and the
    page exists partly to refuse it."""
    page = DOC.read_text(encoding="utf-8").lower()
    assert "part n of m" in page or "part 'n' of 'm'" in page, (
        "the page no longer explains what the sequence element means")
    assert re.search(r"not a (relationship|prerequisite) between", page), (
        "the page no longer says the sequence element is not a prerequisite")


def test_a_repeated_course_code_does_not_make_the_table_stop_adding_up(monkeypatch):
    """`courses` and `sced_codes` counted ROWS while `state_extensions` counted
    distinct codes, so the printed lines reconciled against each other only
    because this file happens to carry no repeated extension code.

    A catalogue that repeats one produced `courses` larger than
    `sced_codes + state_extensions`, with nothing on the page saying why.
    """
    book = workbook({"All courses": [
        ["Course Code (Course ID)", "Course Code Description"],
        ["01001", "ELA I"],
        ["01003CC", "ELA III (Common Core)"],
        # The same extension code twice — two rows, one code.
        ["01003CC", "ELA III (Common Core), second listing"],
    ]})
    monkeypatch.setattr(probe, "fetch", lambda url: book)
    got = probe.new_york()

    assert got["rows"] == 3, "the row count no longer reports rows"
    assert got["courses"] == 2, "the course count is still counting rows"
    assert got["courses"] == got["sced_codes"] + len(got["state_extensions"]), (
        f"the table does not add up: {got['courses']} courses against "
        f"{got['sced_codes']} SCED codes and "
        f"{len(got['state_extensions'])} extensions")


def test_a_sheet_whose_header_row_starts_blank_is_refused(monkeypatch):
    """`header[0]` was read before anything checked it had content.

    The review described this as an IndexError on a blank first row. Driven,
    that exact case does not reach it — `probe_cipsoc.rows` drops a row with no
    values at all, so an entirely blank row never becomes `body[0]`. What DOES
    reach it is a header whose first cell is empty and whose later cells are
    not: the reader pads, so `header[0]` is `""` rather than missing, and the
    column check then compares an empty string and reports a restructured
    export in a message about column names.

    The guard is worth having either way, and this is the shape that gets
    there.
    """
    book = workbook({"All courses": [
        ["", "Course Code Description", "Notes"],
        ["01001", "ELA I", "x"],
    ]})
    monkeypatch.setattr(probe, "fetch", lambda url: book)
    with pytest.raises(probe.MalformedSource, match="opens with a blank row"):
        probe.new_york()


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


def test_the_master_sheet_gets_the_same_blank_header_guard_as_new_york(monkeypatch):
    """The guard reached one function and not its neighbour.

    `new_york()` was given a blank-header check last round; `master()` reads
    `header[0]` the same way, in the same file, and did not get one — so a
    sheet whose first column is empty raised IndexError from inside the check
    meant to report a layout change.
    """
    book = workbook({"SCED 13.0": [["", "SCED Course Code", "Notes"],
                                   ["Algebra I", "02052", "x"]]})
    monkeypatch.setattr(probe, "fetch", lambda url: book)
    with pytest.raises(probe.MalformedSource, match="blank first column"):
        probe.master()


def test_the_document_pins_are_anchored_to_their_own_rows():
    """The pins were bare substrings, and one of them matched the wrong row.

    `"791"` matched `**1,791**` on the version row, so `PWCS courses loaded |
    **791**` — the figure the assertion existed to guard — was never checked.
    A guard that passes on a different number is worse than no guard, because
    it reads as coverage.
    """
    page = DOC.read_text(encoding="utf-8")

    # The trap, made explicit: the SCED total contains the PWCS figure.
    assert "1,791" in page and "**791**" in page
    assert page.count("791") >= 2, "the two figures no longer coexist on the page"

    # So each pin names its row.
    for row in ("| Courses | **1,791** |",
                "| PWCS courses loaded | **791** |"):
        assert row in page, f"the page no longer carries the row {row!r}"


def test_the_new_york_table_is_a_table_and_not_prose():
    """A paragraph inserted mid-table orphaned the last row.

    `| Publishes a sequence column | **No** |` ended up after an intervening
    paragraph, so it rendered as literal text — and it is the section's
    headline answer. A broken table is invisible in a diff and obvious on the
    page.
    """
    page = DOC.read_text(encoding="utf-8")
    lines = page.splitlines()
    sequence = next(i for i, l in enumerate(lines)
                    if l.startswith("| Publishes a sequence column"))
    assert lines[sequence - 1].startswith("|"), (
        f"the sequence row is orphaned — the line above it is prose "
        f"({lines[sequence - 1][:60]!r}), so the row renders as literal text")

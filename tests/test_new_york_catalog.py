"""Reading New York's Comprehensive Course Catalog.

Split from `tests/test_probe_sced.py` alongside `etl/new_york_catalog.py`, on
the boundary the probe's own docstring draws: NCES publishes the taxonomy, New
York publishes the one state directory keyed to it, and reading them are two
jobs.

The failure this half guards is a count that stays plausible while being
wrong — a state extension counted as a SCED code, a blank cell shifting every
column after it, a published code discarded before anything can choose it.
"""

from __future__ import annotations

import io
import pathlib

import pytest

from etl import new_york_catalog as catalog
from etl import probe_sced as probe
from tests.workbook_support import workbook as cipsoc_workbook

DOC = pathlib.Path(__file__).resolve().parents[1] / "docs" / "sources" / "sced.md"


def workbook(sheets: dict[str, list[list[str]]]) -> bytes:
    """An .xlsx of these sheets, as bytes — the same builder every probe's
    tests use, so two suites cannot disagree about what a workbook is."""
    buffer = io.BytesIO()
    cipsoc_workbook(buffer, sheets)
    return buffer.getvalue()


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
    got = probe.new_york(probe.fetch(probe.NEW_YORK))
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
    assert probe.new_york(probe.fetch(probe.NEW_YORK))["publishes_sequence"] is True


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
    got = probe.new_york(probe.fetch(probe.NEW_YORK))
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
        probe.new_york(probe.fetch(probe.NEW_YORK))


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
        probe.new_york(probe.fetch(probe.NEW_YORK))


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
    got = probe.new_york(probe.fetch(probe.NEW_YORK))

    assert got["rows"] == 3, "the row count no longer reports rows"
    assert got["courses"] == 2, "the course count is still counting rows"
    assert got["courses"] == got["sced_codes"] + len(got["state_extensions"]), (
        f"the table does not add up: {got['courses']} courses against "
        f"{got['sced_codes']} SCED codes and "
        f"{len(got['state_extensions'])} extensions")


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


def test_no_published_code_is_dropped_before_the_resolver_sees_it():
    """`new_york()["titles"]` was `{title: code}` and lost the duplicates.

    New York's 2,012 rows collapsed to 1,839 entries, so 173 codes were gone
    before `resolve_titles` — the function whose whole job is choosing between
    the codes behind one title — could see any of them. The rule was applied
    downstream of the step that made it unnecessary, which is why the fix
    looked complete and was not.

    Asserted on the count of CODES, not of titles: a title map that keeps one
    code per title has the same number of titles and is exactly the defect.
    """
    rows = [["02072", "Geometry"],
            ["02072CC", "Geometry"],
            ["02052", "Algebra I"],
            ["", "No code"],
            ["03051", ""]]

    titles = catalog._titles(rows)
    assert set(titles) == {"Geometry", "Algebra I", "No code"}, (
        "a row with no title must be dropped; one with no code must not")
    assert sum(len(codes) for codes in titles.values()) == 4, (
        "a published code was discarded before anything could choose between "
        "them — the title map is keyed by title and keeping only one")
    assert titles["Geometry"] == ["02072", "02072CC"], (
        "both codes for one title must survive, sorted so the value does not "
        "depend on the order of the sheet")

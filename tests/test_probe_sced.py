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

DOC = Path(__file__).resolve().parents[1] / "docs" / "sources" / "sced.md"


def workbook(sheets: dict[str, list[list[str]]]) -> bytes:
    """The smallest valid .xlsx carrying the given sheets."""
    strings: list[str] = []

    def cell(value, col, row):
        if value not in strings:
            strings.append(value)
        return (f'<c r="{chr(65 + col)}{row}" t="s">'
                f'<v>{strings.index(value)}</v></c>')

    parts, rels, entries = [], [], []
    for i, (name, rows) in enumerate(sheets.items(), 1):
        body = "".join(
            f'<row r="{r}">' + "".join(cell(v, c, r) for c, v in enumerate(cells)) + "</row>"
            for r, cells in enumerate(rows, 1))
        entries.append((f"xl/worksheets/sheet{i}.xml",
                        '<?xml version="1.0"?><worksheet xmlns="http://schemas.'
                        'openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
                        + body + "</sheetData></worksheet>"))
        parts.append(f'<sheet name="{name}" sheetId="{i}" r:id="rId{i}"/>')
        rels.append(f'<Relationship Id="rId{i}" Target="worksheets/sheet{i}.xml" '
                    'Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                    'relationships/worksheet"/>')

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as book:
        book.writestr("xl/workbook.xml",
                      '<?xml version="1.0"?><workbook xmlns="http://schemas.'
                      'openxmlformats.org/spreadsheetml/2006/main" xmlns:r='
                      '"http://schemas.openxmlformats.org/officeDocument/2006/'
                      'relationships"><sheets>' + "".join(parts) + "</sheets></workbook>")
        book.writestr("xl/_rels/workbook.xml.rels",
                      '<?xml version="1.0"?><Relationships xmlns="http://schemas.'
                      'openxmlformats.org/package/2006/relationships">'
                      + "".join(rels) + "</Relationships>")
        book.writestr("xl/sharedStrings.xml",
                      '<?xml version="1.0"?><sst xmlns="http://schemas.'
                      'openxmlformats.org/spreadsheetml/2006/main">'
                      + "".join(f"<si><t>{s}</t></si>" for s in strings) + "</sst>")
        for path, xml in entries:
            book.writestr(path, xml)
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
    with pytest.raises(probe.MalformedSource, match="zero rows"):
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


def test_the_document_quotes_only_figures_the_probe_produces():
    """Every figure on `docs/sources/sced.md` comes from the probe. The ones
    that would go stale first are the version and the two counts the argument
    rests on, so those are pinned by name rather than by value — a changed
    figure fails here instead of being quoted for another month."""
    page = DOC.read_text(encoding="utf-8")
    for claim in ("SCED 13.0", "1,791", "2,012", "2,001", "791", "67 — 8%"):
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

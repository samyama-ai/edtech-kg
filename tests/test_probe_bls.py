"""Parsing the published table, and the coverage arithmetic.

The network is stubbed. Under test: reading the table BLS publishes, and the
coverage measurement against the crosswalk — including the three-way split of
what BLS does not carry, which exists so a structural exclusion does not read as
a data gap.

Access, the OEWS release search and the document checks are in
`tests/test_probe_bls_access.py`. Split at 545 lines, when review skipped the
whole file as too large to read. The shared table fixture is in
`tests/bls_fixtures.py`.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from etl import bls_access as access
from etl import probe_bls as probe
from tests.bls_fixtures import page, row, serve


# --------------------------------------------------------------------------
# parsing
# --------------------------------------------------------------------------

def test_the_table_is_read_despite_uppercase_tags(monkeypatch):
    """BLS emits <TR>/<TD>. A lowercase-only pattern finds nothing and reports
    zero occupations from a page that has 800."""
    serve(monkeypatch, page(row("13-2011"), row("29-1141")))
    assert probe.projections()["occupations"] == 2


def test_the_all_occupations_total_is_not_an_occupation(monkeypatch):
    """`00-0000` is the total row. Counting it inflates the denominator and
    puts a fictional occupation in the coverage set."""
    serve(monkeypatch, page(row("00-0000", "Total, all occupations"), row("13-2011")))
    result = probe.projections()
    assert result["occupations"] == 1
    assert "00-0000" not in result["codes"]


def test_the_no_match_sentinel_is_filtered_by_the_reader(tmp_path, monkeypatch):
    """`99-9999` is the crosswalk's explicit NO MATCH row — a CIP that maps to
    nothing. It has to be dropped by `crosswalk_soc()` itself.

    The first version of this test pre-subtracted the sentinel from its own
    fixture, so it never reached the code under test and passed with the filter
    deleted."""
    def cell(value):
        return f'<c t="inlineStr"><is><t>{value}</t></is></c>'

    sheet = ("<worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/"
             "2006/main\"><sheetData>"
             f"<row>{cell('CIP Code')}{cell('SOC Code')}</row>"
             f"<row>{cell('11.0101')}{cell('13-2011')}</row>"
             f"<row>{cell('01.0508')}{cell('99-9999')}</row>"
             "</sheetData></worksheet>")
    book = tmp_path / "crosswalk.xlsx"
    with zipfile.ZipFile(book, "w") as z:
        z.writestr("xl/workbook.xml",
                   '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/'
                   '2006/main"><sheets><sheet name="CIP-SOC" r:id="rId1" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/'
                   'relationships"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/'
                   '2006/relationships"><Relationship Id="rId1" '
                   'Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr("xl/sharedStrings.xml",
                   '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/'
                   '2006/main"></sst>')
        z.writestr("xl/worksheets/sheet1.xml", sheet)

    monkeypatch.setattr(probe, "CROSSWALK", book)
    found = probe.crosswalk_soc()
    assert "13-2011" in found
    assert "99-9999" not in found, "the NO MATCH sentinel reached the coverage set"


def test_a_missing_field_is_not_counted_as_present(monkeypatch):
    serve(monkeypatch, page(row("13-2011", wage="-", education="-")))
    present = probe.projections()["field_present"]
    assert present["Median Annual Wage"] == 0
    # By pattern, not by year: the heading rolls with each release.
    employment = [f for f in present if f.startswith("Employment 2")]
    assert employment, present
    assert all(present[f] == 1 for f in employment), present


def test_a_page_without_the_heading_is_malformed(monkeypatch):
    """A layout change would otherwise be reported as zero occupations, which
    reads as "BLS publishes nothing" rather than "the parser broke"."""
    serve(monkeypatch, "<html><TR><TD>something else</TD></TR></html>")
    with pytest.raises(probe.MalformedSource, match="Occupation Code"):
        probe.projections()


def test_a_table_with_no_occupations_is_refused(monkeypatch):
    serve(monkeypatch, page())
    with pytest.raises(ValueError, match="refusing"):
        probe.projections()


# --------------------------------------------------------------------------
# coverage — the measurement the issue turns on
# --------------------------------------------------------------------------

def cover(monkeypatch, bls_codes, crosswalk_codes):
    serve(monkeypatch, page(*[row(c) for c in bls_codes]))
    monkeypatch.setattr(probe, "crosswalk_soc", lambda: set(crosswalk_codes))
    monkeypatch.setattr(access, "head", lambda url: {"status": 200, "bytes": 1, "is_file": True})
    monkeypatch.setattr(access, "attempt",
                        lambda url, agent=None: {"status": 200 if agent else 403})
    return probe.probe(quiet=True)


def test_coverage_is_measured_against_the_crosswalk_not_the_table(monkeypatch):
    """800 national rows is not the same as covering the occupations a
    programme can reach. The denominator is the crosswalk."""
    result = cover(monkeypatch, ["13-2011", "29-1141", "99-9999"], ["13-2011", "41-1011"])
    assert result["crosswalk_soc_codes"] == 2
    assert result["crosswalk_codes_covered"] == 1


def test_a_military_code_is_not_reported_as_a_data_gap(monkeypatch):
    """BLS does not project military occupations at all. Counting that as a
    coverage failure makes a structural exclusion look like missing data."""
    result = cover(monkeypatch, ["13-2011"], ["13-2011", "55-1011", "55-2011"])
    assert result["missing_military"] == 2
    assert result["missing_outright"] == []


def test_a_code_carried_only_at_the_broad_level_is_separated(monkeypatch):
    """13-1021 is absent but 13-1020 is present — the answer exists, coarser.
    That is a different fact from the occupation not being covered."""
    result = cover(monkeypatch, ["13-1020"], ["13-1021", "13-1022"])
    assert result["missing_but_broad_parent_carried"] == 2
    assert result["missing_outright"] == []
    assert result["answerable_including_broad_parent"] == 2


def test_a_code_absent_outright_is_named(monkeypatch):
    """Named, not counted — a reader can check which occupations we cannot
    answer for."""
    result = cover(monkeypatch, ["13-2011"], ["13-2011", "21-1011"])
    assert result["missing_outright"] == ["21-1011"]


def test_the_three_causes_account_for_every_missing_code(monkeypatch):
    """The three add to the total AND name different codes.

    The sum alone cannot see double-counting: a code classified as both
    military and absent inflates the sum, and a fourth code lost entirely
    deflates it by the same one — the arithmetic balances and both faults are
    invisible. So the categories are checked for overlap by name."""
    result = cover(monkeypatch, ["13-1020", "13-2011"],
                   ["13-2011", "13-1021", "55-1011", "21-1011"])
    assert (result["missing_military"]
            + result["missing_but_broad_parent_carried"]
            + len(result["missing_outright"])) == result["crosswalk_codes_missing"]
    # Each cause is a different code. Only `missing_outright` is named in the
    # result, so the other two are reconstructed from the same inputs the probe
    # had — which is what makes the overlap checkable at all.
    absent = set(result["missing_outright"])
    assert absent == {"21-1011"}, result["missing_outright"]
    assert not absent & {"55-1011"}, "a military code is also counted as absent"
    assert not absent & {"13-1021"}, "a rolled-up code is also counted as absent"
    assert result["missing_military"] == 1 and \
        result["missing_but_broad_parent_carried"] == 1, result


def test_no_crosswalk_locally_does_not_claim_zero_coverage(monkeypatch, tmp_path):
    """A missing local file must not report as "BLS covers none of them".

    The file is made ABSENT rather than `crosswalk_soc` being stubbed to
    return nothing. Stubbing the function is stubbing the code under test:
    delete the `if not CROSSWALK.exists()` guard and the stub still returns an
    empty set, so the test passes on the defect it was written for.
    """
    monkeypatch.setattr(probe, "CROSSWALK", tmp_path / "not-here.xlsx")
    serve(monkeypatch, page(row("13-2011")))
    monkeypatch.setattr(access, "head",
                        lambda url: {"status": 200, "bytes": 1, "is_file": True})
    monkeypatch.setattr(access, "attempt", lambda url, agent=None: {"status": 200})
    result = probe.probe(quiet=True)

    assert result["crosswalk_soc_codes"] == 0
    assert result["crosswalk_codes_covered"] == 0
    # The ratio is the thing a reader would quote, and 0/0 must not render as
    # a percentage at all — "BLS covers 0%" is a claim; "we have no crosswalk
    # here" is the fact.
    assert result["crosswalk_codes_missing"] == 0, (
        "with no crosswalk there is nothing measured as missing either")




def test_next_releases_employment_headings_are_read_not_refused(monkeypatch):
    """BLS republishes this table on a rolling decade: the 2024-34 projections
    become 2025-35. Headings pinned to the literal years turn that into a hard
    `MalformedSource` — reported as BLS having stopped publishing employment,
    when BLS had done nothing but publish again.

    The fixture is renamed to the NEXT release rather than today's, because a
    test driven with today's headings passes whether the years are matched by
    pattern or pinned. This one cannot.
    """
    future = page(row("13-2011")).replace(
        "Employment 2024", "Employment 2025").replace(
        "Employment 2034", "Employment 2035")
    serve(monkeypatch, future)

    result = probe.projections()
    assert result["occupations"] == 1
    present = result["field_present"]
    assert present.get("Employment 2025") == 1, present
    assert present.get("Employment 2035") == 1, present
    assert "Employment 2024" not in present, \
        "a year that is no longer published is still being reported"


def test_a_table_with_no_dated_employment_column_is_a_layout_change(monkeypatch):
    """The other half: matching by pattern must not become matching nothing.
    A table that drops the employment columns entirely is a layout change and
    has to say so, not report employment coverage as zero."""
    gutted = page(row("13-2011")).replace(
        "Employment 2024", "Headcount").replace("Employment 2034", "Outlook")
    serve(monkeypatch, gutted)
    with pytest.raises(probe.MalformedSource, match="dated Employment"):
        probe.projections()


def workbook(path, sheet_name, table):
    """A real .xlsx the real reader can open — not a stubbed `rows`/`sheets`.

    Stubbing the readers would stub the code under test: the whole question is
    which CELLS `crosswalk_soc` reads out of a sheet.
    """
    def cell(value):
        return f'<c t="inlineStr"><is><t>{value}</t></is></c>'

    body = "".join("<row>" + "".join(cell(v) for v in row) + "</row>" for row in table)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/workbook.xml",
                   '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/'
                   f'2006/main"><sheets><sheet name="{sheet_name}" r:id="rId1" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/'
                   'relationships"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/'
                   '2006/relationships"><Relationship Id="rId1" '
                   'Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr("xl/sharedStrings.xml",
                   '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/'
                   '2006/main"></sst>')
        z.writestr("xl/worksheets/sheet1.xml",
                   '<worksheet xmlns="http://schemas.openxmlformats.org/'
                   'spreadsheetml/2006/main"><sheetData>' + body +
                   "</sheetData></worksheet>")
    return path


def test_the_reachable_set_reads_the_soc_column_not_every_cell(tmp_path, monkeypatch):
    """`crosswalk_soc` scanned every cell in every sheet, so any `NN-NNNN`
    string anywhere in the workbook joined the denominator — a note, a page
    range, a phone fragment. It reads the SOC column named by each sheet's own
    header now.

    Measured against the real file the two agree exactly at 867, so this
    changed the SHAPE and not the number. Driven with a SOC-shaped string
    sitting OUTSIDE the SOC column, which the real file does not contain —
    the only reason the defect never fired.
    """
    book = workbook(tmp_path / "crosswalk.xlsx", "CIP-SOC", [
        ["CIP2020Code", "CIP2020Title", "SOC2018Code", "SOC2018Title"],
        # A cell that IS a SOC code, in a column that is not the SOC column.
        # `fullmatch` needs the whole cell, so "note: see 55-1234" would not
        # have exercised anything — the first version of this test used that
        # and passed with the fix removed.
        ["55-1234", "Agriculture, General.", "19-1011", "Animal Scientists"],
        ["01.0001", "Agriculture", "99-9999", "NO MATCH"],
    ])
    monkeypatch.setattr(probe, "CROSSWALK", book)
    got = probe.crosswalk_soc()
    assert got == {"19-1011"}, got
    assert "55-1234" not in got, "a SOC-shaped string outside the SOC column was counted"
    assert "99-9999" not in got, "the NO MATCH sentinel reached the reachable set"


def test_a_sheet_with_no_soc_column_contributes_nothing_rather_than_everything():
    """The File Guide sheet is prose. Falling back to scanning every cell when
    no SOC column is found would put the prose back in the denominator."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        book = workbook(Path(tmp) / "b.xlsx", "File Guide", [
            ["File Name", "Description"],
            ["CIP-SOC", "crosswalks 2020 CIP to 2018 SOC, e.g. 19-1011"],
        ])
        original = probe.CROSSWALK
        probe.CROSSWALK = book
        try:
            assert probe.crosswalk_soc() == set()
        finally:
            probe.CROSSWALK = original


def test_a_renamed_header_is_refused_before_the_rows_are_walked(monkeypatch):
    """The refusal belongs where the fault is detectable. It was raised after
    ~800 rows had been read and scored against columns that were not there."""
    walked = []
    original = probe.SOC_CODE

    class Counting:
        def fullmatch(self, value):
            walked.append(value)
            return original.fullmatch(value)

    gutted = page(row("13-2011")).replace("Median Annual Wage", "Pay")
    serve(monkeypatch, gutted)
    monkeypatch.setattr(probe, "SOC_CODE", Counting())
    with pytest.raises(probe.MalformedSource, match="Median Annual Wage"):
        probe.projections()
    assert not walked, "rows were walked before the header was checked"

"""The crosswalk probe, tested against workbooks built in the test.

No network and no sample file committed. Each test builds the smallest .xlsx
that exercises one behaviour, which also documents what the probe assumes about
the format.

The failure that matters here is the same one as in `test_probe_education.py`:
not crashing, but reporting a number that is not a measurement. A probe that
reads the wrong sheet, or the wrong column, answers confidently and wrongly.
"""

import zipfile

import pytest

from etl import probe_cipsoc as probe
from tests.workbook_support import workbook


def complete(tmp_path, shared=True):
    """A workbook shaped like the real one: title block, then headers, then rows."""
    return workbook(tmp_path / "cw.xlsx", {
        "File Guide": [["ignore me"]],
        "CIP-SOC": [
            ["2020 CIP / 2018 SOC Crosswalk"], [],
            ["CIP2020Code", "CIP2020Title", "SOC2018Code", "SOC2018Title"],
            ["01.0101", "Agriculture", "11-9013", "Farm Manager"],
            ["01.0101", "Agriculture", "45-1011", "Supervisor"],
            ["11.0701", "Computer Science", "15-1252", "Developer"],
        ],
        "Unmatched CIP Codes": [["Unmatched"], ["CIP2020Code"], ["99.9999"], ["98.8888"]],
        "Unmatched SOC Codes": [["Unmatched"], ["SOC2018Code"], ["55-1011"]],
    }, shared=shared)


def test_counts_distinct_codes_not_rows(tmp_path):
    """Three mappings but only two programmes — the first CIP appears twice.
    Counting rows as programmes would overstate coverage."""
    r = probe.probe(complete(tmp_path), quiet=True)
    assert r["mappings"] == 3
    assert r["distinct_cip"] == 2
    assert r["distinct_soc"] == 3


def test_unmatched_codes_are_counted_from_their_own_sheets(tmp_path):
    """These are the honest part of the crosswalk — programmes that map to no
    occupation at all. Losing them would overstate what the graph can answer."""
    r = probe.probe(complete(tmp_path), quiet=True)
    assert r["unmatched_cip"] == 2
    assert r["unmatched_soc"] == 1


def test_inline_strings_are_read_as_well_as_shared(tmp_path):
    """Excel writes a shared-string table; other exporters write inline. A probe
    that read only one would report zero for a file that is perfectly valid."""
    r = probe.probe(complete(tmp_path, shared=False), quiet=True)
    assert r["mappings"] == 3 and r["distinct_cip"] == 2


def test_the_header_row_is_found_below_a_title_block(tmp_path):
    """NCES puts a title and a blank line above the headings. Assuming row 1
    would make every column lookup fail, or worse, succeed on the wrong row."""
    r = probe.probe(complete(tmp_path), quiet=True)
    assert r["mappings"] == 3


def test_columns_are_matched_by_name_not_position(tmp_path):
    """Column order is not a contract. Swapping them must not swap the counts."""
    p = workbook(tmp_path / "swapped.xlsx", {
        "CIP-SOC": [["title"], ["SOC2018Code", "SOC2018Title", "CIP2020Code"],
                    ["11-9013", "Farm Manager", "01.0101"],
                    ["45-1011", "Supervisor", "01.0101"]],
        "Unmatched CIP Codes": [["CIP2020Code"], ["99.9999"]],
        "Unmatched SOC Codes": [["SOC2018Code"], ["55-1011"]],
    })
    r = probe.probe(p, quiet=True)
    assert r["distinct_cip"] == 1, "columns were read by position, not by name"
    assert r["distinct_soc"] == 2


def test_sheets_are_resolved_through_relationships_not_filename_order(tmp_path):
    """Sheet order in the workbook and filenames on disk need not agree.
    Reading sheet2.xml because CIP-SOC is listed second would be a coin flip."""
    p = complete(tmp_path)
    with zipfile.ZipFile(p) as z:
        assert probe.sheets(z)["CIP-SOC"].endswith("sheet2.xml")


def test_a_missing_sheet_is_refused_with_what_it_did_find(tmp_path):
    p = workbook(tmp_path / "partial.xlsx", {"CIP-SOC": [["CIP2020Code", "SOC2018Code"], ["1", "2"]]})
    with pytest.raises(ValueError, match="missing"):
        probe.probe(p, quiet=True)


def test_a_renamed_column_is_refused_rather_than_guessed(tmp_path):
    """If NCES renames a column, the honest answer is that the counts cannot be
    trusted — not a zero that looks like a measurement."""
    p = workbook(tmp_path / "renamed.xlsx", {
        "CIP-SOC": [["ProgrammeCode", "OccupationCode"], ["01.0101", "11-9013"]],
        "Unmatched CIP Codes": [["CIP2020Code"], ["9"]],
        "Unmatched SOC Codes": [["SOC2018Code"], ["9"]],
    })
    with pytest.raises(ValueError, match="header|column"):
        probe.probe(p, quiet=True)


def test_an_absent_file_says_how_to_get_it(tmp_path):
    with pytest.raises(FileNotFoundError, match="--download"):
        probe.probe(tmp_path / "nope.xlsx", quiet=True)


def test_a_download_that_is_not_a_workbook_is_refused(monkeypatch, tmp_path):
    """NCES moving the file would serve an HTML error page. Writing that to
    disk and parsing it later would fail somewhere much less obvious."""
    class Html:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b"<html>404 Not Found</html>"

    monkeypatch.setattr(probe.urllib.request, "urlopen", lambda *a, **k: Html())
    with pytest.raises(ValueError, match="did not return a workbook"):
        probe.download(tmp_path / "out.xlsx")


def test_the_source_url_is_the_nces_one():
    """The figures are only citable if they came from the publisher."""
    assert probe.SOURCE_URL.startswith("https://nces.ed.gov/")
    assert probe.SOURCE_URL.endswith(".xlsx")


def test_json_output_parses_and_carries_provenance(tmp_path, monkeypatch, capsys):
    import json
    monkeypatch.setattr(probe, "LOCAL", complete(tmp_path))
    assert probe.main(["--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mappings"] == 3
    assert payload["source"].startswith("https://nces.ed.gov/")
    assert payload["retrieved_at"].endswith("+00:00")


def test_a_sheet_that_parses_to_zero_rows_is_refused(tmp_path):
    """A header row and nothing under it. Reporting 0 mappings would look like
    a measurement of a crosswalk that maps nothing, rather than a parse that
    found nothing."""
    p = workbook(tmp_path / "empty.xlsx", {
        "CIP-SOC": [["CIP2020Code", "SOC2018Code"]],
        "Unmatched CIP Codes": [["CIP2020Code"], ["99.9999"]],
        "Unmatched SOC Codes": [["SOC2018Code"], ["55-1011"]],
    })
    with pytest.raises(ValueError, match="zero rows"):
        probe.probe(p, quiet=True)


def test_a_sparse_row_keeps_its_columns(tmp_path):
    """Excel omits an empty cell rather than writing a blank one, so a row with
    no title arrives as `<c r="A3">…</c><c r="C3">…</c>`.

    Appending in document order put the SOC code where the header says
    CIP2020Title is — a plausible count of the wrong thing, with no error. This
    is the failure the module docstring names, and nothing caught it because the
    helper only wrote dense rows.
    """
    p = workbook(tmp_path / "sparse.xlsx", {
        "CIP-SOC": [
            ["CIP2020Code", "CIP2020Title", "SOC2018Code"],
            ["01.0101", "Agriculture", "11-9013"],
            ["11.0701", "", "15-1252"],          # blank title — cell omitted
            ["", "Orphan title", "15-2031"],     # blank code on the other side
        ],
        "Unmatched CIP Codes": [["CIP2020Code"], ["99.9999"]],
        "Unmatched SOC Codes": [["SOC2018Code"], ["55-1011"]],
    })
    r = probe.probe(p, quiet=True)
    assert r["mappings"] == 2, "the sparse row lost or shifted a column"
    assert r["distinct_cip"] == 2, r
    assert r["distinct_soc"] == 2, "the SOC column was read from the wrong position"
    assert r["incomplete_rows"] == 1, "a row blank on one side must be visible, not absorbed"


def test_column_letters_convert_to_indices():
    assert probe.col_index("A1") == 0
    assert probe.col_index("C5") == 2
    assert probe.col_index("Z9") == 25
    assert probe.col_index("AA1") == 26
    assert probe.col_index("AB100") == 27


def test_a_non_workbook_already_on_disk_is_refused_not_a_traceback(tmp_path):
    """download() guards the fetch, but a truncated or hand-copied file that
    arrived some other way used to reach zipfile and raise BadZipFile, which
    main() caught nowhere — a stack trace instead of the clear message."""
    bad = tmp_path / "notaworkbook.xlsx"
    bad.write_bytes(b"<html>404 Not Found</html>")
    with pytest.raises(ValueError, match="not a workbook"):
        probe.probe(bad, quiet=True)


def test_download_creates_missing_parent_directories(tmp_path, monkeypatch):
    """mkdir(exist_ok=True) fails when the grandparent is absent too."""
    class Book:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b"PK\x03\x04rest-of-a-zip"

    monkeypatch.setattr(probe.urllib.request, "urlopen", lambda *a, **k: Book())
    target = tmp_path / "deep" / "nested" / "cw.xlsx"
    assert probe.download(target).exists()


def test_a_sheet_that_repeats_its_own_name_is_not_read_as_a_header(tmp_path):
    """The unmatched sheets are called "Unmatched CIP Codes" and "Unmatched SOC
    Codes". A sheet that puts its own name in A1 — the layout CIP-SOC uses —
    contains both the code name and "code", so requiring those two was not
    enough: find_header locked onto the title and counted the real header row
    (`CIP2020Code`) as data. Reproduced at 2 instead of 1, silently.

    The earlier test dodged this by titling the sheet "Unmatched" rather than
    its actual name.
    """
    p = workbook(tmp_path / "titled.xlsx", {
        "CIP-SOC": [["2020 CIP / 2018 SOC Crosswalk"], [],
                    ["CIP2020Code", "CIP2020Title", "SOC2018Code"],
                    ["01.0101", "Agriculture", "11-9013"]],
        "Unmatched CIP Codes": [["Unmatched CIP Codes"], ["CIP2020Code"], ["99.9999"]],
        "Unmatched SOC Codes": [["Unmatched SOC Codes"], ["SOC2018Code"], ["55-1011"]],
    })
    r = probe.probe(p, quiet=True)
    assert r["unmatched_cip"] == 1, "the sheet title was read as the header row"
    assert r["unmatched_soc"] == 1, "the sheet title was read as the header row"
    assert r["mappings"] == 1


def test_a_heading_is_distinguished_from_a_title_naming_the_same_thing():
    assert probe.is_code_header("CIP2020Code", "CIP")
    assert probe.is_code_header("SOC2018Code", "SOC")
    assert not probe.is_code_header("Unmatched CIP Codes", "CIP"), "plural — a sheet title"
    assert not probe.is_code_header("2020 CIP / 2018 SOC Crosswalk", "CIP"), "a title"
    assert not probe.is_code_header("CIP2020Title", "CIP"), "a different column"


def test_an_absolute_relationship_target_resolves(tmp_path):
    """OPC permits Target="/xl/worksheets/sheet1.xml". Prefixing unconditionally
    gave "xl/xl/..." and a KeyError out of read() — a traceback, since main()
    catches no KeyError. The helper writes relative targets, so only a
    hand-built workbook exercises this."""
    p = tmp_path / "absolute.xlsx"
    body = ('<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/'
            'spreadsheetml/2006/main"><sheetData></sheetData></worksheet>')
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("xl/workbook.xml",
                   '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/'
                   'spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/'
                   'officeDocument/2006/relationships">'
                   '<sheets><sheet name="CIP-SOC" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/'
                   'package/2006/relationships"><Relationship Id="rId1" Type="http://'
                   'schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                   'Target="/xl/worksheets/sheet1.xml"/></Relationships>')
        z.writestr("xl/worksheets/sheet1.xml", body)
    with zipfile.ZipFile(p) as z:
        assert probe.sheets(z)["CIP-SOC"] == "xl/worksheets/sheet1.xml"


# --------------------------------------------------------------------------
# the NO MATCH sentinel — edtech-kg#70
# --------------------------------------------------------------------------

def with_sentinel(path):
    """A workbook shaped like the real one: two real mappings, and two
    programmes whose only row carries the crosswalk's NO MATCH sentinel — the
    same two the "Unmatched CIP Codes" sheet lists, which is how the published
    file states that fact twice."""
    return workbook(path / "cw.xlsx", {
        "File Guide": [["ignore me"]],
        "CIP-SOC": [
            ["CIP2020Code", "CIP2020Title", "SOC2018Code", "SOC2018Title"],
            ["01.0101", "Agriculture", "45-1011", "Supervisor"],
            ["11.0701", "Computer Science", "15-1252", "Developer"],
            ["01.0508", "Taxidermy", probe.NO_MATCH_SOC, "NO MATCH"],
            ["01.0599", "Other Agriculture", probe.NO_MATCH_SOC, "NO MATCH"],
        ],
        "Unmatched CIP Codes": [["Unmatched"], ["CIP2020Code"], ["01.0508"], ["01.0599"]],
        "Unmatched SOC Codes": [["Unmatched"], ["SOC2018Code"], ["55-1011"]],
    })


def test_the_no_match_sentinel_is_not_counted_as_an_occupation(tmp_path):
    """`99-9999` means "this programme maps to nothing". Counting it inflated
    the published figure by one — 868 where the real crosswalk holds 867
    occupations (#70). It surfaced only because it turned up in a list of
    occupations BLS "fails to carry", which is the shape of this defect: a
    wrong figure that is only ever one out and so never looks wrong.
    """
    r = probe.probe(with_sentinel(tmp_path), quiet=True)
    assert r["distinct_soc"] == 2, "the sentinel is being counted as an occupation"


def test_a_sentinel_row_is_not_counted_as_a_mapping(tmp_path):
    """The same rows inflated `mappings` too. A row that says NO MATCH is a
    statement that there is no mapping, so counting it as one overstates the
    join every answer in this repo traverses."""
    r = probe.probe(with_sentinel(tmp_path), quiet=True)
    assert r["mappings"] == 2
    assert r["rows_on_the_sheet"] == 4
    assert r["declared_no_match"] == 2


def test_a_programme_with_only_a_sentinel_row_is_still_a_programme(tmp_path):
    """It is listed in the crosswalk, so it counts as a CIP code — dropping it
    would understate what the file covers. What it is not is a programme that
    maps to an occupation, and the two are reported separately rather than one
    number standing in for both."""
    r = probe.probe(with_sentinel(tmp_path), quiet=True)
    assert r["distinct_cip"] == 4
    assert r["cip_with_an_occupation"] == 2


def test_the_workbook_states_the_unmatched_count_in_two_places_and_they_agree(tmp_path):
    """A sentinel row per unmatched programme, and a sheet listing those
    programmes. Asserted rather than enforced in the probe: a workbook that
    states it once is odd, not corrupt, and a probe that refused to run would
    be harder to diagnose than one that reports both figures."""
    r = probe.probe(with_sentinel(tmp_path), quiet=True)
    assert r["declared_no_match"] == r["unmatched_cip"]


def test_a_crosswalk_with_no_sentinel_at_all_still_reports_zero(tmp_path):
    """The fields have to be present whether or not the sentinel appears. A
    key that exists only when the defect does is a key nothing can rely on."""
    r = probe.probe(complete(tmp_path), quiet=True)
    assert r["declared_no_match"] == 0
    assert r["mappings"] == r["rows_on_the_sheet"] == 3
    assert r["distinct_cip"] == r["cip_with_an_occupation"] == 2


def test_the_builder_reaches_past_column_z_and_escapes_its_values():
    """`chr(65 + col)` produced `[` at column 26.

    A fixture wide enough to reach it built a workbook with cell references
    no reader can place — and the readers here place cells BY reference, so
    the test would have been exercising a file Excel could not have written.

    Values and sheet names are escaped for the same reason: `&` and `<` are
    legal in a real workbook, and unescaped they produced XML the reader
    could not parse, so a fixture testing an awkward value failed on the
    fixture rather than on the code.
    """
    import io
    import zipfile

    from tests.workbook_support import workbook as build

    header = [f"col{i}" for i in range(30)]
    header[27] = "R&D <units>"
    buffer = io.BytesIO()
    build(buffer, {"A & B": [header, ["x"] * 30]})

    with zipfile.ZipFile(buffer) as book:
        got = probe.rows(book, probe.sheets(book)["A & B"])

    assert len(got[0]) == 30, "columns past Z were dropped or misplaced"
    assert got[0][27] == "R&D <units>", (
        "an ampersand or angle bracket did not survive the round trip")

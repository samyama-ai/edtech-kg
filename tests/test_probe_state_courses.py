"""Tests for the statewide course-directory probe.

The network is stubbed throughout. What is under test is the counting and the
refusals — the places where a wrong number would look like a right one. The
header-row bug this file pins was real: the document said 1,636 and 2,013 until
the probe was written.
"""

import io
import json
import urllib.error
import zipfile

import pytest

from etl import probe_state_courses as probe


# --------------------------------------------------------------------------
# fetch()
# --------------------------------------------------------------------------

def serve(monkeypatch, payload: bytes):
    class R:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return payload
        def geturl(self): return "https://example.invalid/x"
    monkeypatch.setattr(probe.urllib.request, "urlopen", lambda *a, **k: R())


def test_a_non_workbook_response_is_refused(monkeypatch):
    """Exercises the real fetch(), not a stub of it — an HTML error page saved
    as an .xlsx would otherwise fail much later and much less clearly."""
    serve(monkeypatch, b"<html>404 Not Found</html>")
    with pytest.raises(ValueError, match="expected format"):
        probe.fetch("https://example.invalid/x.xlsx", expect=b"PK")


def test_a_response_of_the_right_shape_passes(monkeypatch):
    serve(monkeypatch, b"PK\x03\x04rest")
    assert probe.fetch("https://example.invalid/x.xlsx", expect=b"PK").startswith(b"PK")


def test_an_http_error_names_the_url(monkeypatch):
    monkeypatch.setattr(probe.urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(
                            urllib.error.HTTPError("u", 403, "no", {}, io.BytesIO(b""))))
    with pytest.raises(RuntimeError, match="403"):
        probe.fetch("https://example.invalid/x")


# --------------------------------------------------------------------------
# Texas
# --------------------------------------------------------------------------

def test_texas_does_not_count_the_header_as_a_course(monkeypatch):
    """The bug this probe found. The document said 1,636; the file has 1,635
    courses and one header row."""
    serve(monkeypatch, b"Code,Description\n01,Algebra I\n02,Biology\n")
    assert probe.texas()["courses"] == 2


def test_texas_refuses_a_header_only_file(monkeypatch):
    """A source that has been emptied must not report as zero courses — that
    reads as a finding rather than as a broken download."""
    serve(monkeypatch, b"Code,Description\n")
    with pytest.raises(ValueError, match="refusing"):
        probe.texas()


def test_texas_finds_a_prerequisite_term_if_one_is_there(monkeypatch):
    serve(monkeypatch, b"Code,Description\n01,Algebra II. Prerequisite: Algebra I\n")
    assert probe.texas()["prerequisite_terms"]["strong"]["prerequisit"] == 1


# --------------------------------------------------------------------------
# New York — the load-bearing evidence, so the workbook parsing is tested
# --------------------------------------------------------------------------

def workbook(sheets: dict, strings: list[str]) -> bytes:
    """A minimal but real .xlsx: `sheets` maps name -> list of rows of cell XML."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        names = list(sheets)
        z.writestr("xl/workbook.xml",
                   '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                   "<sheets>" + "".join(
                       f'<sheet name="{n}" r:id="rId{i}" xmlns:r="http://schemas.openxml'
                       f'formats.org/officeDocument/2006/relationships"/>'
                       for i, n in enumerate(names, 1)) + "</sheets></workbook>")
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
                   'relationships">' + "".join(
                       f'<Relationship Id="rId{i}" Target="worksheets/sheet{i}.xml"/>'
                       for i in range(1, len(names) + 1)) + "</Relationships>")
        z.writestr("xl/sharedStrings.xml",
                   '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                   + "".join(f"<si><t>{s}</t></si>" for s in strings) + "</sst>")
        for i, name in enumerate(names, 1):
            z.writestr(f"xl/worksheets/sheet{i}.xml",
                       '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/'
                       '2006/main"><sheetData>'
                       + "".join(f"<row>{r}</row>" for r in sheets[name])
                       + "</sheetData></worksheet>")
    return buf.getvalue()


def s(i):        # a shared-string cell
    return f'<c t="s"><v>{i}</v></c>'


def ny(monkeypatch, sheets, strings):
    serve(monkeypatch, workbook(sheets, strings))
    return probe.new_york()


def test_new_york_does_not_count_the_header_as_a_course(monkeypatch):
    r = ny(monkeypatch, {"All courses": [s(0) + s(1), s(2), s(3), s(4)]},
           ["Code", "Title", "01", "02", "03"])
    assert r["courses"] == 3


def test_only_the_courses_sheet_is_counted(monkeypatch):
    """The workbook's other sheets track edition-to-edition changes. The doc
    said "2,012 courses across five sheets"; the count is one sheet, and
    summing them would double-count courses that merely changed."""
    r = ny(monkeypatch, {"All courses": [s(0), s(1), s(2)],
                         "Change Tracker": [s(0), s(1)],
                         "New Courses": [s(0), s(1), s(1), s(1)]},
           ["Code", "01", "02"])
    assert r["courses"] == 2
    assert r["rows_per_sheet"] == {"All courses": 2, "Change Tracker": 1, "New Courses": 3}
    assert "only" in r["counted_from"]


def test_a_term_on_a_non_primary_sheet_is_still_found(monkeypatch):
    """The search runs over the shared-string table, which is workbook-wide.
    A prerequisite hiding on the change-tracker sheet must not be missed."""
    r = ny(monkeypatch, {"All courses": [s(0), s(1)], "New Descriptions": [s(2)]},
           ["Code", "01", "Prerequisite: Algebra I"])
    assert r["prerequisite_terms"]["strong"]["prerequisit"] == 1


def test_trailing_rows_with_no_values_are_not_courses(monkeypatch):
    """Styled-but-empty trailing rows are the same silent overcount the header
    row was."""
    r = ny(monkeypatch, {"All courses": [s(0), s(1), '<c s="3"/>', '<c s="3"/>']},
           ["Code", "01"])
    assert r["courses"] == 1


def test_an_empty_courses_sheet_is_refused(monkeypatch):
    with pytest.raises(ValueError, match="refusing"):
        ny(monkeypatch, {"All courses": [s(0)]}, ["Code"])


def test_a_renamed_courses_sheet_is_refused_not_guessed(monkeypatch):
    """The old code fell back to the first sheet. If the catalogue is ever
    restructured that silently counts the change tracker and reports a number
    with no signal that anything went wrong."""
    with pytest.raises(ValueError, match="refusing to count an arbitrary sheet"):
        ny(monkeypatch, {"Change Tracker": [s(0), s(1)], "Catalog 2026": [s(0), s(1)]},
           ["Code", "01"])


def test_an_inline_string_header_is_read(monkeypatch):
    r = ny(monkeypatch, {"All courses": ['<c t="inlineStr"><is><t>Code</t></is></c>', s(0)]},
           ["01"])
    assert r["fields"] == ["Code"]


def test_an_out_of_range_shared_string_index_is_malformed_not_refused(monkeypatch):
    """A parse failure and a refusal to report an unmeasured figure are
    different categories and exit differently."""
    with pytest.raises(probe.MalformedSource):
        ny(monkeypatch, {"All courses": [s(99), s(0)]}, ["Code"])


def test_a_non_numeric_shared_string_index_is_malformed_not_refused(monkeypatch):
    """The other half of the same guard. Raising ValueError here would surface
    as "refused: …", putting a corrupt file in the same category as an honest
    empty source."""
    with pytest.raises(probe.MalformedSource):
        ny(monkeypatch, {"All courses": ['<c t="s"><v>x</v></c>', s(0)]}, ["Code"])


# --------------------------------------------------------------------------
# the states that do not parse — asked every run, never remembered
# --------------------------------------------------------------------------

@pytest.mark.parametrize("code", [403, 429, 503])
def test_a_blocked_state_records_the_status_the_server_gave(monkeypatch, code):
    """Whatever the server said, not a remembered 403. A rate-limit and a block
    are different problems and #50 turns on telling them apart."""
    monkeypatch.setattr(probe.urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(
                            urllib.error.HTTPError("u", code, "no", {}, io.BytesIO(b""))))
    assert probe.attempt("Florida", "https://x")["status"] == code


def test_a_state_that_starts_serving_is_not_reported_as_blocked(monkeypatch):
    """The statuses used to be a hardcoded constant. Florida could have opened
    up and the script would still have printed 403 forever."""
    class R:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b"data"
        def geturl(self): return "https://x"
    monkeypatch.setattr(probe.urllib.request, "urlopen", lambda *a, **k: R())
    assert probe.attempt("Florida", "https://x")["status"] == 200


def test_a_redirect_records_where_it_went(monkeypatch):
    class R:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b"data"
        def geturl(self): return "https://elsewhere"
    monkeypatch.setattr(probe.urllib.request, "urlopen", lambda *a, **k: R())
    assert probe.attempt("California", "https://x")["redirected_to"] == "https://elsewhere"


def test_an_unreachable_state_is_not_a_status_code(monkeypatch):
    monkeypatch.setattr(probe.urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(urllib.error.URLError("dns")))
    assert probe.attempt("Virginia", "https://x")["status"] is None


# --------------------------------------------------------------------------
# strong vs weak terms — the printed table must not contradict the verdict
# --------------------------------------------------------------------------

def test_weak_terms_are_kept_out_of_the_strong_count():
    """"prior to" and "successful completion" occur in ordinary course prose.
    Summing all six terms printed "prerequisite terms: 4" for New York while
    the document concluded zero."""
    counts = probe.term_counts("students should revise prior to the exam; "
                               "successful completion of unit 2 is expected")
    assert sum(counts["strong"].values()) == 0
    assert sum(counts["weak"].values()) == 2
    assert not set(probe.STRONG_TERMS) & set(probe.WEAK_TERMS)


# --------------------------------------------------------------------------
# the CLI
# --------------------------------------------------------------------------

def test_a_refusal_exits_one_and_prints_no_table(monkeypatch, capsys):
    serve(monkeypatch, b"Code,Description\n")
    assert probe.main([]) == 1
    assert "courses" not in capsys.readouterr().out


def test_a_malformed_source_exits_three_not_one(monkeypatch):
    monkeypatch.setattr(probe, "texas", lambda: (_ for _ in ()).throw(
        probe.MalformedSource("bad index")))
    assert probe.main([]) == 3


def test_json_output_carries_a_timestamp_and_the_term_split(monkeypatch, capsys):
    monkeypatch.setattr(probe, "texas", lambda: {"state": "Texas", "courses": 1})
    monkeypatch.setattr(probe, "new_york", lambda: {"state": "New York", "courses": 1})
    monkeypatch.setattr(probe, "attempt", lambda s, u: {"state": s, "status": 403})
    assert probe.main(["--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert "retrieved_at" in out
    assert out["weak_terms"] == list(probe.WEAK_TERMS)

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
import zipfile

import pytest

from etl import probe_sced as probe
from tests.workbook_support import workbook as cipsoc_workbook


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
        probe.fetch(probe.PINNED_WAS)


def test_a_renamed_sheet_is_refused_with_what_it_did_find(monkeypatch):
    """NCES changing the layout must stop the probe, not shrink its answer."""
    book = workbook({"Overview": [["x"]], "Something Else": [["y"]]})
    monkeypatch.setattr(probe, "fetch", lambda url: book)
    # `master()` reads the landing page for the workbook URL now, so a test
    # that fakes the workbook must fake that too or it makes a real request.
    monkeypatch.setattr(probe, "master_file", lambda: (probe.PINNED_WAS, 13))
    with pytest.raises(probe.MalformedSource, match="no course sheet"):
        probe.master()


def test_a_sheet_that_parses_to_zero_rows_is_refused(monkeypatch):
    """An empty taxonomy is not a measurement."""
    book = workbook({"SCED 13.0": [["Course Title", "SCED Course Code"]]})
    monkeypatch.setattr(probe, "fetch", lambda url: book)
    # `master()` reads the landing page for the workbook URL now, so a test
    # that fakes the workbook must fake that too or it makes a real request.
    monkeypatch.setattr(probe, "master_file", lambda: (probe.PINNED_WAS, 13))
    # "no data rows" rather than "zero rows": a header-only sheet is caught by
    # the length guard now, which fires first and says what is missing. The
    # zero-rows message still covers a sheet with rows that all fail the
    # non-empty check.
    # One phrase, not an alternation. `"no data rows|zero rows"` passes on
    # either message, so it asserts that the refusal happened and not which
    # refusal — and the two come from different guards.
    with pytest.raises(probe.MalformedSource, match="no data rows"):
        probe.master()


def test_sheets_are_resolved_through_relationships_not_filename_order():
    """`sheet1.xml` is not reliably the first sheet. A reordered workbook would
    otherwise be read as a different one, silently."""
    book = zipfile.ZipFile(io.BytesIO(workbook(
        {"Overview": [["a"]], "SCED 13.0": [["Course Title"], ["Algebra"]]})))
    found = probe.sheets(book)
    assert set(found) == {"Overview", "SCED 13.0"}
    assert probe.rows(book, found["SCED 13.0"])[1] == ["Algebra"]


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
    # `master()` reads the landing page for the workbook URL now, so a test
    # that fakes the workbook must fake that too or it makes a real request.
    monkeypatch.setattr(probe, "master_file", lambda: (probe.PINNED_WAS, 13))
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
    # `master()` reads the landing page for the workbook URL now, so a test
    # that fakes the workbook must fake that too or it makes a real request.
    monkeypatch.setattr(probe, "master_file", lambda: (probe.PINNED_WAS, 13))
    with pytest.raises(probe.MalformedSource, match="banner rows"):
        probe.master()


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
    # `master()` reads the landing page for the workbook URL now, so a test
    # that fakes the workbook must fake that too or it makes a real request.
    monkeypatch.setattr(probe, "master_file", lambda: (probe.PINNED_WAS, 13))
    with pytest.raises(probe.MalformedSource, match="blank first column"):
        probe.master()


def test_the_master_workbook_is_read_from_the_landing_page_not_pinned(monkeypatch):
    """The comment claimed this and the code did not do it.

    `MASTER` was a hard-pinned v13 URL and `LANDING` was fetched nowhere, while
    the comment beside it said the URL was "read from the landing page rather
    than pinned, so the next version is a changed figure and not a stale
    constant". When NCES ships v14 that probe reports SCED 13.0 for ever —
    precisely the stale constant the page's corrections section claims to
    avoid.

    The HIGHEST version, not the first link: NCES publishes the previous
    version alongside the current one, so taking the first match pins whichever
    happens to be listed first.
    """
    page = ('<a href="/files/SCEDv12File_508.xlsx">v12</a>'
            '<a href="/files/SCEDv13File_508.xlsx">v13</a>')
    monkeypatch.setattr(probe, "fetch_text", lambda url: page)

    url, version = probe.master_file()
    assert version == 13, "the older version was taken as current"
    assert url.endswith("/files/SCEDv13File_508.xlsx")
    assert url.startswith("https://nces.ed.gov"), (
        "the href is relative on the real page and must be resolved against it")


def test_a_restructured_landing_page_stops_the_run(monkeypatch):
    """No fallback to the pinned URL.

    A fallback that kicks in silently when the landing page changes shape is
    the stale constant again, wearing a guard: the run would keep reporting
    whichever version was pinned the day this was written, and nothing would
    say so.
    """
    monkeypatch.setattr(probe, "fetch_text", lambda url: "<html>redesigned</html>")
    with pytest.raises(probe.MalformedSource, match="no SCEDv"):
        probe.master_file()


def test_the_json_payload_still_carries_the_new_york_titles(monkeypatch):
    """RUN the probe and look at what comes out.

    This grepped the source for `state.pop("titles")`, so it passed the moment
    the pop became a comprehension omitting the same key — while the payload
    it is named for was still missing it. `titles` is the input the reach
    figures are computed from, and a payload that drops its own input cannot
    be re-checked.
    """
    from etl import pwcs_source

    monkeypatch.setattr(probe, "master_file", lambda: (probe.PINNED_WAS, 13))
    monkeypatch.setattr(probe, "fetch", lambda url: workbook(
        {"SCED 13.0": [["Course Title", "SCED Course Code"], ["Algebra I", "02052"]],
         "Elements and Attributes": [["Element Name"], ["Course Title"],
                                     ["Attribute Name"], ["Course Level"]]}))
    monkeypatch.setattr(probe, "new_york", lambda payload: {
        "source": "x", "columns": ["a"], "rows": 1, "courses": 1,
        "sced_codes": 1, "state_extensions": [], "subject_prefixes": 1,
        "publishes_sequence": False, "titles": {"Algebra I": ["02052"]}})
    monkeypatch.setattr(pwcs_source, "read",
                        lambda: {"courses": [{"title": "Algebra I"}]})

    payload = probe.probe(quiet=True)

    assert "titles" in payload["new_york"], (
        "the JSON payload dropped the New York titles, so the input the reach "
        "figures are computed from is not in the machine-readable output")
    assert payload["new_york"]["titles"] == {"Algebra I": ["02052"]}
    assert payload["district"]["reachable_by_name"] == 1, (
        "the reach measurement did not run, so this asserted the payload "
        "shape of something that was never computed")


def test_an_elements_sheet_named_sced_does_not_trip_the_version_guard(monkeypatch):
    """`startswith("SCED ")` and `"Element" in n` could both match one name.

    A sheet called `SCED Elements` satisfied both, so the course-sheet check
    saw two candidates and refused the whole run over a name that is not a
    second version. Today's names do not collide — a false refusal waiting on
    a rename. The course sheet is matched by shape now.
    """
    book = workbook({
        "SCED 13.0": [["Course Title", "SCED Course Code"], ["Algebra I", "02052"]],
        "SCED Elements": [["Element Name"], ["Course Title"],
                          ["Attribute Name"], ["Course Level"]]})
    monkeypatch.setattr(probe, "fetch", lambda url: book)
    monkeypatch.setattr(probe, "master_file", lambda: (probe.PINNED_WAS, 13))

    got = probe.master()
    assert got["version_sheet"] == "SCED 13.0", (
        "a sheet named `SCED Elements` was taken as a second version")
    assert got["elements"] == ["Course Title"]

    # And a real second version is still refused.
    two = workbook({
        "SCED 13.0": [["Course Title", "SCED Course Code"], ["Algebra I", "02052"]],
        "SCED 14.0": [["Course Title", "SCED Course Code"], ["Algebra I", "02052"]],
        "Elements and Attributes": [["Element Name"], ["Course Title"],
                                    ["Attribute Name"], ["Course Level"]]})
    monkeypatch.setattr(probe, "fetch", lambda url: two)
    with pytest.raises(probe.MalformedSource, match="current SCED sheets"):
        probe.master()


def test_a_second_sequence_definition_is_visible_rather_than_last_wins(monkeypatch):
    """`sequence = definition` kept whichever row came last, silently — and
    the page quotes that definition as its answer to edtech-kg#48."""
    book = workbook({
        "SCED 13.0": [["Course Title", "SCED Course Code"], ["Algebra I", "02052"]],
        "Elements and Attributes": [
            ["Element Name"],
            ["Sequence", "a consecutive sequence of courses, first"],
            # BOTH in the element bucket — an attribute carrying the phrase
            # is a different case and is covered separately.
            ["Other", "a consecutive sequence of courses, second"],
            ["Attribute Name"],
            ["Course Level", "how advanced"]]})
    monkeypatch.setattr(probe, "fetch", lambda url: book)
    monkeypatch.setattr(probe, "master_file", lambda: (probe.PINNED_WAS, 13))

    got = probe.master()
    assert got["sequence_definitions"] == 2, (
        "a second definition of the sequence element was silently discarded")
    assert got["sequence_element"].endswith("first"), (
        "the definition reported depends on the order of the rows")


def test_two_links_for_one_version_are_refused_rather_than_ordered(monkeypatch):
    """`max(..., key=version)` broke a tie by the order of the page, and
    which copy this reads decides what every figure describes."""
    monkeypatch.setattr(probe, "fetch_text", lambda url: (
        '<a href="/a/SCEDv13File_508.xlsx">x</a>'
        '<a href="/b/SCEDv13File_508.xlsx">y</a>'))
    with pytest.raises(probe.MalformedSource, match="links for SCED v13"):
        probe.master_file()

    # One link per version is still an answer, highest wins.
    monkeypatch.setattr(probe, "fetch_text", lambda url: (
        '<a href="/SCEDv12File_508.xlsx">x</a>'
        '<a href="/SCEDv13File_508.xlsx">y</a>'))
    url, version = probe.master_file()
    assert version == 13 and url.endswith("/SCEDv13File_508.xlsx")


def test_a_reordered_master_sheet_is_refused_rather_than_counted(monkeypatch):
    """`courses` is counted by `r[0].strip()` while `new_york()` pins its own
    column names, so a reordered sheet keeps parsing and counts something
    else — the positional read every other reader here was moved off."""
    book = workbook({
        "SCED 13.0": [["SCED Course Code", "Course Title"],
                      ["02052", "Algebra I"]],
        "Elements and Attributes": [["Element Name"], ["Course Title"],
                                    ["Attribute Name"], ["Course Level"]]})
    monkeypatch.setattr(probe, "fetch", lambda url: book)
    monkeypatch.setattr(probe, "master_file", lambda: (probe.PINNED_WAS, 13))

    with pytest.raises(probe.MalformedSource, match="not the course title"):
        probe.master()


def test_a_sequence_definition_in_the_attribute_bucket_is_not_an_element(monkeypatch):
    """The page says SCED's ELEMENT list includes Sequence of Course.

    The match ran against any bucket, so an attribute carrying the phrase
    would be quoted as an element — the answer to edtech-kg#48, about the
    wrong thing.
    """
    book = workbook({
        "SCED 13.0": [["Course Title", "SCED Course Code"], ["Algebra I", "02052"]],
        "Elements and Attributes": [
            ["Element Name"], ["Course Code", "a code"],
            ["Attribute Name"],
            ["Something", "part of a consecutive sequence of courses"]]})
    monkeypatch.setattr(probe, "fetch", lambda url: book)
    monkeypatch.setattr(probe, "master_file", lambda: (probe.PINNED_WAS, 13))

    got = probe.master()
    assert got["sequence_element"] is None, (
        "an ATTRIBUTE definition was reported as the sequence element")


def test_a_repeated_header_row_is_not_counted_as_a_course(monkeypatch):
    """Any non-empty column 0 counted, so a sheet that repeats its header —
    which is how a long table is paged — inflates the count the page quotes.
    """
    book = workbook({
        "SCED 13.0": [["Course Title", "SCED Course Code"],
                      ["Algebra I", "02052"],
                      ["Course Title", "SCED Course Code"],
                      ["Biology", "03051"]],
        "Elements and Attributes": [["Element Name"], ["Course Title"],
                                    ["Attribute Name"], ["Course Level"]]})
    monkeypatch.setattr(probe, "fetch", lambda url: book)
    monkeypatch.setattr(probe, "master_file", lambda: (probe.PINNED_WAS, 13))

    assert probe.master()["courses"] == 2, "a repeated header counted as a course"


def test_the_workbook_url_must_be_https_on_the_nces_host(monkeypatch):
    """`urljoin` takes whatever scheme the fetched page offers."""
    monkeypatch.setattr(probe, "fetch_text", lambda url: (
        '<a href="file:///etc/passwd/SCEDv99File_x.xlsx">x</a>'))
    with pytest.raises(probe.MalformedSource, match="not https"):
        probe.master_file()

    monkeypatch.setattr(probe, "fetch_text", lambda url: (
        '<a href="https://evil.example/SCEDv99File_x.xlsx">x</a>'))
    with pytest.raises(probe.MalformedSource, match="same host"):
        probe.master_file()


def test_the_printed_tables_carry_the_figures_the_page_quotes(monkeypatch, capsys):
    """The print block never executed in tests — every call passed
    `quiet=True`, so two printing mutants survived the whole suite.

    The page quotes what this prints, so what it prints is the contract. Faked
    sources rather than live ones, for the reason `conftest` gives.
    """
    from etl import new_york_catalog, sced_reach
    from etl import pwcs_source

    monkeypatch.setattr(probe, "master_file", lambda: (probe.PINNED_WAS, 13))
    monkeypatch.setattr(probe, "fetch", lambda url: workbook({
        "SCED 13.0": [["Course Title", "SCED Course Code"],
                      ["Algebra I", "02052"]],
        "Elements and Attributes": [["Element Name"], ["Course Title"],
                                    ["Attribute Name"], ["Course Level"]]}))
    monkeypatch.setattr(new_york_catalog, "new_york", lambda payload: {
        "source": "x", "columns": ["Course Code (Course ID)", "Course Code Description"],
        "rows": 3, "courses": 3, "sced_codes": 2,
        "state_extensions": ["01003CC"], "subject_prefixes": 1,
        "publishes_sequence": False, "titles": {"Algebra I": ["02052"]}})
    monkeypatch.setattr(probe, "new_york", lambda payload: new_york_catalog.new_york(payload))
    monkeypatch.setattr(pwcs_source, "read",
                        lambda: {"courses": [{"title": "Algebra I"},
                                             {"title": "Turfgrass Management"}]})
    monkeypatch.setattr(sced_reach, "MAX_TERM", 0, raising=False)

    probe.probe(quiet=False)
    printed = capsys.readouterr().out

    # The two figures that were typed on the page because nothing printed them.
    assert "Course Code (Course ID), Course Code Description" in printed, (
        "the columns are not printed, so the page's count of them is typed")
    assert "01003CC" in printed, (
        "the extension codes are not printed, so the page's list is typed")
    # And the exhibits, which the page reproduces verbatim.
    assert "Algebra I" in printed and "Turfgrass Management" in printed

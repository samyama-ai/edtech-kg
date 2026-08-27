"""The code-sets probe, and the document that quotes it.

The failure to guard against is not a crash. It is a probe that reports a clean
alignment because it compared nothing — `0 in O*NET and not ours` reads as
"perfect" and is also what an empty set gives you. Several of these drive the
case where the answer would be wrong rather than absent.

Workbooks are built in the test, so no network and no committed sample file.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from etl import probe_codesets as probe
from tests.test_probe_cipsoc import workbook as cipsoc_workbook

DOC = Path(__file__).resolve().parents[1] / "docs" / "sources" / "code-sets.md"

# The one sheet the O*NET crosswalk carries. Named here because the probe
# resolves it through the workbook relationships and refuses to guess when
# there is more than one.
ONET_SHEET = "O-NET-SOC 2019 Occupation Listi"


def workbook(rows: list[list[str]]) -> bytes:
    """A single-sheet .xlsx carrying these rows, as bytes.

    Built by `tests.test_probe_cipsoc.workbook` rather than by a second
    builder here — the same reason `probe_codesets` calls `probe_cipsoc.rows`
    instead of carrying its own reader. That builder OMITS a cell whose value
    is `""`, which is what Excel does for a blank; the builder this file used
    to carry emitted every cell, so no fixture could reach the reader's
    placement rule at all.
    """
    buffer = io.BytesIO()
    cipsoc_workbook(buffer, {ONET_SHEET: rows})
    return buffer.getvalue()


def archived(member: str, payload: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as outer:
        outer.writestr(member, payload)
    return buffer.getvalue()


class _body:
    """One response body, for the fetches that are not the two pages."""

    def __init__(self, payload): self._payload = payload
    def __enter__(self): return self
    def __exit__(self, *exc): return False
    def read(self): return self._payload


def test_an_html_page_is_refused_rather_than_read_as_an_empty_archive(monkeypatch, tmp_path):
    """A 200 carrying an error page would otherwise parse to zero occupations
    and be reported as a taxonomy with nothing in it."""
    # `download`, not the pages — one body for one fetch, so `serve` (which
    # answers per URL for `career_clusters`) is the wrong shape here.
    monkeypatch.setattr(probe.urllib.request, "urlopen",
                        lambda *a, **k: _body(b"<!DOCTYPE html><html>404"))
    with pytest.raises(probe.MalformedSource, match="did not return an archive"):
        probe.download(probe.ONET_URL, tmp_path / "x.zip")


def test_a_renamed_member_is_refused_with_what_the_archive_holds(monkeypatch):
    """O*NET reorganising its zip must stop the probe, not shrink its answer."""
    monkeypatch.setattr(probe, "download",
                        lambda url, into: archived("Something/Else.xlsx", b"PK"))
    with pytest.raises(probe.MalformedSource, match="not in the O\\*NET archive"):
        probe.onet_to_soc(ours=set())


def test_a_crosswalk_with_no_header_is_refused(monkeypatch):
    """The header is found by content, not by row number — O*NET puts two title
    rows above it. A file without one is a layout change, not an empty answer."""
    book = workbook([["some", "other", "columns"], ["11-1011.00", "x", "11-1011"]])
    monkeypatch.setattr(probe, "download", lambda url, into: archived(probe.ONET_MEMBER, book))
    with pytest.raises(probe.MalformedSource, match="no header row"):
        probe.onet_to_soc(ours=set())


def test_a_naive_join_matching_nothing_is_reported_as_such(monkeypatch):
    """The finding the page leads with. Every O*NET code carries a `.NN`
    suffix, so string equality against a SOC code matches nothing — and that is
    the SAFE failure, because a partial match would be a figure nobody could
    reproduce.

    Driven with a fixture whose SOC side deliberately matches the crosswalk
    set passed in, so a zero here means the suffix and not an empty
    comparison. That set is passed explicitly rather than read from `data/`,
    which is gitignored — these three tests used to reach the real workbook
    and failed on a clean checkout, which is what CI is.
    """
    book = workbook([
        ["O*NET-SOC 2019 Occupation Listings"],
        ["Crosswalk"],
        ["O*NET-SOC 2019 Code", "O*NET-SOC 2019 Title", "2018 SOC Code", "2018 SOC Title"],
        ["11-1011.00", "Chief Executives", "11-1011", "Chief Executives"],
    ])
    monkeypatch.setattr(probe, "download", lambda url, into: archived(probe.ONET_MEMBER, book))
    got = probe.onet_to_soc(ours={"11-1011"})
    assert got["onet_occupations"] == 1
    assert got["naive_string_matches"] == 0, (
        "an O*NET code matched a SOC code by string equality — the suffix rule "
        "this page rests on no longer holds")
    assert got["soc_codes_they_roll_up_to"] == 1


def test_a_one_to_many_roll_up_is_counted(monkeypatch):
    """76 SOC codes carry more than one O*NET occupation, the largest ten. A
    future Occupation node has to decide its grain, so the fan-out is reported
    rather than flattened."""
    book = workbook([
        ["O*NET-SOC 2019 Occupation Listings"],
        ["Crosswalk"],
        ["O*NET-SOC 2019 Code", "O*NET-SOC 2019 Title", "2018 SOC Code", "2018 SOC Title"],
        ["15-1299.01", "Web Administrators", "15-1299", "Computer Occupations"],
        ["15-1299.02", "GIS Technologists", "15-1299", "Computer Occupations"],
        ["11-1011.00", "Chief Executives", "11-1011", "Chief Executives"],
    ])
    monkeypatch.setattr(probe, "download", lambda url, into: archived(probe.ONET_MEMBER, book))
    got = probe.onet_to_soc(ours=set())
    assert got["soc_with_several"] == 1
    assert got["largest_fan_out"] == 2
    assert got["soc_with_one_occupation"] == 1


def test_a_row_that_omits_its_title_still_reads_its_soc_code_from_the_right_column(monkeypatch):
    """The defect that would not have shown up as an error.

    Excel omits a blank cell rather than writing an empty one, so a row with no
    title arrives as `<c r="A5">…</c><c r="C5">…</c>`. A reader that appends in
    document order puts the *2018 SOC Title* into the slot the header calls
    *2018 SOC Code*, and `soc_codes_they_roll_up_to`, `fan` and the 867/867
    alignment all stay plausible and become wrong, with nothing raising.

    This is why the probe uses `probe_cipsoc.rows` rather than a second reader
    of its own: that one places cells by their `r` attribute. Measured against
    the O*NET file as it stands, every row is dense and both readers agree
    exactly — so the guard is against the file changing, not against today.
    """
    book = workbook([
        ["O*NET-SOC 2019 Code", "O*NET-SOC 2019 Title", "2018 SOC Code", "2018 SOC Title"],
        ["11-1011.00", "Chief Executives", "11-1011", "Chief Executives"],
        # No title. The SOC code must still land in column C.
        ["11-1011.03", "", "11-1011", "Chief Executives"],
    ])
    monkeypatch.setattr(probe, "download", lambda url, into: archived(probe.ONET_MEMBER, book))
    got = probe.onet_to_soc(ours=set())
    assert got["onet_occupations"] == 2, "the untitled row was dropped"
    assert got["soc_codes_they_roll_up_to"] == 1, (
        "the untitled row contributed something other than its SOC code — the "
        "reader is placing cells by document order again")
    assert got["largest_fan_out"] == 2


def test_a_second_sheet_is_refused_rather_than_guessed_at(monkeypatch):
    """The O*NET crosswalk carries one sheet, and the probe resolves it through
    the workbook relationships rather than assuming `sheet1.xml`. If the file
    ever carries two, reading whichever came first would be a plausible count
    of the wrong thing — the failure `probe_cipsoc.sheets` exists to prevent."""
    buffer = io.BytesIO()
    cipsoc_workbook(buffer, {
        ONET_SHEET: [["O*NET-SOC 2019 Code", "2018 SOC Code"], ["11-1011.00", "11-1011"]],
        "Notes": [["ignore me"]]})
    monkeypatch.setattr(probe, "download",
                        lambda url, into: archived(probe.ONET_MEMBER, buffer.getvalue()))
    with pytest.raises(probe.MalformedSource, match="refusing to guess which sheet"):
        probe.onet_to_soc(ours=set())


def test_a_missing_crosswalk_is_fetched_rather_than_raising_a_traceback(monkeypatch, tmp_path):
    """`data/` is gitignored, so on a clean checkout the CIP-SOC workbook is
    absent. Reading it directly raised `FileNotFoundError`, which `main()` does
    not catch — a traceback for the first person to reproduce these figures.
    """
    monkeypatch.setattr(probe.crosswalk, "LOCAL", tmp_path / "absent.xlsx")
    asked = []
    monkeypatch.setattr(probe.crosswalk, "download",
                        lambda *a, **k: asked.append(True))
    # Narrowed to what this path actually raises, and asserted on. Catching
    # `FileNotFoundError` too meant the test passed whether the fetch was
    # wrapped or not, which is the thing under test — `crosswalk_pairs` exists
    # because a bare FileNotFoundError reached `main()`.
    with pytest.raises(probe.MalformedSource):
        probe.crosswalk_pairs()
    assert asked, "the probe read a gitignored path without trying to fetch it"


def test_a_crosswalk_that_cannot_be_fetched_is_refused_with_a_message(monkeypatch, tmp_path):
    """And when the fetch itself fails, it exits under `refused:` rather than
    as a `RuntimeError` nobody catches."""
    monkeypatch.setattr(probe.crosswalk, "LOCAL", tmp_path / "absent.xlsx")

    def boom(*a, **k):
        raise RuntimeError("NCES did not answer")
    monkeypatch.setattr(probe.crosswalk, "download", boom)
    with pytest.raises(probe.MalformedSource, match="could not fetch the CIP-SOC crosswalk"):
        probe.crosswalk_pairs()


def test_a_family_row_is_told_apart_from_a_series_row_and_a_leaf():
    """`11.0000` names a whole family, `11.0700` a series, `11.0701` a
    programme. Counting them together would report the crosswalk as carrying a
    hierarchy it does not.

    **The two patterns OVERLAP** and the test did not say so: `11.0000`
    matches `SERIES` as well as `FAMILY`, and the code disambiguates with
    `SERIES.match(c) and not FAMILY.match(c)`. Asserting the patterns alone
    left that disambiguation untested — drop it and every family row is
    counted as a series as well, inflating the hierarchy figure the section
    argues from.
    """
    assert probe.FAMILY.match("11.0000") and not probe.FAMILY.match("11.0700")
    assert probe.SERIES.match("11.0700") and not probe.SERIES.match("11.0701")
    assert probe.SERIES.match("11.0000"), (
        "the patterns no longer overlap, so the disambiguation below is "
        "asserting something that cannot happen")

    got = probe.cip_hierarchy([(c, "11-1011") for c in ("11.0000", "11.0700", "11.0701", "13.0000")])
    assert got["family_rows"] == 2, "a family row was not counted as one"
    assert got["series_rows"] == 1, (
        "a family row was counted as a series as well — the two patterns "
        "overlap and the family must win")
    assert got["leaf_rows"] == 1


def test_the_document_quotes_only_figures_the_probe_produces():
    """Every figure on the page comes from the probe. These are the ones the
    argument rests on, so a changed figure fails here rather than being quoted
    for another month."""
    page = DOC.read_text(encoding="utf-8")
    for claim in ("2,143", "2,116", "**49**", "**0 of 1,016**", "867",
                  "14 Clusters, 72 Sub-Clusters", "All rights reserved"):
        assert claim in page, f"the page no longer states {claim!r}"


def test_the_document_calls_the_zero_match_safe_rather_than_a_problem():
    """The interesting half of the finding. A reader who sees "matches 0" and
    concludes the taxonomies disagree has it backwards — they align exactly,
    and the zero is the suffix failing loudly."""
    page = DOC.read_text(encoding="utf-8").lower()
    assert "safe failure" in page, (
        "the page no longer explains that matching nothing is the good case")
    assert "align" in page, "the page no longer states that the taxonomies align"


def test_the_soc_column_is_found_by_name_not_by_position(monkeypatch):
    """Half the file was trusted to keep its layout, and it was the half
    carrying the codes.

    The O*NET column was looked up by heading while the SOC column was read at
    a hardcoded `r[2]`. Four columns today, so reading the third by index keeps
    working — wrongly — the moment a fifth arrives.
    """
    moved = ["O*NET-SOC 2019 Code", "2018 SOC Code",
             "O*NET-SOC 2019 Title", "2018 SOC Title"]
    book = workbook([moved,
                     ["11-1011.00", "11-1011", "Chief Executives", "Chief Executives"]])
    monkeypatch.setattr(probe, "download", lambda url, into: archived(probe.ONET_MEMBER, book))

    got = probe.onet_to_soc(ours={"11-1011"})
    assert got["soc_codes_they_roll_up_to"] == 1
    # `in_onet_not_ours`, named outright. This was a conditional expression
    # over two possible keys — `x == [] if "x" in got else y == []` — which
    # asserts whichever key happens to be there and cannot fail if neither is:
    # a test hedging about the shape of the thing it is testing.
    assert "in_onet_not_ours" in got, "onet_to_soc stopped reporting the gap"
    assert got["in_onet_not_ours"] == [], (
        "the SOC column was read by position, so a reordered file yielded "
        "something that is not a SOC code")
    assert got["widest_soc"] == "11-1011"


def test_a_renamed_soc_column_is_refused_rather_than_guessed(monkeypatch):
    """A heading that has moved is a layout change. Reading the old index
    would keep working while counting the wrong column."""
    book = workbook([["O*NET-SOC 2019 Code", "O*NET-SOC 2019 Title", "Something Else"],
                     ["11-1011.00", "Chief Executives", "x"]])
    monkeypatch.setattr(probe, "download", lambda url, into: archived(probe.ONET_MEMBER, book))
    with pytest.raises(probe.MalformedSource, match="no column headed"):
        probe.onet_to_soc(ours=set())


def test_the_widest_fan_out_names_itself(monkeypatch):
    """The page's one concrete illustration of the fan-out — `15-1299
    Computer Occupations, All Other -> 10` — was written down while the probe
    emitted only the count. The illustration is printed now."""
    book = workbook([
        ["O*NET-SOC 2019 Code", "O*NET-SOC 2019 Title", "2018 SOC Code", "2018 SOC Title"],
        ["15-1299.01", "Web Administrators", "15-1299", "Computer Occupations, All Other"],
        ["15-1299.02", "GIS Technologists", "15-1299", "Computer Occupations, All Other"],
        ["11-1011.00", "Chief Executives", "11-1011", "Chief Executives"],
    ])
    monkeypatch.setattr(probe, "download", lambda url, into: archived(probe.ONET_MEMBER, book))

    got = probe.onet_to_soc(ours=set())
    assert got["largest_fan_out"] == 2
    assert got["widest_soc"] == "15-1299"
    assert got["widest_soc_title"] == "Computer Occupations, All Other", (
        "the widest fan-out does not name itself, so the page's example is "
        "again a figure the probe cannot produce")


def test_two_columns_matching_one_lookup_are_refused_rather_than_guessed():
    """`column_named` returned the first match.

    A heading reading "SOC Code and Title" satisfies both the code lookup and
    the title lookup, so two different figures would be read off one column
    with nothing saying so — the positional read this function exists to
    replace, arriving by another route.
    """
    with pytest.raises(probe.MalformedSource, match="2 columns are headed"):
        probe.column_named(["2018 SOC Code", "2018 SOC Code (rolled up)"], "SOC", "Code")

    # One match is still one answer.
    assert probe.column_named(
        ["O*NET-SOC 2019 Code", "2018 SOC Code"], "2018", "Code") == 1


def test_a_published_file_with_an_apostrophe_in_its_name_is_counted():
    """`[^"']*` excluded both quote characters from the href.

    A double-quoted href may legitimately contain an apostrophe, so
    `href="/o'brien.csv"` counted as no published file — and a missed file is
    a false zero, which is the direction that manufactures the licence
    conclusion. Only the delimiter that opened the attribute can close it.
    """
    assert probe.data_files('''href="/o'brien.csv"''') == ["/o'brien.csv"]
    assert probe.data_files("href='/x.xlsx?v=2'") == ["/x.xlsx"]
    # And a genuinely mismatched quote is still not a link.
    assert probe.data_files('''href="a.csv'"''') == []

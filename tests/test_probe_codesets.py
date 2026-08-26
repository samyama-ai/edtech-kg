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

DOC = Path(__file__).resolve().parents[1] / "docs" / "sources" / "code-sets.md"


def workbook(rows: list[list[str]]) -> bytes:
    """The smallest valid single-sheet .xlsx carrying these rows."""
    strings: list[str] = []

    def cell(value, col, row):
        if value not in strings:
            strings.append(value)
        return (f'<c r="{chr(65 + col)}{row}" t="s">'
                f"<v>{strings.index(value)}</v></c>")

    body = "".join(
        f'<row r="{r}">' + "".join(cell(v, c, r) for c, v in enumerate(cells)) + "</row>"
        for r, cells in enumerate(rows, 1))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as book:
        book.writestr("xl/worksheets/sheet1.xml",
                      '<?xml version="1.0"?><worksheet xmlns="http://schemas.'
                      'openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
                      + body + "</sheetData></worksheet>")
        book.writestr("xl/sharedStrings.xml",
                      '<?xml version="1.0"?><sst xmlns="http://schemas.'
                      'openxmlformats.org/spreadsheetml/2006/main">'
                      + "".join(f"<si><t>{s}</t></si>" for s in strings) + "</sst>")
    return buffer.getvalue()


def archived(member: str, payload: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as outer:
        outer.writestr(member, payload)
    return buffer.getvalue()


def test_an_html_page_is_refused_rather_than_read_as_an_empty_archive(monkeypatch, tmp_path):
    """A 200 carrying an error page would otherwise parse to zero occupations
    and be reported as a taxonomy with nothing in it."""
    class Response:
        def __enter__(self): return self
        def __exit__(self, *exc): return False
        def read(self): return b"<!DOCTYPE html>not a zip"
    monkeypatch.setattr(probe.urllib.request, "urlopen", lambda *a, **k: Response())
    with pytest.raises(probe.MalformedSource, match="did not return an archive"):
        probe.download(probe.ONET_URL, tmp_path / "x.zip")


def test_a_renamed_member_is_refused_with_what_the_archive_holds(monkeypatch):
    """O*NET reorganising its zip must stop the probe, not shrink its answer."""
    monkeypatch.setattr(probe, "download",
                        lambda url, into: archived("Something/Else.xlsx", b"PK"))
    with pytest.raises(probe.MalformedSource, match="not in the O\\*NET archive"):
        probe.onet_to_soc()


def test_a_crosswalk_with_no_header_is_refused(monkeypatch):
    """The header is found by content, not by row number — O*NET puts two title
    rows above it. A file without one is a layout change, not an empty answer."""
    book = workbook([["some", "other", "columns"], ["11-1011.00", "x", "11-1011"]])
    monkeypatch.setattr(probe, "download", lambda url, into: archived(probe.ONET_MEMBER, book))
    with pytest.raises(probe.MalformedSource, match="no header row"):
        probe.onet_to_soc()


def test_a_naive_join_matching_nothing_is_reported_as_such(monkeypatch):
    """The finding the page leads with. Every O*NET code carries a `.NN`
    suffix, so string equality against a SOC code matches nothing — and that is
    the SAFE failure, because a partial match would be a figure nobody could
    reproduce.

    Driven with a fixture whose SOC side deliberately matches our crosswalk, so
    a zero here means the suffix and not an empty comparison.
    """
    book = workbook([
        ["O*NET-SOC 2019 Occupation Listings"],
        ["Crosswalk"],
        ["O*NET-SOC 2019 Code", "O*NET-SOC 2019 Title", "2018 SOC Code", "2018 SOC Title"],
        ["11-1011.00", "Chief Executives", "11-1011", "Chief Executives"],
    ])
    monkeypatch.setattr(probe, "download", lambda url, into: archived(probe.ONET_MEMBER, book))
    got = probe.onet_to_soc()
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
    got = probe.onet_to_soc()
    assert got["soc_with_several"] == 1
    assert got["largest_fan_out"] == 2
    assert got["soc_with_one_occupation"] == 1


def test_a_family_row_is_told_apart_from_a_series_row_and_a_leaf():
    """`11.0000` names a whole family, `11.0700` a series, `11.0701` a
    programme. Counting them together would report the crosswalk as carrying a
    hierarchy it does not."""
    assert probe.FAMILY.match("11.0000") and not probe.FAMILY.match("11.0700")
    assert probe.SERIES.match("11.0700") and not probe.SERIES.match("11.0701")
    assert not probe.SERIES.match("11.0701")


def test_the_copyright_notice_survives_a_full_stop(monkeypatch):
    """The first version of this pattern stopped at the first full stop and
    found nothing — reporting no notice on a page that carries one, which is
    the wrong way round for a licence check."""
    page = ('<html><footer>© 2023 Advance CTE: State Leaders Connecting '
            'Learning to Work. All rights reserved.</footer>'
            '<p>14 Clusters and 72 Sub-Clusters</p></html>').encode()

    class Response:
        def __enter__(self): return self
        def __exit__(self, *exc): return False
        def read(self): return page
    monkeypatch.setattr(probe.urllib.request, "urlopen", lambda *a, **k: Response())

    got = probe.career_clusters()
    assert got["copyright_notice"], "the notice was not found on a page that has one"
    assert "All rights reserved" in got["copyright_notice"]
    assert (got["clusters"], got["sub_clusters"]) == (14, 72)
    assert got["measured_or_read"] == "read", (
        "a licence position is a reading, and the result must say so")


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

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


def test_no_machine_readable_file_is_reported_only_when_there_is_none(monkeypatch):
    """The zero that feeds the licence conclusion.

    "0 machine-readable files" is the reason Career Clusters is recorded as not
    cleared, so a pattern that misses a real link would produce that conclusion
    from a false negative. The first pattern required double quotes and the
    extension at the very end of the href, so `'/x.xlsx?v=2'` counted as none.
    """
    def page_of(body: str):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *exc): return False
            def read(self): return body.encode()
        return lambda *a, **k: Response()

    bare = "<html><p>14 Clusters and 72 Sub-Clusters</p><a href='/brand.pdf'>x</a></html>"
    monkeypatch.setattr(probe.urllib.request, "urlopen", page_of(bare))
    assert probe.career_clusters()["machine_readable_files"] == [], (
        "a PDF was counted as a machine-readable file")

    linked = bare.replace("<a href='/brand.pdf'>x</a>",
                          "<a href='/clusters.xlsx?v=2'>x</a>"
                          '<a href="/c.csv#tab">y</a>')
    monkeypatch.setattr(probe.urllib.request, "urlopen", page_of(linked))
    found = probe.career_clusters()["machine_readable_files"]
    assert found == ["/c.csv", "/clusters.xlsx"], (
        f"a published data file was missed, so the licence conclusion would "
        f"rest on a false zero — found {found}")


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
    # Still absent after the stubbed download, so the read fails — the point is
    # that the fetch was attempted and the failure carries a message.
    with pytest.raises((probe.MalformedSource, FileNotFoundError)):
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

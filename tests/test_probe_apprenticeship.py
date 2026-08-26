"""The apprenticeship probe, and the two documents that quote it.

The failure to guard against is not a crash. It is a probe that reports a clean
overlap because it compared nothing — `0 reachable only by apprenticeship`
reads as "the programme route covers everything" and is also what an empty set
gives you. Several of these drive the case where the answer would be wrong
rather than absent.

Workbooks are built in the test, so no network and no committed sample file.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from etl import probe_apprenticeship as probe
from tests.test_probe_cipsoc import workbook as cipsoc_workbook

APPRENTICESHIP = Path(__file__).resolve().parents[1] / "docs" / "sources" / "apprenticeship.md"
CAREERONESTOP = Path(__file__).resolve().parents[1] / "docs" / "sources" / "careeronestop.md"

SHEET = "O-NET-SOC 2019 Crosswalks"


def workbook(rows: list[list[str]]) -> bytes:
    """A single-sheet .xlsx carrying these rows, as bytes.

    Built by `tests.test_probe_cipsoc.workbook` rather than by a second builder
    here — the same reason the probe imports that module's reader instead of
    carrying its own. It OMITS a cell whose value is `""`, which is what Excel
    does for a blank, so a fixture can reach the reader's placement rule.
    """
    buffer = io.BytesIO()
    cipsoc_workbook(buffer, {SHEET: rows})
    return buffer.getvalue()


def crosswalks(monkeypatch, rapids: list[list[str]], cip: list[list[str]]):
    """Serve both O*NET workbooks without touching the network or `data/`."""
    books = {probe.RAPIDS_URL: workbook(rapids), probe.CIP_URL: workbook(cip)}
    monkeypatch.setattr(probe, "download", lambda url, into: books[url])


HEADER = ["RAPIDS Code", "RAPIDS Title", "O*NET-SOC 2019 Code", "O*NET-SOC 2019 Title"]


def test_the_suffix_means_a_naive_join_finds_nothing(monkeypatch):
    """The finding this page shares with `code-sets.md`, confirmed on a second
    file rather than cited from the first.

    Every O*NET-SOC code carries a `.NN` suffix, so string equality against a
    SOC code matches nothing — the SAFE failure, because a partial match would
    be a figure nobody could reproduce. Driven with a fixture whose SOC side
    deliberately matches our crosswalk, so a zero means the suffix and not an
    empty comparison.
    """
    crosswalks(monkeypatch,
               [HEADER, ["0001", "Electrician", "47-2111.00", "Electricians"]],
               [HEADER, ["46.0302", "Electrician", "47-2111.00", "Electricians"]])
    monkeypatch.setattr(probe, "our_soc", lambda: {"47-2111"})

    got = probe.routes()
    assert got["apprentice_soc"] == 1, "the rollup lost the occupation"
    assert got["apprenticeable_in_ours"] == 1, (
        "the rolled-up code did not join — the comparison is empty, so the "
        "zero below would mean nothing")
    assert got["naive_string_matches"] == 0, (
        "an O*NET-SOC code matched a SOC code by string equality — the suffix "
        "rule both this page and code-sets.md rest on no longer holds")


def test_an_occupation_reachable_only_by_apprenticeship_is_reported(monkeypatch):
    """The number the whole probe exists for. It has to be a set difference and
    not a count of rows: an occupation reachable by both routes is not part of
    the gap, however many apprenticeship codes point at it."""
    crosswalks(
        monkeypatch,
        [HEADER,
         ["0001", "Electrician", "47-2111.00", "Electricians"],
         # A second apprenticeship code for the SAME occupation. It must not
         # make the occupation count twice.
         ["0002", "Electrician (Maint)", "47-2111.01", "Electricians"],
         ["0003", "Machine Setter", "51-4081.00", "Machine Tool Setters"]],
        [HEADER, ["46.0302", "Electrician", "47-2111.00", "Electricians"]])
    monkeypatch.setattr(probe, "our_soc", lambda: {"47-2111", "51-4081"})

    got = probe.routes()
    assert got["rapids_codes"] == 3
    assert got["apprentice_soc"] == 2, "two distinct occupations, not three rows"
    assert got["both_ways"] == 1
    assert got["apprenticeship_only"] == ["51-4081"], (
        "the occupation with no programme route was not reported as the gap")


def test_an_occupation_missing_from_our_crosswalk_is_named_not_counted(monkeypatch):
    """A count of misses is not actionable; the codes are. This is the list a
    reader checks before believing the join is clean."""
    crosswalks(monkeypatch,
               [HEADER, ["0001", "Something New", "99-1234.00", "Novel Job"]],
               [HEADER, ["46.0302", "Electrician", "47-2111.00", "Electricians"]])
    monkeypatch.setattr(probe, "our_soc", lambda: {"47-2111"})

    got = probe.routes()
    assert got["apprentice_soc_missing_from_ours"] == ["99-1234"]


def test_a_crosswalk_with_no_header_is_refused(monkeypatch):
    """O*NET puts two title rows above the header, so it is found by content
    rather than by row number. A file without one is a layout change, not an
    empty answer — and an empty answer here reads as "nothing is
    apprenticeable"."""
    crosswalks(monkeypatch,
               [["some", "other", "columns"], ["0001", "x", "47-2111.00", "y"]],
               [HEADER, ["46.0302", "Electrician", "47-2111.00", "Electricians"]])
    with pytest.raises(probe.MalformedSource, match="no header row"):
        probe.routes()


def test_a_crosswalk_that_parses_to_nothing_is_refused(monkeypatch):
    """Zero rows is the reading that would report a perfect overlap."""
    crosswalks(monkeypatch,
               [HEADER],
               [HEADER, ["46.0302", "Electrician", "47-2111.00", "Electricians"]])
    with pytest.raises(probe.MalformedSource, match="parsed to zero rows"):
        probe.routes()


def test_a_second_sheet_is_refused_rather_than_guessed_at(monkeypatch):
    """These files carry one sheet and the probe resolves it through the
    workbook relationships. If one ever carries two, reading whichever came
    first is a plausible count of the wrong thing."""
    buffer = io.BytesIO()
    cipsoc_workbook(buffer, {SHEET: [HEADER, ["0001", "x", "47-2111.00", "y"]],
                             "Notes": [["ignore me"]]})
    monkeypatch.setattr(probe, "download", lambda url, into: buffer.getvalue())
    with pytest.raises(probe.MalformedSource, match="refusing to guess which sheet"):
        probe.routes()


def test_the_onet_column_is_found_by_name_not_by_position(monkeypatch):
    """These files carry four columns today, and reading the third by index
    would keep working — wrongly — if a fifth arrived. The fixture puts the
    O*NET-SOC column somewhere else entirely."""
    moved = ["RAPIDS Code", "O*NET-SOC 2019 Code", "RAPIDS Title", "Notes"]
    crosswalks(monkeypatch,
               [moved, ["0001", "47-2111.00", "Electrician", "n/a"]],
               [moved, ["46.0302", "47-2111.00", "Electrician", "n/a"]])
    monkeypatch.setattr(probe, "our_soc", lambda: {"47-2111"})
    got = probe.routes()

    # The CODE, not the count. Asserting `== 1` passed under the mutation this
    # test exists to catch: with the column hardcoded to index 2 the probe read
    # "Electrician" as the occupation, which is still exactly one occupation.
    assert got["apprentice_soc_missing_from_ours"] == [], (
        "the O*NET-SOC column was read by position, so a reordered file "
        "yielded something that is not a SOC code at all")
    assert got["apprenticeable_in_ours"] == 1, (
        "the reordered file did not join against the crosswalk")


def test_a_row_that_omits_a_cell_does_not_shift_the_columns(monkeypatch):
    """Excel omits a blank cell rather than writing an empty one, so a row with
    no title arrives as `<c r="A5">…</c><c r="C5">…</c>`. A reader that appends
    in document order would read the O*NET-SOC *title* as its code, and every
    figure after that stays plausible and is wrong.

    This is why the probe uses `probe_cipsoc.rows`, which places cells by their
    `r` attribute, rather than carrying a reader of its own.
    """
    crosswalks(
        monkeypatch,
        [HEADER,
         ["0001", "Electrician", "47-2111.00", "Electricians"],
         ["0002", "", "51-4081.00", "Machine Tool Setters"]],
        [HEADER, ["46.0302", "Electrician", "47-2111.00", "Electricians"]])
    monkeypatch.setattr(probe, "our_soc", lambda: {"47-2111", "51-4081"})

    got = probe.routes()
    assert got["apprentice_soc"] == 2, "the untitled row was dropped"
    assert got["apprenticeship_only"] == ["51-4081"], (
        "the untitled row's code was misread — the reader is placing cells by "
        "document order again")


def test_a_host_that_does_not_resolve_is_told_apart_from_one_that_refuses(monkeypatch):
    """The distinction the CareerOneStop page turns on, and the reason it can
    assert one finding and not the other.

    A name that resolves nowhere is broken at the publisher's end. A resolved
    address that refuses a connection cannot be told apart, from one network,
    from an outbound restriction. Reporting both as "unreachable" would let the
    page overclaim.
    """
    def resolve(host):
        if host == "gone.example":
            raise OSError(8, "nodename nor servname provided")
        return "10.0.0.1"
    monkeypatch.setattr(probe.socket, "gethostbyname", resolve)

    def refuse(*a, **k):
        raise probe.urllib.error.URLError("timed out")
    monkeypatch.setattr(probe.urllib.request, "urlopen", refuse)
    monkeypatch.setattr(probe, "REACH", [("gone", "https://gone.example/"),
                                         ("refusing", "https://refusing.example/")])

    by_name = {row["source"]: row for row in probe.reachable()}
    assert "does not resolve" in by_name["gone"]["status"]
    assert by_name["gone"]["dns"] is None
    assert "no connection" in by_name["refusing"]["status"], (
        "a refused connection is reported as a DNS failure — a claim the "
        "careeronestop page explicitly declines to make")
    assert by_name["refusing"]["dns"] == "10.0.0.1"


def test_the_documents_quote_only_figures_the_probe_produces():
    """Every figure on both pages comes from the probe. These are the ones the
    argument rests on, so a changed figure fails here rather than being quoted
    for another month."""
    page = APPRENTICESHIP.read_text(encoding="utf-8")
    for claim in ("1,439", "1,171", "**449**", "**419**", "**688**", "**356**",
                  "**63**", "**867**", "**0** of 449"):
        assert claim in page, f"apprenticeship.md no longer states {claim!r}"

    blocked = CAREERONESTOP.read_text(encoding="utf-8")
    assert "**403**" in blocked and "TCP 443 never opens" in blocked


def test_the_apprenticeship_page_does_not_claim_the_trades_are_the_gap():
    """The half of the finding that contradicts the issue. edtech-kg#39 assumes
    the exclusive occupations are well-paid trades; measured, construction and
    maintenance are 82% and 91% already reachable through a programme, and the
    gap is in Production. A page that lost that would be quoting a true number
    under a false story."""
    page = APPRENTICESHIP.read_text(encoding="utf-8").lower()
    assert "not the trades" in page, (
        "the page no longer says the gap is not in the trades")
    assert "production" in page, "the page no longer names where the gap is"


def test_the_careeronestop_page_states_what_it_cannot_establish():
    """A blocked source is easy to overclaim. The page must keep saying that a
    refused connection from one network is not proof the source is down."""
    page = CAREERONESTOP.read_text(encoding="utf-8").lower()
    assert "not established" in page
    assert "not cleared" in page, "the verdict is gone"
    assert "registered api key" in page, (
        "the page no longer says what reopening this needs")

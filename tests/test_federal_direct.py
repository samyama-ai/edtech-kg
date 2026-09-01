"""`docs/sources/federal-direct.md` against the run that produced it — #43.

Nothing here fetches. The probe's readers take their input, and the committed
record is what the page is checked against, in both directions: a figure on the
page that is not in the record is one somebody typed, and a figure in the
record that is not on the page is a measurement nobody published.

The reconciliation is the load-bearing claim — that the wrapper's 9,026,310 and
the direct file's 300,877 describe the same data — so it is asserted as
ARITHMETIC rather than as two numbers that happen to appear.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

from etl import probe_federal_direct as probe

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs" / "sources" / "federal-direct.md"
RECORD = ROOT / "docs" / "sources" / "federal-direct-measured.json"


@pytest.fixture(scope="module")
def record() -> dict:
    return json.loads(RECORD.read_text(encoding="utf-8"))


def figures(text: str) -> set[int]:
    """Every grouped number on the page. Grouped, because a bare `30` is a
    column count and also half the words in a document."""
    return {int(m.replace(",", ""))
            for m in re.findall(r"(?<![\d,])(\d{1,3}(?:,\d{3})+)(?![\d,])", text)}


def test_the_reconciliation_is_arithmetic_not_coincidence(record):
    """The page's central claim. Two numbers appearing near each other is not
    the same as one being the other times thirty."""
    ipeds = record["ipeds"]
    assert ipeds["rows"] * len(ipeds["count_columns"]) == ipeds["rows_x_counts"]
    assert ipeds["rows_x_counts"] == ipeds["wrapper_rows"], (
        "the direct file no longer reconciles with the wrapper's row count, "
        "so the page's central finding is stale")
    assert ipeds["reconciles"] is True


def test_the_award_count_is_not_the_row_count(record):
    """The distinction the page exists to draw. If these ever coincide the
    page's argument evaporates and the wording has to change."""
    ipeds = record["ipeds"]
    assert ipeds["awards_first_major"] != ipeds["wrapper_rows"]
    assert ipeds["awards_first_major"] > ipeds["rows"]


def test_every_figure_on_the_page_comes_from_the_record(record):
    """A number on the page that is not in the run is one somebody typed."""
    measured = {record["ipeds"]["rows"], record["ipeds"]["rows_x_counts"],
                record["ipeds"]["wrapper_rows"],
                record["ipeds"]["awards_first_major"]}
    # The other direction is covered below; this one catches invention.
    unexplained = {n for n in figures(PAGE.read_text(encoding="utf-8"))
                   if n not in measured}
    assert not unexplained, (
        f"these grouped figures are on the page and not in the record: "
        f"{sorted(unexplained)}")


def test_the_page_publishes_what_was_measured(record):
    """And the other direction. A measurement nobody published is a run that
    did not need making."""
    page = PAGE.read_text(encoding="utf-8")
    for key in ("rows", "rows_x_counts", "wrapper_rows", "awards_first_major"):
        value = f"{record['ipeds'][key]:,}"
        assert value in page, f"the page does not state {key} ({value})"


def test_the_page_states_the_date_the_record_holds(record):
    page = PAGE.read_text(encoding="utf-8")
    assert record["retrieved_at"] in page, (
        "the page and the record disagree about when this was read")


def test_the_page_does_not_call_the_row_count_a_number_of_graduates():
    """The failure mode this document is about. Asserted on the words a reader
    acts on, because the whole finding is that one number reads as another."""
    page = PAGE.read_text(encoding="utf-8")
    assert "is not a number of graduates" in page
    assert "CCD" in page and "Not established" in page, (
        "the page no longer says plainly that CCD was not established, which "
        "is the one route that did not work")


def test_a_key_requirement_is_reported_as_one(record):
    """A 403 for a missing key and a 403 by agent policy look identical from
    the status line, and they call for opposite conclusions."""
    api = record["routes"]["Scorecard API"]
    assert api["status"] == 403 and api.get("needs_a_key") is True
    bulk = record["routes"]["Scorecard bulk, institution"]
    assert bulk["status"] == 200 and not bulk.get("needs_a_key"), (
        "the bulk files needing no key is half the Scorecard finding")


def test_the_revised_member_is_named_not_silently_chosen(record):
    """Two members, one revised. A silent pick is a silent difference in every
    figure downstream."""
    ipeds = record["ipeds"]
    assert len(ipeds["members"]) == 2
    assert not ipeds["file_read"].lower().endswith("_rv.csv")
    assert ipeds["file_read"] in ipeds["members"]
    for member in ipeds["members"]:
        assert member in PAGE.read_text(encoding="utf-8"), (
            f"{member} is in the record and not named on the page")


# --------------------------------------------------------------------------
# Driving the readers. Everything above asserts against the committed record,
# which says nothing about the code that produced it — the shape of test this
# repo has been caught by repeatedly.
# --------------------------------------------------------------------------

def _zip(members: dict) -> bytes:
    import io as _io
    import zipfile as _zipfile
    buffer = _io.BytesIO()
    with _zipfile.ZipFile(buffer, "w") as book:
        for name, text in members.items():
            book.writestr(name, text)
    return buffer.getvalue()


HEADER = ("UNITID,CIPCODE,MAJORNUM,AWLEVEL,XCTOTALT,CTOTALT,XCTOTALM,CTOTALM")
BASE = HEADER + "\n1,01.0101,1,5,R,10,R,4\n1,01.0101,2,5,R,7,R,3\n"
REVISED = HEADER + "\n1,01.0101,1,5,R,99,R,44\n"


def _serve(monkeypatch, blob: bytes):
    class Response:
        status = 200
        headers = {"Content-Length": str(len(blob))}
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, n=None): return blob
    monkeypatch.setattr(probe, "_open", lambda url, method: Response())


def test_the_unrevised_member_is_the_one_read(monkeypatch):
    """Two members and only one is the release this repo means. Picking by
    position rather than by name would take whichever the zip happens to list
    first, and the difference is silent in every figure downstream."""
    _serve(monkeypatch, _zip({"c2022_a_rv.csv": REVISED, "c2022_a.csv": BASE}))
    shape = probe.ipeds_shape()
    assert shape["file_read"] == "c2022_a.csv"
    # 99 is only in the revised file; reading it would show up here.
    assert shape["awards_first_major"] == 10


def test_a_second_major_is_not_counted_as_another_award(monkeypatch):
    """`MAJORNUM` 2 is a second major on the SAME award. Summing every row
    counts those students twice, which is how a completions total quietly
    overstates itself — the fixture carries one of each."""
    _serve(monkeypatch, _zip({"c2022_a.csv": BASE}))
    assert probe.ipeds_shape()["awards_first_major"] == 10        # not 17


def test_a_zip_without_an_unrevised_member_is_refused(monkeypatch):
    """A layout change must not be guessed through."""
    _serve(monkeypatch, _zip({"c2022_a_rv.csv": REVISED}))
    with pytest.raises(probe.Unreachable, match="expected one unrevised"):
        probe.ipeds_shape()


def test_a_file_with_no_count_columns_is_refused(monkeypatch):
    """Every figure on the page is rows x count columns. Zero columns would
    make that product zero and reconcile against nothing, silently."""
    _serve(monkeypatch, _zip({"c2022_a.csv": "UNITID,CIPCODE,MAJORNUM,AWLEVEL\n1,01,1,5\n"}))
    with pytest.raises(probe.Unreachable, match="no demographic count columns"):
        probe.ipeds_shape()


def test_a_missing_key_is_told_apart_from_a_refusal(monkeypatch):
    """Both are 403. They call for opposite conclusions — register for a key,
    or stop asking."""
    import urllib.error

    def refuse(url, method):
        raise urllib.error.HTTPError(
            url, 403, "Forbidden", {},
            __import__("io").BytesIO(b'{"error":{"code":"API_KEY_MISSING"}}'))

    monkeypatch.setattr(probe, "_open", refuse)
    assert probe.reach("https://example.test/x", True)["needs_a_key"] is True


def test_a_plain_refusal_is_not_reported_as_a_missing_key(monkeypatch):
    """The other direction, or the flag means nothing."""
    import urllib.error

    def refuse(url, method):
        raise urllib.error.HTTPError(
            url, 403, "Forbidden", {}, __import__("io").BytesIO(b"go away"))

    monkeypatch.setattr(probe, "_open", refuse)
    assert not probe.reach("https://example.test/x", True).get("needs_a_key")


def test_a_route_that_does_not_answer_is_refused_not_recorded(monkeypatch):
    """An unreachable route recorded as a status would publish a measurement
    of nothing."""
    import urllib.error

    def down(url, method):
        raise urllib.error.URLError("name or service not known")

    monkeypatch.setattr(probe, "_open", down)
    with pytest.raises(probe.Unreachable):
        probe.reach("https://example.test/x", False)


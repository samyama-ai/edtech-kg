"""`institution-identity.md` against the run that produced it — #45.

Nothing here fetches. Everything the readers do takes its input, and the
committed record is what the page is checked against, in both directions.

Seven tests DRIVE the readers rather than reading the record — the trap this
repo keeps hitting, where a suite asserts against an artifact and says nothing
about the code that wrote it.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

from etl import probe_institution_identity as probe

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs" / "sources" / "institution-identity.md"
RECORD = ROOT / "docs" / "sources" / "institution-identity-measured.json"


@pytest.fixture(scope="module")
def record() -> dict:
    return json.loads(RECORD.read_text(encoding="utf-8"))


def page() -> str:
    return PAGE.read_text(encoding="utf-8")


def grouped(text: str) -> set[int]:
    return {int(m.replace(",", ""))
            for m in re.findall(r"(?<![\d,])(\d{1,3}(?:,\d{3})+)(?![\d,])", text)}


# ---------------------------------------------------------------- the page

def test_the_page_names_unitid_as_the_identifier(record):
    """The question #45 asks. An answer buried in a table is not an answer."""
    text = page()
    assert "canonical identifier is `UNITID`" in text
    assert record["identity"]["unitid_is_unique"] is True, (
        "UNITID is no longer unique per row and the page's verdict is wrong")


def test_the_page_states_opeid_is_not_an_identity(record):
    """The finding that stops a three-campus system collapsing to one node."""
    shared = record["identity"]["opeids_shared_by_several"]
    involved = record["identity"]["institutions_sharing_an_opeid"]
    assert shared > 0 and involved > shared, (
        "OPEID no longer covers several institutions, so the page's warning "
        "describes something that stopped being true")
    for figure in (shared, involved):
        assert str(figure) in page(), f"the page omits {figure}"


def test_the_sentinel_is_named_and_counted(record):
    """`-2` is not missing data and not a number. `99-9999 NO MATCH` was read
    as an occupation until #70; this is the same shape one collection over."""
    text, ident = page(), record["identity"]
    assert "sentinel" in text.lower()
    assert str(ident["on_the_sentinel"]) in text
    assert f"{ident['columns_using_the_sentinel']} of the {ident['total_columns']}" in text, (
        "the page does not say how widely the sentinel is used, which is the "
        "part that generalises beyond this one column")


def test_the_page_says_closure_and_merger_do_not_overlap(record):
    """Zero institutions carry both, so code checking one misses the other."""
    after = record["afterlife"]
    assert after["with_both"] == 0, (
        "an institution now has both a close date and a successor, so the "
        "page's 'disjoint' claim is stale")
    assert "**Zero carry both.**" in page()


def test_the_page_gives_a_rule_for_an_institution_that_is_gone(record):
    """#45's done-when. "Nothing" is the wrong answer for a student asking
    about a college they attended."""
    text = page()
    assert "never nothing" in text.lower() or "wrong answer" in text.lower()
    assert "NEWID" in text and "close date" in text


def test_ror_is_reported_as_not_a_bridge(record):
    """Reported as measured, not as an assumption — and the distinction
    between "no IPEDS id" and "a two-hop route via Wikidata" is the useful
    half."""
    ror = record["ror"]
    assert ror["carries_ipeds"] is False
    assert "not a bridge" in page().lower()
    assert str(ror["sampled"]) in page(), "the page does not say how many were sampled"


def test_wikidata_is_a_bridge_and_not_an_identity(record):
    text = page()
    assert f"{record['wikidata_items_with_an_ipeds_id']:,}" in text
    assert "never an identity" in text or "refused as an identity" in text


def test_every_grouped_figure_on_the_page_is_in_the_record(record):
    known = {record["identity"][k] for k in
             ("institutions", "distinct_unitid", "distinct_real_opeid")}
    known.add(record["wikidata_items_with_an_ipeds_id"])
    unexplained = grouped(page()) - known
    assert not unexplained, (
        f"these grouped figures are on the page and in no record: "
        f"{sorted(unexplained)}")


def test_the_page_says_what_it_does_not_establish():
    """Coverage is an upper bound, not an overlap; one year, not a history."""
    text = page()
    assert "does not establish" in text.lower()
    for limit in ("upper bound", "One year", "sampled"):
        assert limit.lower() in text.lower(), f"the limits omit {limit!r}"


# ------------------------------------------------------- driving the readers

HEADER = "UNITID,OPEID,INSTNM,CLOSEDAT,NEWID,CYACTIVE"


def rows(*lines: str) -> list[dict]:
    import csv
    import io as _io
    return list(csv.DictReader(_io.StringIO(HEADER + "\n" + "\n".join(lines))))


def test_the_sentinel_is_not_counted_as_an_opeid():
    """The defect this page exists to prevent, driven rather than described."""
    found = probe.identity(rows(
        "1,-2,A,-2,,1", "2,-2,B,-2,,1", "3,100200,C,-2,,1"))
    assert found["on_the_sentinel"] == 2
    assert found["distinct_real_opeid"] == 1
    assert found["opeids_shared_by_several"] == 0, (
        "the sentinel was counted as an OPEID shared by two institutions, "
        "which is exactly the false merge this measurement is about")


def test_a_genuinely_shared_opeid_is_counted():
    """The other direction, or the check above passes by refusing everything."""
    found = probe.identity(rows(
        "1,100200,A,-2,,1", "2,100200,B,-2,,1", "3,300400,C,-2,,1"))
    assert found["opeids_shared_by_several"] == 1
    assert found["institutions_sharing_an_opeid"] == 2


def test_a_close_date_and_a_successor_are_counted_apart():
    found = probe.afterlife(rows(
        "1,100200,A,06/30/2022,,1",     # closed
        "2,100300,B,-2,999999,1",       # merged
        "3,100400,C,-2,,1"))            # neither
    assert found["with_a_close_date"] == 1
    assert found["with_a_successor"] == 1
    assert found["with_both"] == 0


def test_an_institution_with_both_is_reported_as_both():
    """`with_both` is the page's headline. A counter that can only return 0
    would prove the claim by construction."""
    found = probe.afterlife(rows("1,100200,A,06/30/2022,999999,1"))
    assert found["with_both"] == 1


def test_an_empty_directory_is_refused_not_reported_as_zero():
    with pytest.raises(probe.Unreachable, match="empty"):
        probe.identity([])


def test_wikidata_refusing_is_not_recorded_as_no_coverage(monkeypatch):
    """A 429 written down as zero publishes our own rate limit as a fact
    about Wikidata."""
    monkeypatch.setattr(probe.time, "sleep", lambda *a: None)

    def refuse(url, timeout=90, accept=None):
        raise OSError("429 Too Many Requests")

    monkeypatch.setattr(probe, "_open", refuse)
    with pytest.raises(probe.Unreachable, match="four attempts"):
        probe.wikidata_coverage()


def test_ror_returning_nothing_is_refused_not_divided_by(monkeypatch):
    monkeypatch.setattr(probe.time, "sleep", lambda *a: None)

    class Empty:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, n=None): return b'{"items": []}'

    monkeypatch.setattr(probe, "_open", lambda *a, **k: Empty())
    with pytest.raises(probe.Unreachable, match="no organisations"):
        probe.ror_external_ids(pages=1)

"""One reading of the crosswalk's SOC codes — edtech-kg#112.

Three modules read the same workbook by three routes and filtered it three
ways. `probe_bls` scanned the SOC column of every sheet and excluded
`{99-9999, 00-0000}`; `probe_codesets` derived the codes from the CIP-SOC
pairs it had already parsed and excluded only the sentinel;
`probe_apprenticeship` parsed those pairs itself and did the same. All three
produced 867 codes, which is how the disagreement stayed invisible: `00-0000`
is not in this release, so the narrower filter was right by accident.

The dangerous half was never the duplication. `probe_bls` returned an EMPTY SET
when the workbook was absent, and `data/` is gitignored — so on a fresh clone
the published figures were

    crosswalk_soc_codes      0
    crosswalk_codes_covered  0
    crosswalk_codes_missing  0

and `0 missing` reads as nothing missing. Reproduced before the change.
"""

from __future__ import annotations

import pytest

from etl import probe_bls, probe_cipsoc
from tests.test_probe_bls import workbook


def test_a_missing_workbook_is_never_an_empty_set(tmp_path, monkeypatch):
    """The failure this issue is about, asserted directly.

    An empty set is also what a real measurement of zero looks like, and the
    caller subtracts it: `missing = reachable - projected` is empty too, so
    the probe published `0 missing` from a file nobody had downloaded.
    """
    monkeypatch.setattr(probe_cipsoc, "LOCAL", tmp_path / "absent.xlsx")
    with pytest.raises(probe_cipsoc.MissingSource, match="not at"):
        probe_cipsoc.soc_codes()


def test_the_refusal_names_the_command_that_fixes_it(tmp_path, monkeypatch):
    """A refusal a reader cannot act on is a traceback with better manners.

    Driven through `soc_codes()`. The first version of this test RAISED the
    exception itself and then asserted on the string it had just written,
    which passes whatever the module does.
    """
    monkeypatch.setattr(probe_cipsoc, "LOCAL", tmp_path / "absent.xlsx")
    with pytest.raises(probe_cipsoc.MissingSource) as refused:
        probe_cipsoc.soc_codes()
    message = str(refused.value)
    assert "etl.probe_cipsoc" in message, "the refusal does not say how to fix it"
    assert str(tmp_path / "absent.xlsx") in message, "it does not say which file"


def test_the_non_occupation_codes_are_one_set_not_three():
    """`00-0000` is the one the narrower filters missed. It is not in this
    release, so all three agreed anyway — an agreement that would have ended
    silently the day a code of that shape appeared."""
    assert probe_cipsoc.NOT_AN_OCCUPATION == {"99-9999", "00-0000"}
    assert probe_cipsoc.NO_MATCH_SOC in probe_cipsoc.NOT_AN_OCCUPATION


def test_a_sentinel_in_the_pairs_never_reaches_the_codes():
    """Driven through the derivation route, which is the one two callers use."""
    mapped = [("11.0101", "13-2011"), ("99.9999", "99-9999"), ("00.0000", "00-0000")]
    assert probe_cipsoc.soc_codes(mapped) == {"13-2011"}


def crosswalk_like(path, extra_sheet=None):
    """A workbook shaped like the real one: a CIP-SOC sheet, and a second sheet.

    Synthetic ON PURPOSE, and this file carried a cache-gated version first.
    That one skipped wherever `data/` is absent — which is CI, always — so the
    reconciliation it existed to hold would have been checked on developer
    machines and nowhere else. A skip is indistinguishable from a pass in every
    summary line.
    """
    book = workbook(path, "CIP-SOC", [
        ["CIP Code", "SOC Code"],
        ["11.0101", "13-2011"],
        ["51.3801", "29-1141"],
        ["99.9999", "99-9999"],
    ])
    return book


def test_the_two_routes_agree_on_a_workbook_shaped_like_the_real_one(tmp_path, monkeypatch):
    """The reconciliation, kept measured rather than remembered.

    Both routes survive the merge because they cost differently — the workbook
    read is ~650ms and the derivation ~0.5ms, and `probe_codesets` does it
    twice. That is only safe while they agree.
    """
    monkeypatch.setattr(probe_cipsoc, "LOCAL", crosswalk_like(tmp_path / "c.xlsx"))
    from_workbook = probe_cipsoc.soc_codes()
    from_pairs = probe_cipsoc.soc_codes([("11.0101", "13-2011"),
                                         ("51.3801", "29-1141"),
                                         ("99.9999", "99-9999")])
    assert from_workbook == from_pairs == {"13-2011", "29-1141"}


def test_the_routes_differ_only_where_a_second_sheet_carries_extra_codes(tmp_path, monkeypatch):
    """WHERE THEY WOULD DIVERGE, so "they agree" is a measurement and not luck.

    The workbook read scans the SOC column of EVERY sheet; the derivation reads
    the CIP-SOC pairs. On the published release those are the same 867 codes,
    which is exactly why the disagreement went unnoticed for three
    implementations. Given a sheet the real file does not have, they part —
    and this says which way round, so a future release growing one is a
    failure with an explanation rather than a puzzle.
    """
    book = workbook(tmp_path / "two.xlsx", "Other Sheet", [
        ["SOC Code", "Title"],
        ["47-2111", "Electricians"],
    ])
    monkeypatch.setattr(probe_cipsoc, "LOCAL", book)
    assert probe_cipsoc.soc_codes() == {"47-2111"}
    assert probe_cipsoc.soc_codes([("11.0101", "13-2011")]) == {"13-2011"}


def test_every_caller_reads_through_the_one_function(tmp_path, monkeypatch):
    """The point of the consolidation, asserted at the CALL SITES rather than
    at the function — a caller can still filter afterwards and undo it.

    Driven against a synthetic workbook so it holds on a clean checkout, which
    is the machine the old empty-set behaviour was wrong on.
    """
    monkeypatch.setattr(probe_cipsoc, "LOCAL", crosswalk_like(tmp_path / "c.xlsx"))
    reported = {
        "probe_bls": probe_bls.crosswalk_soc(),
        "probe_cipsoc": probe_cipsoc.soc_codes(),
    }
    assert len(set(map(frozenset, reported.values()))) == 1, {
        name: sorted(codes) for name, codes in reported.items()}
    assert reported["probe_bls"] == {"13-2011", "29-1141"}

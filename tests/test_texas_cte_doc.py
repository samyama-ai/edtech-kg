"""`docs/sources/texas-cte.md` held to the record it quotes.

The repo's most common review finding is one figure written in several places
and changed in one. This page quotes seven figures from
`texas-cte-measured.json` — a re-run that moves any of them must fail here
rather than leave the prose reading as measured.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "sources" / "texas-cte.md"
RECORD = json.loads((ROOT / "docs" / "sources"
                     / "texas-cte-measured.json").read_text(encoding="utf-8"))

TEXT = DOC.read_text(encoding="utf-8")
FLAT = " ".join(TEXT.split())


def stated(pattern: str) -> int:
    """The figure the page states, or a failure naming the sentence."""
    found = re.search(pattern, FLAT)
    assert found, f"the page no longer states a figure matching {pattern!r}"
    return int(found.group(1).replace(",", ""))


def test_the_row_count_agrees():
    assert stated(r"\| rows \| \*\*([\d,]+)\*\* \|") == RECORD["courses"]["rows"]


def test_the_cte_count_agrees():
    assert stated(r"CTE-flagged courses \| \*\*([\d,]+)\*\*") \
        == RECORD["courses"]["cte_courses"]


def test_the_table_count_agrees():
    assert stated(r"\*\*([\d,]+) code tables\*\*") \
        == RECORD["tables_in_download"]


def test_the_flag_values_agree():
    """`H` (531), `M` (2) — quoted in prose, and the reason the obvious guess
    of 1/Y produces a wrong finding rather than a failed one."""
    values = RECORD["courses"]["cte_flag_values"]
    for value in ("H", "M"):
        assert re.search(rf"`{value}` \({values[value]}\)", FLAT), (
            f"the page no longer states {value}={values[value]}")


def test_the_empty_columns_are_still_empty_in_the_record():
    """The page's central claim. If a re-run populates either column the
    finding is wrong, and this page says the opposite of the measurement."""
    populated = RECORD["cluster_columns_populated"]
    assert populated == {"Subject": 0, "Subject Area": 0}, (
        f"the record now shows {populated}; the page says both are empty on "
        f"every row")
    assert "EMPTY on every row" in TEXT or "empty on all" in FLAT


def test_the_no_soc_claim_matches_the_record():
    total = sum(v["soc_shaped"] for v in RECORD["code_shaped_matches"].values())
    assert total == 0, (
        f"the record now holds {total} SOC-shaped codes; the page says zero, "
        f"and 'no route to an occupation' rests on it")
    assert re.search(r"SOC-shaped codes \(`nn-nnnn`\): zero", FLAT) or \
        "SOC: zero" in FLAT


def test_the_cip_false_positive_count_agrees():
    total = sum(v["cip_shaped"] for v in RECORD["code_shaped_matches"].values())
    assert stated(r"CIP-shaped codes \(`nn\.nnnn`\): ([\d,]+) matches") == total


def test_the_page_does_not_call_them_statute_references_without_showing_one():
    """The verdict is a reading, so the evidence for it has to be reachable —
    the record stores sample matches for exactly this."""
    if "statute reference" not in FLAT:
        pytest.skip("the page no longer makes that claim")
    samples = [s for v in RECORD["code_shaped_matches"].values()
               for s in v.get("samples", [])]
    assert samples, (
        "the page calls the matches statute references but the record holds "
        "no sample of them, so the verdict cannot be re-checked")

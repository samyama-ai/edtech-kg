"""`docs/sources/geography.md` held to the record it quotes, both directions.

The page's claim is that point geography is already available in a source this
repo cleared. Every figure supporting that must come from
`geography-measured.json` — the page said "nothing is typed" while every figure
in it was, which is the failure this file exists to make impossible.
"""

from __future__ import annotations

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "sources" / "geography.md"
RECORD = json.loads((ROOT / "docs" / "sources"
                     / "geography-measured.json").read_text(encoding="utf-8"))

TEXT = DOC.read_text(encoding="utf-8")
FLAT = " ".join(TEXT.split())
CCD = RECORD["directories"]["ccd_schools"]
IPEDS = RECORD["directories"]["ipeds_institutions"]


def stated(pattern: str) -> int:
    found = re.search(pattern, FLAT)
    assert found, f"the page no longer states a figure matching {pattern!r}"
    return int(found.group(1).replace(",", ""))


def test_the_page_cites_the_command_that_prints_its_figures():
    """CONTRIBUTING: "If you cannot point at the command, delete the figure."
    The page claimed "read live from the APIs named" and named no command."""
    assert "python -m etl.probe_geography" in TEXT
    assert "geography-measured.json" in TEXT


def test_the_populations_agree():
    assert stated(r"CCD school directory, 2022 \| ([\d,]+) \|") == CCD["population"]
    assert stated(r"IPEDS institution directory, 2022 \| ([\d,]+) \|") \
        == IPEDS["population"]


def test_the_sample_size_and_pages_agree():
    assert stated(r"\| ([\d,]+) over pages \[") == CCD["sampled"]
    pages = re.search(r"over pages (\[[\d, ]+\])", FLAT)
    assert pages and json.loads(pages.group(1)) == CCD["pages_read"], (
        "the page names pages the record did not read")


def test_the_ipeds_census_claim_is_true_of_the_record():
    """"a census, not a sample" is the strongest claim on the page."""
    assert IPEDS["is_census"] is True, (
        "the record no longer reports a census; the page says it is one")
    assert "a census, not a sample" in FLAT


def test_full_coverage_is_what_the_record_shows():
    for name, got in (("CCD", CCD), ("IPEDS", IPEDS)):
        assert got["absent"] == 0 and got["null_island"] == 0, (
            f"{name} now has uncovered rows; the page says 100%")
        assert got["usable_coordinates"] == got["sampled"], name
    assert FLAT.count("**100.0%**") >= 2


def test_the_page_size_trap_agrees():
    delivered = RECORD["page_size_requested_vs_delivered"]
    assert stated(r"return \*\*([\d,]+) rows\*\*") == delivered["100"]
    assert delivered["100"] == delivered["500"], (
        "the page says both requested sizes deliver the same; the record "
        "no longer shows that")
    assert stated(r"\*\*(\d+) pages, not 1,023\*\*") == CCD["pages_in_population"]


def test_the_boundary_figures_agree():
    bounds = RECORD["boundaries"]
    assert stated(r"\*\*(\d+) state files\*\*") == bounds["state_files"]
    for year in bounds["vintage"]:
        assert year in FLAT, f"the page no longer names the {year} vintage"


def test_the_vintage_matches_the_data_year_the_page_relies_on():
    """The page's boundary argument is that TIGER and the directories can be
    pinned to the same year. If TIGER stops publishing 2022 that argument goes,
    and the page must not keep making it."""
    assert "2022" in RECORD["boundaries"]["vintage"], (
        "TIGER no longer publishes a 2022 vintage; the page's "
        "same-year-pinning argument no longer holds")

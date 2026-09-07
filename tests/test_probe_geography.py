"""What the geography probe reports, without touching the network.

`coverage()` and `page_size()` are driven through a stubbed `get`, so every
case here is deterministic. The live figures are in
`docs/sources/geography-measured.json`.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from etl import probe_geography as probe

ROOT = pathlib.Path(__file__).resolve().parent.parent
RECORD = ROOT / "docs" / "sources" / "geography-measured.json"


def stub(monkeypatch, pages: dict, count: int, per_page: int):
    """Serve the API's shape: `?per_page=1` for the count, `?page=N` for rows."""
    def fake(url: str) -> bytes:
        if "per_page=1&" in url or url.endswith("per_page=1"):
            first = pages.get(1) or [{}]
            return json.dumps({"count": count, "results": first[:1]}).encode()
        if "per_page=" in url:
            # The cap: any requested size above it delivers `per_page` rows.
            return json.dumps({"count": count,
                               "results": (pages.get(1) or [])[:per_page]}).encode()
        page = int(url.split("page=")[1].split("&")[0])
        return json.dumps({"count": count, "results": pages.get(page, [])}).encode()
    monkeypatch.setattr(probe, "get", fake)


def rows(n: int, lat=34.0, lon=-86.0):
    return [{"latitude": lat, "longitude": lon, "fips": "01"} for _ in range(n)]


def test_a_population_that_fits_one_page_is_a_census(monkeypatch):
    stub(monkeypatch, {1: rows(60)}, count=60, per_page=60)
    got = probe.coverage("https://x/")
    assert got["is_census"] is True
    assert got["pages_read"] == [1]
    assert got["usable_coordinates"] == 60


def test_the_last_page_is_always_read(monkeypatch):
    """A directory ordered by state, sampled only from the front, is a sample of
    Alabama. The stride must reach the end."""
    pages = {p: rows(10) for p in range(1, 12)}
    stub(monkeypatch, pages, count=110, per_page=10)
    got = probe.coverage("https://x/", wanted_pages=3)
    assert got["pages_in_population"] == 11
    assert max(got["pages_read"]) == 11, "the final page must be sampled"
    assert got["is_census"] is False


def test_null_island_is_not_counted_as_located(monkeypatch):
    """(0, 0) is in the Atlantic. A row carrying it has a coordinate column and
    no location, and counting it as covered overstates the finding."""
    stub(monkeypatch, {1: rows(2) + rows(3, lat=0.0, lon=0.0)},
         count=5, per_page=5)
    got = probe.coverage("https://x/")
    assert got["usable_coordinates"] == 2
    assert got["null_island"] == 3
    assert got["absent"] == 0


def test_a_missing_coordinate_is_absent_not_zero(monkeypatch):
    stub(monkeypatch, {1: rows(1) + [{"latitude": None, "longitude": None}]},
         count=2, per_page=2)
    got = probe.coverage("https://x/")
    assert got["absent"] == 1 and got["usable_coordinates"] == 1


def test_the_delivered_page_size_is_asked_for_not_assumed(monkeypatch):
    """`per_page` is ignored above a cap. A stride computed from the REQUESTED
    size gives a page past the end and a 404, which reads as the source being
    broken rather than the caller being wrong."""
    stub(monkeypatch, {1: rows(10000)}, count=102268, per_page=10000)
    assert probe.page_size("https://x/") == {"100": 10000, "500": 10000}


def test_an_unreachable_source_is_named_not_swallowed(monkeypatch):
    def gone(url):
        raise probe.Unreachable(f"{url}: boom")
    monkeypatch.setattr(probe, "get", gone)
    with pytest.raises(probe.Unreachable, match="boom"):
        probe.coverage("https://x/")


def test_the_committed_record_has_the_shape_the_doc_reads():
    got = json.loads(RECORD.read_text(encoding="utf-8"))
    assert set(got) >= {"retrieved_at", "page_size_requested_vs_delivered",
                        "directories", "boundaries"}
    for name in ("ccd_schools", "ipeds_institutions"):
        assert set(got["directories"][name]) >= {
            "population", "pages_read", "is_census", "sampled",
            "usable_coordinates", "absent", "null_island"}

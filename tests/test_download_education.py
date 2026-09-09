"""The education download, driven without the network.

edtech-kg#7. Three things decide whether the cached slice is trustworthy, and
none of them is visible in the file that lands on disk: whether the walk
followed the source's own `next` link, whether it stopped short, and whether
an empty answer was written down as a measurement of zero.

`tests/conftest.py` refuses real sockets in this suite, so a test here that
reached the API would fail rather than pass slowly — which is how
`test_sced_doc.py` was found making live requests on every full-suite run.
"""

from __future__ import annotations

import json

import pytest

from etl import download_education as dl


class Api:
    """The Urban Institute API as pages, answering only what it is asked."""

    def __init__(self, pages):
        self.pages = pages
        self.asked: list[str] = []

    def __call__(self, url):
        self.asked.append(url)
        for match, body in self.pages:
            if match in url:
                return body
        raise AssertionError(f"unexpected request: {url}")


def page(count, rows, next_url=None):
    return {"count": count, "results": rows, "next": next_url}


def rows(n, start=0):
    return [{"unitid": start + i} for i in range(n)]


def test_the_walk_follows_the_sources_own_next_link(monkeypatch):
    """**Not a computed page number.** `docs/sources/geography.md` records
    what computing one costs: `per_page` is ignored above a cap, so a stride
    derived from the requested size runs past the end and 404s — which reads
    as the source being broken rather than the caller being wrong.
    """
    api = Api([("page=2", page(3, rows(1, 2))),
               ("completions", page(3, rows(2), "https://x/?page=2"))])
    monkeypatch.setattr(dl, "get", api)
    collected, total = dl.walk("https://x/completions")
    assert total == 3
    assert len(collected) == 3
    assert "page=2" in api.asked[1], (
        "the second request was not the link the source offered")


def test_a_walk_that_stops_short_is_refused_not_written(tmp_path,
                                                       monkeypatch):
    """**The failure this whole file exists for.** A short walk understates
    every figure downstream and does so silently — the cached file looks
    exactly like a complete one, and the only evidence is a count nobody
    compared."""
    monkeypatch.setattr(dl, "CACHE", tmp_path)
    monkeypatch.setattr(dl, "ROOT", tmp_path)
    monkeypatch.setattr(dl, "get", Api([("completions", page(190770, rows(7)))]))
    with pytest.raises(dl.Truncated, match="190,770"):
        dl.fetch("completions", {"url": "https://x/completions", "what": "c"})


def test_an_empty_answer_is_not_a_measurement_of_zero(tmp_path,
                                                     monkeypatch):
    """A table answering with nothing has not told us there is nothing — it
    has not answered. Written to disk, it makes every count downstream a
    measured zero, which is the one wrong answer that looks right."""
    monkeypatch.setattr(dl, "CACHE", tmp_path)
    monkeypatch.setattr(dl, "ROOT", tmp_path)
    monkeypatch.setattr(dl, "get", Api([("completions", page(0, []))]))
    with pytest.raises(dl.Truncated, match="not a measurement of zero"):
        dl.fetch("completions", {"url": "https://x/completions", "what": "c"})


def test_an_answer_without_a_count_is_refused(monkeypatch):
    """With no count there is nothing to compare the walk against, so a short
    walk and a complete one are the same file."""
    monkeypatch.setattr(dl, "get",
                        Api([("completions", {"results": rows(3)})]))
    with pytest.raises(dl.Unreachable, match="without a count"):
        dl.walk("https://x/completions")


def test_a_next_link_offered_past_the_count_does_not_loop(monkeypatch):
    """The count is reached and a `next` is still offered. Following it would
    duplicate rows or spin; the count is what the completeness check compares
    against, so the count wins."""
    api = Api([("completions", page(2, rows(2), "https://x/?page=2"))])
    monkeypatch.setattr(dl, "get", api)
    collected, total = dl.walk("https://x/completions")
    assert len(collected) == 2 == total
    assert len(api.asked) == 1, api.asked


def test_a_complete_walk_is_written_with_what_it_can_be_checked_against(
        tmp_path, monkeypatch):
    """The cached file carries the reported count beside the collected count.
    Without both, a later reader cannot tell a complete slice from a truncated
    one without re-fetching it."""
    monkeypatch.setattr(dl, "CACHE", tmp_path)
    monkeypatch.setattr(dl, "ROOT", tmp_path)
    monkeypatch.setattr(dl, "get", Api([("completions", page(3, rows(3)))]))
    result = dl.fetch("completions", {"url": "https://x/completions",
                                      "what": "completions"})
    held = json.loads(
        (tmp_path / f"completions-{dl.FIPS}-{dl.YEAR}.json")
        .read_text(encoding="utf-8"))
    assert held["count_reported"] == held["rows_collected"] == 3
    assert held["fips"] == dl.FIPS and held["year"] == dl.YEAR
    assert result["from_cache"] is False


def test_the_cache_is_used_and_says_so(tmp_path, monkeypatch):
    """The completions walk is twenty requests for 190,770 rows and a loader
    under development runs many times. A cached read that did not say it was
    cached would let a stale slice be reported as a fresh measurement."""
    monkeypatch.setattr(dl, "CACHE", tmp_path)
    monkeypatch.setattr(dl, "ROOT", tmp_path)
    (tmp_path / f"completions-{dl.FIPS}-{dl.YEAR}.json").write_text(
        json.dumps({"rows": rows(3), "count_reported": 3}), encoding="utf-8")

    def refuse(url):
        raise AssertionError("the cache was not used; the API was called")

    monkeypatch.setattr(dl, "get", refuse)
    result = dl.fetch("completions", {"url": "https://x/c", "what": "c"})
    assert result["from_cache"] is True
    assert len(result["rows"]) == 3

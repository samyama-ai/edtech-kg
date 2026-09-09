"""The education download, driven without the network.

edtech-kg#7. Three things decide whether the cached slice is trustworthy, and
none of them is visible in the file that lands on disk: whether the walk
followed the source's own `next` link, whether it stopped short, and whether
an empty answer was written down as a measurement of zero.

**Nothing here opens a socket, and that is asserted rather than trusted** —
`test_this_file_opens_no_sockets` runs this file under a watcher in a child
process. An earlier draft of this docstring claimed a `tests/conftest.py`
refused sockets suite-wide. There is no such file on this branch; the claim
was written from a sibling branch where one is being built. An unbacked claim
about the test harness is worse than no claim, because it is the sentence a
reader uses to decide how much the rest of the file is worth.
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
        json.dumps({"rows": rows(3), "count_reported": 3,
                    "rows_collected": 3}), encoding="utf-8")

    def refuse(url):
        raise AssertionError("the cache was not used; the API was called")

    monkeypatch.setattr(dl, "get", refuse)
    result = dl.fetch("completions", {"url": "https://x/c", "what": "c"})
    assert result["from_cache"] is True
    assert len(result["rows"]) == 3


def test_a_short_cached_slice_is_refused_rather_than_served(tmp_path,
                                                           monkeypatch):
    """**The completeness check used to run only on the write.** So a
    truncated or hand-edited file on disk was returned as trustworthy, and
    this module is the "later reader" the stored counts exist for. A cache
    that skips the check it was built to make possible is worse than no
    cache — the loader would have built every count on it.

    The fixture in `test_the_cache_is_used_and_says_so` was itself incomplete
    and passed, which is how this was found.
    """
    monkeypatch.setattr(dl, "CACHE", tmp_path)
    monkeypatch.setattr(dl, "ROOT", tmp_path)
    (tmp_path / f"completions-{dl.FIPS}-{dl.YEAR}.json").write_text(
        json.dumps({"rows": rows(7), "count_reported": 190770,
                    "rows_collected": 7}), encoding="utf-8")
    with pytest.raises(dl.Truncated, match="190770"):
        dl.fetch("completions", {"url": "https://x/c", "what": "c"})


def test_an_empty_cached_slice_is_refused_like_an_empty_answer(tmp_path,
                                                               monkeypatch):
    """A cached file holding no rows is self-consistent — 0 collected, 0
    reported — so both count checks pass it. It is still not a measurement of
    zero, for the same reason the live answer is not, and it is the shape a
    truncated-to-nothing write leaves behind.

    Found by mutation: deleting this guard left the whole file green.
    """
    monkeypatch.setattr(dl, "CACHE", tmp_path)
    monkeypatch.setattr(dl, "ROOT", tmp_path)
    (tmp_path / f"completions-{dl.FIPS}-{dl.YEAR}.json").write_text(
        json.dumps({"rows": [], "count_reported": 0, "rows_collected": 0}),
        encoding="utf-8")
    with pytest.raises(dl.Truncated, match="no rows"):
        dl.fetch("completions", {"url": "https://x/c", "what": "c"})


def test_a_cached_slice_whose_rows_do_not_match_its_own_count_is_refused(
        tmp_path, monkeypatch):
    """The two stored counts agreeing with each other is not the same as
    either agreeing with the rows actually on disk — a half-written file can
    carry a complete header."""
    monkeypatch.setattr(dl, "CACHE", tmp_path)
    monkeypatch.setattr(dl, "ROOT", tmp_path)
    (tmp_path / f"completions-{dl.FIPS}-{dl.YEAR}.json").write_text(
        json.dumps({"rows": rows(2), "count_reported": 9,
                    "rows_collected": 9}), encoding="utf-8")
    with pytest.raises(dl.Truncated):
        dl.fetch("completions", {"url": "https://x/c", "what": "c"})


def test_an_interrupted_write_leaves_no_cache_file_at_all(tmp_path,
                                                          monkeypatch):
    """**A half-written cache file is this module's own failure by another
    door.** 190,770 rows is a large single write; a Ctrl-C part-way through
    used to leave a partial file at the cache path, which the next run takes
    as its cache and dies on — from a line that reads like a bug in the
    reader.

    Written aside and moved into place, so the path either holds a complete
    file or holds nothing.
    """
    monkeypatch.setattr(dl, "CACHE", tmp_path)
    monkeypatch.setattr(dl, "ROOT", tmp_path)
    monkeypatch.setattr(dl, "get", Api([("x/c", page(3, rows(3)))]))

    def die(src, dst):
        raise KeyboardInterrupt

    monkeypatch.setattr(dl.os, "replace", die)
    with pytest.raises(KeyboardInterrupt):
        dl.fetch("completions", {"url": "https://x/c", "what": "c"})
    assert not (tmp_path / f"completions-{dl.FIPS}-{dl.YEAR}.json").exists(), (
        "an interrupted write left a file at the cache path")


def test_check_refuses_a_source_with_no_count_instead_of_a_traceback(
        monkeypatch):
    """`walk` refuses here with a message saying why; `--check` formatted
    `None` with `:,` and died on a TypeError — the same conclusion reached as
    a stack trace, which reads as a bug in this code rather than as an answer
    about the source."""
    monkeypatch.setattr(dl, "get", lambda url: {"results": []})
    with pytest.raises(dl.Unreachable, match="without a count"):
        dl.check()


def test_only_with_no_tables_named_does_not_download_everything():
    """`nargs="*"` made a bare `--only` yield `[]`, the `if args.only` test
    false, and every table fetched — the opposite of what the flag reads as.
    Argparse refuses it now, before a request is made."""
    with pytest.raises(SystemExit):
        dl.main(["--only"])


def test_this_file_opens_no_sockets():
    """The docstring above says nothing here fetches. Asserted, not trusted.

    A missing monkeypatch is invisible until somebody watches the socket:
    `test_sced_doc.py` made live requests on every full-suite run and nothing
    noticed. Both `connect` and `connect_ex` are watched — a guard covering
    one of them is green against the other.
    """
    from tests.no_sockets import connects_made_by
    connects, output = connects_made_by(__file__)
    assert connects == 0, (
        f"{connects} socket(s) opened — a test in this file reached the "
        f"network:\n{output}")

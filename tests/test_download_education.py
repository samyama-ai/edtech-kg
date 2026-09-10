"""The education download, driven without the network.

edtech-kg#7. Three things decide whether the cached slice is trustworthy, and
none of them is visible in the file that lands on disk: whether the walk
followed the source's own `next` link, whether it stopped short, and whether
an empty answer was written down as a measurement of zero.

**Nothing here opens a socket**, and that is enforced by `tests/conftest.py`,
which refuses `connect` and `connect_ex` suite-wide. This file carried its own
per-file watcher until #179 landed that conftest; the two then disagreed, and
the watcher lost. It ran the file in a child that replaced `socket.socket`
with a counting subclass, so the conftest patched the counter off the class it
had just been handed and the guard passed while counting nothing.
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
    collected, total, unique = dl.walk("https://x/completions")
    assert total == 3
    assert unique == 3
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
    # **The half the name promises.** Asserting only `raises` leaves the file
    # green if the write moves above the validation — a truncated slice at the
    # cache path with a refusal printed over it. This also pins the scratch
    # `.part` being cleaned up rather than left behind.
    assert not list(tmp_path.iterdir()), (
        f"refused, and still wrote {[f.name for f in tmp_path.iterdir()]}")


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
    assert not list(tmp_path.iterdir()), (
        f"refused, and still wrote {[f.name for f in tmp_path.iterdir()]}")


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
    collected, total, unique = dl.walk("https://x/completions")
    assert len(collected) == 2 == total == unique
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


def test_a_corrupt_cache_file_is_refused_not_a_traceback(tmp_path,
                                                         monkeypatch):
    """An interrupted write leaves unparseable JSON, and `json.loads` raised
    `JSONDecodeError` straight through `main`'s `except Truncated` — the
    module documents a clean refusal for every other unusable slice and
    delivered a traceback for this one."""
    monkeypatch.setattr(dl, "CACHE", tmp_path)
    monkeypatch.setattr(dl, "ROOT", tmp_path)
    (tmp_path / f"completions-{dl.FIPS}-{dl.YEAR}.json").write_text(
        "{not json", encoding="utf-8")
    with pytest.raises(dl.Truncated, match="not readable JSON"):
        dl.fetch("completions", {"url": "https://x/c", "what": "c"})


def test_a_cached_slice_with_no_counts_is_refused_not_a_key_error(tmp_path,
                                                                  monkeypatch):
    """Both counts absent compare equal as `None`, so the agreement check
    passed them and `held["rows_collected"]` raised `KeyError` two lines
    later. A slice carrying no counts cannot be checked at all, which is a
    refusal, not a crash."""
    monkeypatch.setattr(dl, "CACHE", tmp_path)
    monkeypatch.setattr(dl, "ROOT", tmp_path)
    (tmp_path / f"completions-{dl.FIPS}-{dl.YEAR}.json").write_text(
        json.dumps({"rows": rows(2)}), encoding="utf-8")
    with pytest.raises(dl.Truncated, match="rows_collected or count_reported"):
        dl.fetch("completions", {"url": "https://x/c", "what": "c"})


def test_check_prints_a_table_reporting_zero_rows(tmp_path, monkeypatch,
                                                  capsys):
    """`check` sets `pages` to None when a table reports no rows, and `:>3`
    cannot format None — `--check` died with a `TypeError` on the one answer
    it most needed to show. Zero rows is a report, not a crash."""
    monkeypatch.setattr(dl, "CACHE", tmp_path)
    monkeypatch.setattr(dl, "ROOT", tmp_path)
    monkeypatch.setattr(dl, "get", lambda url: {"count": 0, "results": []})
    assert dl.main(["--check"]) == 0
    printed = capsys.readouterr().out
    assert "0 rows" in printed
    assert "- pages" in printed


def test_reaching_the_count_by_repetition_is_refused(tmp_path, monkeypatch):
    """**Cardinality is not identity.** The completeness check was
    `len(rows) != total`, so a `next` chain that re-serves a page reaches the
    count with duplicates and passes. Driven directly against the old code:

        collected: [{'unitid': 1}, {'unitid': 2}, {'unitid': 1}, {'unitid': 2}]
        len(rows) = 4   total = 4   unique = 2   -> check PASSED

    The slice was then written with `count_reported == rows_collected == 4`
    holding two real rows, and the read path could never catch it because all
    three stored numbers agreed. That is this module's headline failure —
    every figure downstream understating silently — arriving by repetition
    instead of truncation.
    """
    monkeypatch.setattr(dl, "CACHE", tmp_path)
    monkeypatch.setattr(dl, "ROOT", tmp_path)
    monkeypatch.setattr(dl, "get", Api([
        ("page=2", page(4, rows(2))),
        ("completions", page(4, rows(2), "https://x/completions?page=2")),
    ]))
    with pytest.raises(dl.Truncated, match="repetition"):
        dl.fetch("completions", {"url": "https://x/completions", "what": "c"})
    assert not list(tmp_path.iterdir())


def test_a_cached_slice_that_repeats_rows_is_refused(tmp_path, monkeypatch):
    """A duplicated slice already on disk is self-consistent — every stored
    number agrees — so identity has to be counted from the rows themselves,
    not read back out of the file that got it wrong."""
    monkeypatch.setattr(dl, "CACHE", tmp_path)
    monkeypatch.setattr(dl, "ROOT", tmp_path)
    doubled = rows(2) + rows(2)
    (tmp_path / f"completions-{dl.FIPS}-{dl.YEAR}.json").write_text(
        json.dumps({"rows": doubled, "count_reported": 4,
                    "rows_collected": 4, "rows_unique": 4}), encoding="utf-8")
    with pytest.raises(dl.Truncated, match="repetition"):
        dl.fetch("completions", {"url": "https://x/completions", "what": "c"})


def test_a_next_that_never_advances_is_refused_rather_than_paged_for_ever(
        monkeypatch):
    """`batch = []` is not `None`, so an empty page grew nothing while
    `len(rows) >= total` stayed false and the loop re-requested at 2 req/s
    with no output, no exit code and no refusal. Measured at **3,001 requests
    and still going** before this guard.

    Remembering page URLs rather than counting pages also catches an A->B->A
    cycle, which a page ceiling would only catch late.
    """
    api = Api([("completions", page(10, [], "https://x/completions"))])

    def bounded(url):
        # **The stub refuses rather than letting the walk spin.** Without the
        # guard this loop never returns, so the test would HANG rather than
        # fail — and a hanging CI job is a worse regression signal than a red
        # one. Five is far above the one request a correct walk makes here.
        if len(api.asked) >= 5:
            raise AssertionError(
                f"the walk made {len(api.asked)} requests without advancing "
                f"and was still going")
        return api(url)

    monkeypatch.setattr(dl, "get", bounded)
    with pytest.raises(dl.Unreachable, match="twice"):
        dl.walk("https://x/completions")
    assert len(api.asked) <= 2, (
        f"the walk made {len(api.asked)} requests before refusing")


@pytest.mark.parametrize("offered", [
    "file:///etc/passwd",
    "http://x/completions?page=2",          # scheme downgraded
    "https://elsewhere.test/completions",   # foreign host
])
def test_a_next_link_off_the_api_is_not_followed(monkeypatch, offered):
    """`urlopen` serves `file://` through `FileHandler` — verified against
    this interpreter, which read a local file handed to it as a `next` link.
    The exposure against a public government API is thin, but this repo has
    already made the decision twice, at `etl/probe_sced.py:129-139` and
    `etl/probe_pwcs.py:189-202`, with the argument written down.
    """
    api = Api([("completions", page(4, rows(2), offered))])
    monkeypatch.setattr(dl, "get", api)
    with pytest.raises(dl.Unreachable, match="same host"):
        dl.walk("https://x/completions")


def test_the_two_exit_codes_are_not_interchangeable(tmp_path, monkeypatch):
    """The docstring calls telling them apart "the point of having them", and
    nothing asserted either: swapping `EXIT_UNREACHABLE` and `EXIT_TRUNCATED`
    left the suite green. A CI step branching on the code is the contract."""
    monkeypatch.setattr(dl, "CACHE", tmp_path)
    monkeypatch.setattr(dl, "ROOT", tmp_path)

    def unreachable(url):
        raise dl.Unreachable("the source did not answer")
    monkeypatch.setattr(dl, "get", unreachable)
    assert dl.main(["--only", "institutions"]) == dl.EXIT_UNREACHABLE == 1

    # matched on the real path segment: the institutions table is
    # `/ipeds/directory/`, and the table NAME appears nowhere in its URL.
    monkeypatch.setattr(dl, "get", Api([("directory", page(9, rows(2)))]))
    assert dl.main(["--only", "institutions"]) == dl.EXIT_TRUNCATED == 3

"""Finding a catalogue's pages, and asking for them politely.

Split from `tests/test_probe_second_district.py` when the module under test
was split — that file samples pages and classifies them; this decides which
pages exist and how they are fetched.

**Every bound here exists because it was once absent.** Reading only the first
index page found 73 of PWCS's 817 courses and the sample was drawn from that
biased subset; a 429 was caught as a transport failure so a rate-limiting
district got 59 more requests; the delay sat after each SUCCESSFUL call, so
it was skipped on exactly the paths where a host is struggling.

No network — `tests/conftest.py` refuses a socket to every test here.
"""

from __future__ import annotations

import pytest


def test_the_crawl_follows_the_pager(monkeypatch):
    """**The bug that skewed the whole measurement, and nothing guarded it.**

    Drupal paginates its index with `?page=n`. Reading only the first page
    found 73 of PWCS's 817 courses — and the sample was then drawn from
    whatever that page happened to link to, which is a BIASED subset rather
    than a small one. Arlington measured 101 pages and publishes 698.
    """
    import etl.catalogue_pages as module
    monkeypatch.setattr(module, "DELAY", 0)
    pages = {
        "https://x.test/courses": '<a href="/s/a">a</a><a href="/s/b">b</a>',
        "https://x.test/courses?page=1": '<a href="/s/c">c</a>',
        "https://x.test/courses?page=2": '<a href="/s/d">d</a>',
        # page 3 repeats page 2 — the end of a Drupal pager
        "https://x.test/courses?page=3": '<a href="/s/d">d</a>',
    }
    asked = []

    def fake(url):
        asked.append(url)
        if url in pages:
            return pages[url]
        raise module.Unreachable(url)

    monkeypatch.setattr(module, "get", fake)
    found = module.crawl("https://x.test")
    assert found == {"/s/a", "/s/b", "/s/c", "/s/d"}, (
        "the pager was not followed; only the first page's courses were found")
    assert "https://x.test/courses?page=3" in asked, "page 3 was never asked for"
    assert "https://x.test/courses?page=4" not in asked, (
        "a page yielding no NEW course must stop the loop — otherwise a "
        "server that ignores ?page runs to the cap")


def test_the_crawl_stops_rather_than_running_to_the_cap(monkeypatch):
    """A server ignoring `?page` returns the same index forever."""
    import etl.catalogue_pages as module
    monkeypatch.setattr(module, "DELAY", 0)
    asked = []

    def same(url):
        asked.append(url)
        return '<a href="/s/a">a</a>'

    monkeypatch.setattr(module, "get", same)
    assert module.crawl("https://x.test") == {"/s/a"}
    per_index = [u for u in asked if u.startswith("https://x.test/courses")]
    assert len(per_index) <= 2, (
        f"asked for {len(per_index)} pages of one index; a repeat must stop "
        f"the loop, not the {module.MAX_PAGES}-page cap")


def test_an_index_is_not_abandoned_because_another_already_found_its_courses(
        monkeypatch):
    """The crawl subtracted the GLOBAL set, so an index whose first page
    linked only paths another index had already yielded was abandoned —
    every later page of it included."""
    import etl.catalogue_pages as module
    monkeypatch.setattr(module, "DELAY", 0)
    pages = {
        "https://x.test/courses": '<a href="/s/a">a</a>',
        "https://x.test/high-school-courses": '<a href="/s/a">a</a>',
        "https://x.test/high-school-courses?page=1":
            '<a href="/s/b">b</a><a href="/s/c">c</a>',
    }
    monkeypatch.setattr(module, "get",
                        lambda url: pages.get(url) if url in pages
                        else (_ for _ in ()).throw(module.Unreachable(url)))
    found = module.crawl("https://x.test")
    assert found == {"/s/a", "/s/b", "/s/c"}, (
        f"the second index was abandoned on its first page; got {found}")


def test_a_soft_404_is_not_a_sitemap(monkeypatch):
    """`has_sitemap` was set from a 200 alone, so a themed "not found" page
    answering 200 was indistinguishable from a real sitemap listing no
    courses — a distinction the page states as fact."""
    import etl.catalogue_pages as module
    monkeypatch.setattr(module, "DELAY", 0)
    monkeypatch.setattr(module, "crawl", lambda base: {"/s/a"})
    monkeypatch.setattr(module, "get",
                        lambda url: "<html><body>Page not found</body></html>")
    _, how = module.course_paths("https://x.test")
    assert how["has_sitemap"] is False, (
        "a 200 that is not a sitemap was recorded as one")


def test_a_429_stops_the_run_rather_than_shrinking_the_denominator(monkeypatch):
    """`URLError` is `HTTPError`'s parent, so catching it first swallowed a
    429: a district that began rate-limiting mid-sample got 59 more requests,
    and each throttled page landed in `unreachable` — quietly shrinking the
    denominator instead of stopping."""
    import urllib.error
    import etl.catalogue_pages as module
    monkeypatch.setattr(module, "DELAY", 0)

    def throttled(request, timeout=None):
        raise urllib.error.HTTPError(
            "u", 429, "Too Many Requests", {"Retry-After": "120"}, None)

    monkeypatch.setattr(module.urllib.request, "urlopen", throttled)
    with pytest.raises(module.Refused, match="429"):
        module.get("https://x.test/a")


def test_the_politeness_delay_cannot_be_skipped(monkeypatch):
    """It used to sit after each successful call, so it was skipped on exactly
    the paths where a host is struggling — a sitemap 404 fell straight into
    the crawl, and five failing index candidates fired five back-to-back
    requests."""
    import urllib.error
    import etl.catalogue_pages as module
    slept = []
    monkeypatch.setattr(module.time, "sleep", lambda s: slept.append(s))
    monkeypatch.setattr(
        module.urllib.request, "urlopen",
        lambda *a, **k: (_ for _ in ()).throw(urllib.error.URLError("down")))
    with pytest.raises(module.Unreachable):
        module.get("https://x.test/a")
    assert slept, "no delay before a request that failed"


def test_the_sitemap_branch_reports_the_parsed_check_not_an_assertion(monkeypatch):
    """`has_sitemap: True` was hard-coded in the branch that succeeds, while
    the variable beside it was computed from whether the body parses. The two
    could disagree, and the record would carry the assertion."""
    import etl.catalogue_pages as module
    monkeypatch.setattr(module, "DELAY", 0)
    monkeypatch.setattr(module, "crawl", lambda base: set())
    # A 200 that is NOT a sitemap but happens to contain a course-shaped loc.
    monkeypatch.setattr(
        module, "get",
        lambda url: "<html><loc>https://x.test/s/a</loc></html>")
    paths, how = module.course_paths("https://x.test")
    assert how["has_sitemap"] is False, (
        "a document with no <urlset> was recorded as a sitemap")


def test_the_index_crawl_runs_only_where_the_calibration_needs_it(monkeypatch):
    """It ran alongside a working sitemap for every district — up to ~200
    extra requests each, for a number only the calibration paragraph uses.
    On a politeness-bounded probe reading school-district servers that is
    the expensive kind of thoroughness."""
    import etl.catalogue_pages as module
    monkeypatch.setattr(module, "DELAY", 0)
    crawled = []
    monkeypatch.setattr(module, "crawl",
                        lambda base: (crawled.append(base), {"/s/a"})[1])
    monkeypatch.setattr(
        module, "get",
        lambda url: "<urlset><loc>https://x.test/s/a</loc></urlset>")

    _, how = module.course_paths("https://x.test", calibrate=False)
    assert not crawled, "the crawl ran with a working sitemap and no calibration"
    assert how["courses_in_index_crawl"] is None, (
        "not measured must be None, not 0 — 'not measured here' and 'the "
        "crawl found nothing' are different facts")

    _, how = module.course_paths("https://x.test", calibrate=True)
    assert crawled == ["https://x.test"]
    assert how["courses_in_index_crawl"] == 1


def test_a_district_without_a_sitemap_still_crawls(monkeypatch):
    """The crawl is how four of the five are enumerated at all — skipping it
    there would leave them with no population."""
    import etl.catalogue_pages as module
    monkeypatch.setattr(module, "DELAY", 0)
    monkeypatch.setattr(module, "crawl", lambda base: {"/s/a", "/s/b"})
    monkeypatch.setattr(module, "get", lambda url: "<html>not a sitemap</html>")
    paths, how = module.course_paths("https://x.test", calibrate=False)
    assert sorted(paths) == ["/s/a", "/s/b"]
    assert how["how"] == "index crawl"

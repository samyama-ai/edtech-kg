"""The second-district probe's classifier, driven without the network.

The measurement turns on one distinction — a prerequisite in the TYPED field
versus the same prerequisite in prose — so that is what is tested. Everything
else in the probe is walking and counting.
"""

from __future__ import annotations

from etl import probe_second_district as probe


def page(*, typed=None, prose=None) -> str:
    """A course page carrying either field, both, or neither.

    `None` means the field is ABSENT; `""` means present and empty. Those are
    different answers and the probe treats them differently, so the helper has
    to express both — the first version used `""` for absent and could not
    build the empty-field case at all.
    """
    markup = "<div>"
    if typed is not None:
        markup += (f'<div class="field--name-field-prerequisite-courses">'
                   f'{typed}</div>')
    if prose is not None:
        markup += (f'<div class="field--name-field-pr">'
                   f'<div class="field__item">{prose}</div></div>')
    return markup + '<div class="field--name-field-credits">1</div></div>'


PUBLISHED = {"/maths/algebra-1", "/maths/algebra-2"}


def test_the_typed_field_is_found_and_the_prose_field_is_not_mistaken_for_it():
    """**The bug this probe had first.** `field--name-field-pr\\b` excludes
    `field-prerequisite-courses` — the word boundary stops at `pr` — so the
    first version read the prose field on every district and reported PWCS at
    0% linked. The repo's own figure for PWCS is 89%; a method that cannot
    reproduce the control measures nothing.
    """
    # ASSERTED, not argued. A review read the boundary the other way, and
    # the claim is load-bearing: it is why the prose pattern can be searched
    # over a whole page without stealing the typed field's match. After `pr`
    # comes `e`, so there is no word boundary and no match.
    assert not probe.PROSE_FIELD.search(
        'field--name-field-prerequisite-courses'
        '<div class="field__item">x</div>'), (
        "the prose pattern matches the typed field's class name")

    typed = probe.classify(
        page(typed='<a href="/maths/algebra-1">Algebra I</a>'), PUBLISHED)
    assert typed["kind"] == "typed"
    assert typed["links"] == ["/maths/algebra-1"]
    assert typed["resolved"] == ["/maths/algebra-1"]

    prose = probe.classify(page(prose="Audition by the band director"), PUBLISHED)
    assert prose["kind"] == "prose", (
        "a free-text prerequisite must not be counted as an edge")


def test_a_page_with_both_fields_counts_as_typed():
    """Counting it as prose would understate a district that answers the
    question in the form that resolves."""
    both = probe.classify(
        page(typed='<a href="/maths/algebra-2">Algebra II</a>',
             prose="See your counsellor"), PUBLISHED)
    assert both["kind"] == "typed"


def test_a_link_to_a_page_the_catalogue_does_not_publish_is_not_resolved():
    """The resolution rate is the good half of the finding — "the problem is
    not broken links" — so a link that lands nowhere must not count."""
    found = probe.classify(
        page(typed='<a href="/maths/algebra-1">A</a>'
                   '<a href="/gone/nowhere">B</a>'), PUBLISHED)
    assert found["links"] == ["/maths/algebra-1", "/gone/nowhere"]
    assert found["resolved"] == ["/maths/algebra-1"]


def test_a_typed_field_holding_no_course_link_is_its_own_answer():
    """The CMS emits `/saml_login` inside the field on every page. A typed
    field whose only links are navigation states nothing traversable, so it
    must not count as typed — that would inflate every district including
    PWCS.

    But it is not "prose" and it is not "no field" either. Folding it into
    those reported a district that emits the field and fills it with
    navigation as one that does not use the field at all, which is a
    different fact. It gets its own kind.
    """
    found = probe.classify(
        page(typed='<a href="/saml_login">Log in</a>',
             prose="Teacher recommendation"), PUBLISHED)
    assert found["kind"] == "typed but no course link"
    assert "Log in" in found["text"]


def test_an_absolute_link_to_the_same_host_resolves():
    """Matching only `/…` meant a district linking its prerequisites as
    `https://catalog.example.edu/x/y` was counted as having none — the
    finding this probe exists to measure, produced by not looking."""
    base = "https://catalog.example.edu"
    found = probe.classify(
        page(typed=f'<a href="{base}/maths/algebra-1">Algebra I</a>'),
        PUBLISHED, base)
    assert found["kind"] == "typed"
    assert found["resolved"] == ["/maths/algebra-1"]


def test_a_link_to_another_host_is_not_a_course_and_not_a_failure():
    """An off-host link is not a prerequisite this catalogue publishes, and
    counting it as an unresolved link would understate resolution."""
    found = probe.classify(
        page(typed='<a href="https://elsewhere.example/x/y">Elsewhere</a>'
                   '<a href="/maths/algebra-1">Algebra I</a>'),
        PUBLISHED, "https://catalog.example.edu")
    assert found["links"] == ["/maths/algebra-1"]
    assert found["resolved"] == ["/maths/algebra-1"]


def test_none_and_absent_are_different_answers():
    """A page with no field has not been asked; a page saying "None" has
    answered. Folding them together would move courses out of the
    denominator."""
    assert probe.classify(page(), PUBLISHED)["kind"] == "no field"
    assert probe.classify(page(prose="None"), PUBLISHED)["kind"] == "says none"
    assert probe.classify(page(prose=""), PUBLISHED)["kind"] == "says none"


def test_only_two_segment_paths_count_as_courses():
    """The vendor's shape, and the rule `etl/pwcs_source.py` already uses.
    A different rule here would measure the rule rather than the district."""
    assert probe.COURSE_PATH.match("/maths/algebra-1")
    assert not probe.COURSE_PATH.match("/maths")
    assert not probe.COURSE_PATH.match("/maths/algebra-1/unit-2")


def test_two_runs_of_the_probe_read_the_same_pages(monkeypatch):
    """The issue asks for a recorded seed. Asserted by running `district()`
    twice and comparing what it FETCHED — the first version compared two calls
    to `random.Random`, which tests the standard library."""
    import etl.probe_second_district as module
    paths = [f"/s/c{i}" for i in range(200)]
    monkeypatch.setattr(module, "course_paths",
                        lambda base: (paths, {"how": "index crawl",
                                              "has_sitemap": False,
                                              "courses_in_sitemap": 0,
                                              "courses_in_index_crawl": 200}))
    monkeypatch.setattr(module, "DELAY", 0)

    def run():
        asked = []
        monkeypatch.setattr(module, "get",
                            lambda url: (asked.append(url), page())[1])
        module.district("D", "https://example.test", sample=15)
        return asked

    assert run() == run(), "two runs read different pages"
    assert probe.SEED == 19, "the seed is the issue number, recorded on the page"


def test_a_typed_field_at_the_very_end_of_a_page_is_still_found():
    """The lookahead required another `field--name-field-*` or a `</footer>`
    to follow, so a page whose prerequisite field is the LAST thing in the
    document matched nothing and was counted as stating none."""
    last = ('<div class="field--name-field-prerequisite-courses">'
            '<a href="/maths/algebra-1">Algebra I</a></div>')
    found = probe.classify(last, PUBLISHED)
    assert found["kind"] == "typed", (
        "a typed field with nothing after it was read as absent")
    assert found["resolved"] == ["/maths/algebra-1"]


def test_json_and_record_are_refused_together(capsys):
    """Opposite intentions — print without touching the tree, and write to
    the tree. One silently winning is the worse outcome."""
    import etl.probe_second_district as module
    called = []
    module_measure = module.measure
    module.measure = lambda *a, **k: (called.append(1), {"districts": {}})[1]
    try:
        assert module.main(["--json", "--record"]) == 2
        assert "pick one" in capsys.readouterr().err
        # **The point.** Refusing after `measure()` meant the full
        # five-district crawl ran first and was then thrown away over a flag
        # combination knowable at parse time.
        assert not called, "the crawl ran before the flags were checked"
    finally:
        module.measure = module_measure


def test_an_unreachable_page_leaves_the_denominator_honest(monkeypatch):
    """A page that did not answer is not a page that stated nothing. Counting
    it in `read` would report a network failure as a district's choice.

    Driven through `district()`, not asserted as arithmetic. The first version
    computed `10 - 1 == 9` in the test body and never called the module — it
    tested Python.
    """
    import etl.probe_second_district as module
    paths = [f"/s/c{i}" for i in range(10)]
    monkeypatch.setattr(module, "course_paths",
                        lambda base: (paths, {"how": "index crawl",
                                              "has_sitemap": False,
                                              "courses_in_sitemap": 0,
                                              "courses_in_index_crawl": 10}))
    monkeypatch.setattr(module, "DELAY", 0)

    def one_refusal(url):
        if url.endswith("/s/c0"):
            raise module.Unreachable("the host said no")
        if url.endswith("/s/c1"):
            return page(typed='<a href="/s/c2">C2</a>')
        return page()

    monkeypatch.setattr(module, "get", one_refusal)
    found = module.district("D", "https://example.test", sample=10)
    assert found["sampled"] == 10
    assert found["unreachable"] == 1
    assert found["read"] == 9, "the refused page is in the denominator"
    assert found["with_a_typed_prerequisite"] == 1
    assert found["percent_of_pages_with_a_typed_prerequisite"] == 11.1


def test_the_crawl_follows_the_pager(monkeypatch):
    """**The bug that skewed the whole measurement, and nothing guarded it.**

    Drupal paginates its index with `?page=n`. Reading only the first page
    found 73 of PWCS's 817 courses — and the sample was then drawn from
    whatever that page happened to link to, which is a BIASED subset rather
    than a small one. Arlington measured 101 pages and publishes 698.
    """
    import etl.probe_second_district as module
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
    import etl.probe_second_district as module
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

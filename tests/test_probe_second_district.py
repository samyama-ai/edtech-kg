"""The second-district probe's classifier, driven without the network.

The measurement turns on one distinction — a prerequisite in the TYPED field
versus the same prerequisite in prose — so that is what is tested. Everything
else in the probe is walking and counting.
"""

from __future__ import annotations

import json

# The single-page fixture builder lives with the single-page tests.
from tests.test_course_page import page
from etl import catalogue_pages
from etl import probe_second_district as probe






















def test_two_runs_of_the_probe_read_the_same_pages(monkeypatch):
    """The issue asks for a recorded seed. Asserted by running `district()`
    twice and comparing what it FETCHED — the first version compared two calls
    to `random.Random`, which tests the standard library."""
    import etl.probe_second_district as module
    paths = [f"/s/c{i}" for i in range(200)]
    monkeypatch.setattr(module, "course_paths",
                        lambda base, calibrate=False: (paths, {"how": "index crawl",
                                              "has_sitemap": False,
                                              "courses_in_sitemap": 0,
                                              "courses_in_index_crawl": 200}))
    # DELAY lives with get() in catalogue_pages, which is where it is read.
    monkeypatch.setattr(catalogue_pages, "DELAY", 0)

    def run():
        asked = []
        monkeypatch.setattr(module, "get",
                            lambda url: (asked.append(url), page())[1])
        module.district("D", "https://example.test", sample=15)
        return asked

    assert run() == run(), "two runs read different pages"
    assert probe.SEED == 19, "the seed is the issue number, recorded on the page"




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
                        lambda base, calibrate=False: (paths, {"how": "index crawl",
                                              "has_sitemap": False,
                                              "courses_in_sitemap": 0,
                                              "courses_in_index_crawl": 10}))
    # DELAY lives with get() in catalogue_pages, which is where it is read.
    monkeypatch.setattr(catalogue_pages, "DELAY", 0)

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












def test_a_pathway_page_leaves_the_denominator(monkeypatch):
    """`docs/schema.md` quotes every PWCS rate against 791 courses, not 960
    pages, and classifies by MARKUP rather than depth. Counting two-segment
    paths alone put pathway pages — which carry no prerequisite field — into
    the denominator and deflated the percentage the conclusion rests on."""
    import etl.probe_second_district as module
    from etl.pwcs_pages import PATHWAY_FIELD_PRESENT
    # DELAY lives with get() in catalogue_pages, which is where it is read.
    monkeypatch.setattr(catalogue_pages, "DELAY", 0)
    paths = [f"/s/c{i}" for i in range(4)]
    monkeypatch.setattr(module, "course_paths",
                        lambda base, calibrate=False: (paths, {"how": "index crawl",
                                              "has_sitemap": False,
                                              "courses_in_sitemap": 0,
                                              "courses_in_index_crawl": 4}))
    pathway = ('<div class="field--name-field-'
               + PATHWAY_FIELD_PRESENT.pattern.split("field-")[-1].strip("\\b")
               + '">x</div>')
    monkeypatch.setattr(
        module, "get",
        lambda url: pathway if url.endswith("/s/c0") else page())
    found = module.district("D", "https://x.test", sample=4)
    assert found["sampled_but_not_a_course"] >= 1, (
        "a pathway page stayed in the denominator")
    assert found["read"] == 4 - found["sampled_but_not_a_course"]














def test_the_record_guard_is_not_all_or_nothing(monkeypatch, capsys, tmp_path):
    """`--record` refused only an entirely empty measurement. A run where four
    of five districts time out — the likely real failure — overwrote the
    record with a near-empty one and exited 0.

    Refuses when a district that previously HAD candidate paths now has none.
    """
    import etl.probe_second_district as module
    committed = {"districts": {
        "A": {"candidate_course_paths": 700},
        "B": {"candidate_course_paths": 200}}}
    record = tmp_path / "r.json"
    record.write_text(json.dumps(committed), encoding="utf-8")
    monkeypatch.setattr(module, "RECORD", record)
    monkeypatch.setattr(module, "measure", lambda *a, **k: {
        "seed": 19, "sample_per_district": 60, "districts": {
            "A": {"candidate_course_paths": 700, "read": 60,
                  "with_a_typed_prerequisite": 3,
                  "percent_of_pages_with_a_typed_prerequisite": 5.0,
                  "links_resolving_to_a_published_course": 4, "links": 4},
            "B": {"candidate_course_paths": 0}}})
    before = record.read_bytes()
    assert module.main(["--record"]) == 3
    said = capsys.readouterr().err
    assert "B" in said, "the refusal must name the district that went empty"
    assert record.read_bytes() == before, "the record was overwritten"


def test_the_first_run_can_still_write(monkeypatch, tmp_path):
    """A ratchet that refused with no committed record could never write one."""
    import etl.probe_second_district as module
    record = tmp_path / "absent.json"
    monkeypatch.setattr(module, "RECORD", record)
    monkeypatch.setattr(module, "measure", lambda *a, **k: {
        "seed": 19, "sample_per_district": 60,
        "districts": {"A": {
            "candidate_course_paths": 700, "read": 60,
            "with_a_typed_prerequisite": 3,
            "percent_of_pages_with_a_typed_prerequisite": 5.0,
            "links_resolving_to_a_published_course": 4, "links": 4}}})
    assert module.main(["--record"]) == 0
    assert record.exists()


def test_the_pathway_fixture_is_not_built_from_the_code_under_test(monkeypatch):
    """The first version constructed the pathway markup from
    `PATHWAY_FIELD_PRESENT.pattern`, so a wrong field name moved the fixture
    with it and still passed. The class string is written out."""
    import etl.probe_second_district as module
    from etl.pwcs_pages import PATHWAY_FIELD_PRESENT
    PATHWAY = ('<div class="field field--name-field-degree-section-courses">'
               '<article class="degree-row">x</article></div>')
    assert PATHWAY_FIELD_PRESENT.search(PATHWAY), (
        "the hard-coded pathway fixture no longer matches the repo's own "
        "pattern — one of the two has moved and this test is why you know")

    # DELAY lives with get() in catalogue_pages, which is where it is read.
    monkeypatch.setattr(catalogue_pages, "DELAY", 0)
    paths = [f"/s/c{i}" for i in range(4)]
    monkeypatch.setattr(module, "course_paths",
                        lambda base, calibrate=False: (paths, {"how": "index crawl",
                                              "has_sitemap": False,
                                              "courses_in_sitemap": 0,
                                              "courses_in_index_crawl": 4}))
    monkeypatch.setattr(module, "get",
                        lambda url: PATHWAY if url.endswith("/s/c0") else page())
    found = module.district("D", "https://x.test", sample=4)
    assert found["sampled_but_not_a_course"] == 1
    assert found["read"] == 3




def test_a_district_with_no_paths_carries_every_key():
    """The empty branch promises "the same keys as every other district" and
    had lost `unreachable_by_status` — the same KeyError its own comment
    guards against, a second time."""
    import etl.probe_second_district as module
    import inspect
    source = inspect.getsource(module.district)
    empty = source[source.index("if not paths:"):source.index("published = set")]
    for key in ("sampled_but_not_a_course", "unreachable_by_status",
                "state_a_prerequisite_in_either_field", "prose_examples"):
        assert f'"{key}"' in empty, (
            f"the empty-district branch omits {key}; a short entry is a "
            f"KeyError waiting for the first consumer that iterates")





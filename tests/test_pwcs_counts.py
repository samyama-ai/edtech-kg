"""What the probe counts, and what it counts it against — edtech-kg#74.

Split out of `tests/test_probe_pwcs.py` when that file passed the 500-line
review limit. Split by SUBJECT: this file is the denominator — which pages are
courses, which set prerequisites resolve against, and the digit that says which
denominator produced a rate. `test_probe_pwcs.py` keeps fetching, caching,
parsing and the CLI.

The defect these exist for is not a crash. The probe reported 960 courses for a
catalogue with 791, every rate in two documents was quoted against it, and
nothing failed — the wrong number was simply published.
"""

from __future__ import annotations

from etl import probe_pwcs as probe
from tests.test_probe_pwcs import COURSE, NO_PREREQ, serve


SUBJECT_INDEX = """<html><body><h1 class="page-title">Agriculture</h1>
<div class="views-row"><a href="/agriculture/landscaping-1">Landscaping 1</a></div>
</body></html>"""

PATHWAY_PAGE = """<html><body><h1 class="page-title">Finance Pathway</h1>
<div class="field--name-field-degree-section-courses">
<article about="/agriculture/landscaping-1" class="degree-row"></article>
</div></body></html>"""


def test_only_pages_the_classifier_calls_courses_reach_the_denominator(monkeypatch):
    """The defect #74 names, asserted on the number the documents quote.

    A subject index parses perfectly well as a course — it has a title and no
    prerequisite field — so `parse_course` returning a record was never
    evidence of anything. Three pages are served here and only one is a
    course; before the fix all three counted.
    """
    serve(monkeypatch, {
        probe.SITEMAP: (
            '<urlset><loc>https://catalog.pwcs.edu/agriculture</loc>'
            '<loc>https://catalog.pwcs.edu/agriculture/landscaping-1</loc>'
            '<loc>https://catalog.pwcs.edu/cte/career-pathways/finance</loc>'
            '</urlset>'),
        "https://catalog.pwcs.edu/agriculture": SUBJECT_INDEX,
        "https://catalog.pwcs.edu/agriculture/landscaping-1": NO_PREREQ,
        "https://catalog.pwcs.edu/cte/career-pathways/finance": PATHWAY_PAGE})
    result = probe.probe(quiet=True)
    assert result["population"] == 3
    assert (result["subjects"], result["courses"], result["pathways"]) == (1, 1, 1)
    assert result["unclassified"] == 0


def test_a_course_page_publishing_a_pathway_table_is_not_counted_as_a_course(monkeypatch):
    """Markup beats depth, in the probe as it already does in the loader.

    Four real pages do this (#87). Counted by depth they inflate the
    denominator, which is the same error #74 fixes one level up.
    """
    serve(monkeypatch, {
        probe.SITEMAP: ('<urlset>'
                        '<loc>https://catalog.pwcs.edu/agriculture/landscaping-1</loc>'
                        '<loc>https://catalog.pwcs.edu/agriculture/ib-programme</loc>'
                        '</urlset>'),
        "https://catalog.pwcs.edu/agriculture/landscaping-1": NO_PREREQ,
        # course DEPTH, pathway MARKUP
        "https://catalog.pwcs.edu/agriculture/ib-programme": PATHWAY_PAGE})
    result = probe.probe(quiet=True)
    assert (result["courses"], result["pathways"]) == (1, 1)


def test_prerequisites_resolve_against_courses_and_not_against_every_page(monkeypatch):
    """`published_paths` must BE the set resolution ran against.

    It was every sitemap page, so the printed line said the links had been
    checked against 960 paths when 791 were eligible — a claim wider than the
    check behind it.
    """
    serve(monkeypatch, {
        probe.SITEMAP: (
            '<urlset><loc>https://catalog.pwcs.edu/agriculture</loc>'
            '<loc>https://catalog.pwcs.edu/agriculture/landscaping-1</loc>'
            '<loc>https://catalog.pwcs.edu/agriculture/landscaping-2</loc>'
            '</urlset>'),
        "https://catalog.pwcs.edu/agriculture": SUBJECT_INDEX,
        "https://catalog.pwcs.edu/agriculture/landscaping-1": NO_PREREQ,
        "https://catalog.pwcs.edu/agriculture/landscaping-2": COURSE})
    result = probe.probe(quiet=True)
    assert result["published_paths"] == result["courses"] == 2


PREREQ_ON_A_SUBJECT_INDEX = """<html><body><h1 class="page-title">Landscaping 2</h1>
<div class="field--name-field-prerequisite-courses">
<a href="/agriculture">Agriculture</a></div></body></html>"""


def test_a_prerequisite_pointing_at_a_subject_index_is_dangling_not_resolved(monkeypatch):
    """The narrowing of the RESOLUTION set, not just of the count.

    `published_paths` alone did not pin this: it is derived from the course
    list, so swapping the set passed to `resolve()` back to all 960 left every
    assertion green. The behaviour that actually changes needs a link pointing
    at a page that is published but is not a course — resolved under the old
    set, and then silently absent from the graph, because the loader only ever
    writes course-to-course edges.
    """
    serve(monkeypatch, {
        probe.SITEMAP: (
            '<urlset><loc>https://catalog.pwcs.edu/agriculture</loc>'
            '<loc>https://catalog.pwcs.edu/agriculture/landscaping-2</loc>'
            '</urlset>'),
        "https://catalog.pwcs.edu/agriculture": SUBJECT_INDEX,
        "https://catalog.pwcs.edu/agriculture/landscaping-2": PREREQ_ON_A_SUBJECT_INDEX})
    result = probe.probe(quiet=True)
    assert result["stating_a_prerequisite"] == 1
    assert result["resolvable_edges"] == 0
    assert result["dangling_links"] == 1
    assert result["no_link_resolves"] == 1


def test_the_summary_names_the_denominator_it_used(capsys, monkeypatch):
    """The print block is where the reader meets the number.

    Asserted on the printed text because a correct `result` dict printed
    against the old label is exactly the failure this issue is about.
    """
    serve(monkeypatch, {
        probe.SITEMAP: (
            '<urlset><loc>https://catalog.pwcs.edu/agriculture</loc>'
            '<loc>https://catalog.pwcs.edu/agriculture/landscaping-1</loc>'
            '</urlset>'),
        "https://catalog.pwcs.edu/agriculture": SUBJECT_INDEX,
        "https://catalog.pwcs.edu/agriculture/landscaping-1": COURSE})
    probe.probe()
    printed = capsys.readouterr().out
    assert "every rate below is quoted against this" in printed
    assert "subject indexes" in printed


def test_the_rate_carries_the_digit_that_distinguishes_the_denominators():
    """24% and 29% round apart; 28.8% and 29.0% do not.

    The documents quote this figure, so the decimal is what says which
    denominator produced it.
    """
    assert probe.pct(229, 791) == "29.0%"
    assert probe.pct(229, 960) == "23.9%"


# `catalogue_urls` returns `sorted(set(...))`, so a limited run reads the
# alphabetically FIRST pages, not the first in the sitemap. These fixtures are
# named so the page that states the prerequisite sorts before its target.
PREREQ_ON_ANOTHER_COURSE = """<html><body><h1 class="page-title">Landscaping 1</h1>
<div class="field--name-field-prerequisite-courses">
<a href="/agriculture/landscaping-9">Landscaping 9</a></div></body></html>"""

PREREQ_ON_AN_UNOPENED_SUBJECT = """<html><body><h1 class="page-title">Landscaping 1</h1>
<div class="field--name-field-prerequisite-courses">
<a href="/zoology">Zoology</a></div></body></html>"""

PARTIAL_SITEMAP = ('<urlset>'
                   '<loc>https://catalog.pwcs.edu/agriculture/landscaping-1</loc>'
                   '<loc>https://catalog.pwcs.edu/agriculture/landscaping-9</loc>'
                   '</urlset>')

PARTIAL_PAGES = {
    probe.SITEMAP: PARTIAL_SITEMAP,
    "https://catalog.pwcs.edu/agriculture/landscaping-1": PREREQ_ON_ANOTHER_COURSE,
    "https://catalog.pwcs.edu/agriculture/landscaping-9": NO_PREREQ}


def test_a_partial_run_does_not_call_an_unopened_course_a_broken_link(monkeypatch):
    """`--limit` resolved against the courses READ, not the courses published.

    Narrowing resolution to courses is #74's fix. Narrowing it to the pages
    this run happened to open is a different change, and it made a
    prerequisite pointing at any of the ~740 unopened courses dangle. The docs
    advertise `--limit 50` as a quick run whose output merely "says it is
    partial"; it would also have mis-reported the headline resolution figures,
    and the more partial the run the more broken the catalogue would look.

    One course is read. Its prerequisite points at a course that is published
    in the sitemap and is never opened.
    """
    serve(monkeypatch, PARTIAL_PAGES)
    result = probe.probe(limit=1, quiet=True)
    assert (result["population"], result["pages_read"]) == (2, 1)
    assert result["stating_a_prerequisite"] == 1
    assert result["dangling_links"] == 0
    assert result["every_link_resolves"] == 1
    assert result["no_link_resolves"] == 0
    # The reported set must BE the set resolution ran against, on a partial
    # run as much as on a full one: one course read, one unopened.
    assert result["published_paths"] == 2


def test_a_full_run_of_the_same_pages_reports_the_same_resolution(monkeypatch):
    """The partial-run widening must not change what a full run reports.

    On a full run nothing is unopened, so the set resolution uses is exactly
    the courses read — unchanged by this fix, and that is the claim.
    """
    serve(monkeypatch, PARTIAL_PAGES)
    full = probe.probe(quiet=True)
    assert full["published_paths"] == full["courses"] == 2
    assert full["dangling_links"] == 0


def test_a_partial_run_says_its_dangling_count_is_a_ceiling(monkeypatch):
    """The reader meets the caveat next to the number, or not at all."""
    serve(monkeypatch, PARTIAL_PAGES)
    assert "a ceiling, not a finding" in probe.probe(limit=1,
                                                     quiet=True)["coverage"]


def test_a_partial_run_still_dangles_a_link_to_a_page_that_is_not_a_course(monkeypatch):
    """The generosity is bounded: unopened means unknown, not "counts as a course".

    Without this, widening the set on a partial run could undo #74 itself — a
    prerequisite pointing at a subject index would resolve again, and the
    loader would still write no edge for it. The subject index here is
    unopened too, and must still dangle, because its DEPTH says it is not a
    course.
    """
    serve(monkeypatch, {
        probe.SITEMAP: (
            '<urlset>'
            '<loc>https://catalog.pwcs.edu/agriculture/landscaping-1</loc>'
            '<loc>https://catalog.pwcs.edu/zoology</loc>'
            '</urlset>'),
        "https://catalog.pwcs.edu/agriculture/landscaping-1": PREREQ_ON_AN_UNOPENED_SUBJECT,
        "https://catalog.pwcs.edu/zoology": SUBJECT_INDEX})
    result = probe.probe(limit=1, quiet=True)
    assert result["pages_read"] == 1
    assert result["dangling_links"] == 1
    assert result["no_link_resolves"] == 1

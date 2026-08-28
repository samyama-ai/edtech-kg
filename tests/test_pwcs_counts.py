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

"""`parse_pathway` — the parse that got it wrong the first time.

Its first version bounded the enclosing field with a lookahead that stopped at
the first section and found 71 of 218 rows. A partial parse returning plausible
numbers is the failure this repo keeps hitting, so these cases are what stops it
recurring.

Split out of `tests/test_pwcs_source.py` when that file passed the 500-line
review limit. Split by SUBJECT: this file drives the row-and-section parse with
synthetic markup, and `test_pwcs_source.py` covers keys, classification, and
what the cached catalogue actually holds.
"""

from __future__ import annotations

import pytest

from etl import probe_pwcs as source
from etl import pwcs_pages
from etl import pwcs_source as reader
from tests.test_pwcs_classify import needs_cache
from tests.pwcs_markup import PUBLISHED, row, section


def test_rows_are_read_from_every_section_not_only_the_first():
    """The defect: a pathway publishes SEVERAL course lists, one per named
    section, and the first version bounded the enclosing field with a lookahead
    that stopped at the first — 71 of 218 rows. A partial parse returning
    plausible numbers is the failure this repo keeps hitting."""
    markup = section("First", "/a/one") + section("Second", "/a/two", "/b/three")
    got = reader.parse_pathway(markup, "https://catalog.pwcs.edu/p", PUBLISHED)
    assert len(got["courses"]) == 3, got["courses"]


def test_each_row_is_attributed_to_the_section_it_sits_under():
    markup = section("First", "/a/one") + section("Second", "/a/two")
    got = reader.parse_pathway(markup, "https://catalog.pwcs.edu/p", PUBLISHED)
    assert ({reader.segments(c["url"])[-1]: c["section"] for c in got["courses"]}
            == {"one": "First", "two": "Second"})


def test_a_row_before_any_section_title_has_no_section():
    got = reader.parse_pathway(
        f'<div class="field field--name-field-degree-section-courses">{row("/a/one")}</div>',
        "https://catalog.pwcs.edu/p", PUBLISHED)
    assert got["courses"][0]["section"] is None


def test_a_section_title_is_unescaped():
    markup = section("Journalism &amp; Broadcasting", "/a/one")
    got = reader.parse_pathway(markup, "https://catalog.pwcs.edu/p", PUBLISHED)
    assert got["courses"][0]["section"] == "Journalism & Broadcasting"


def test_a_row_pointing_outside_the_sitemap_is_reported_not_dropped():
    """16 of the catalogue's 390 real rows point at a Drupal node id with no
    published alias. Counting them as absent would understate what the district
    publishes."""
    markup = section("First", "/a/one", "/node/1435")
    got = reader.parse_pathway(markup, "https://catalog.pwcs.edu/p", PUBLISHED)
    # By CONTENT, not by position. `got["courses"][0]` and an ordered
    # `dangling ==` make document order part of the contract, so re-ordering
    # the rows on the page — which the district may do at any time — fails a
    # test that is not about ordering.
    assert {c["url"] for c in got["courses"]} == {"https://catalog.pwcs.edu/a/one"}
    assert set(got["dangling"]) == {"https://catalog.pwcs.edu/node/1435"}


def test_a_rendered_field_with_no_rows_is_a_parse_failure_not_an_empty_pathway():
    """The same distinction the probe draws for the prerequisite field: the
    field would not be rendered at all if there were nothing in it."""
    markup = '<div class="field field--name-field-degree-section-courses"></div>'
    got = reader.parse_pathway(markup, "https://catalog.pwcs.edu/p", PUBLISHED)
    assert got["field_present_no_rows"] is True


def test_a_pathway_with_no_such_field_is_not_a_parse_failure():
    got = reader.parse_pathway("<html></html>", "https://catalog.pwcs.edu/p", PUBLISHED)
    assert got["field_present_no_rows"] is False
    assert got["courses"] == []


def test_a_credit_value_is_normalised_like_a_section_title():
    """One went through `html.unescape` and whitespace collapsing and the other
    did not, for no reason anyone chose."""
    # Asked of the builder rather than spliced into its output. The previous
    # form string-replaced `field__item">1</span>` inside built markup, so a
    # change to the credits element made this test stop exercising credits at
    # all — silently, since the un-replaced markup still parses.
    markup = section("First", "/a/one", credits="  1 &amp; a half\n")
    got = reader.parse_pathway(markup, "https://catalog.pwcs.edu/p", PUBLISHED)
    assert got["courses"][0]["credits"] == "1 & a half"


def test_a_row_under_no_section_is_counted_even_when_it_dangles():
    """`rows_without_a_section` was computed inside the resolving branch, so a
    template change that broke section titles on a page whose rows mostly
    dangle showed a small number and read as fine."""
    markup = row("/node/1435") + row("/node/1436")
    got = reader.parse_pathway(markup, "https://catalog.pwcs.edu/p", PUBLISHED)
    assert got["courses"] == []
    assert got["rows_without_a_section"] == 2, got


def test_a_row_with_no_credits_is_counted_rather_than_dropped():
    """`COURSE_ROW` required a credits field, so a `degree-row` article without
    one matched nothing at all — not in `rows`, not in `courses`, not in
    `dangling`. A published course simply disappeared.

    The real catalogue has exactly one such row, which is why the loss was
    small enough to go unnoticed and large enough to be wrong.

    The row is emitted INSIDE the section. The previous fixture built
    `section("First")` with no paths — which renders an empty
    `field-degree-section-courses` div, the exact markup
    `test_a_rendered_field_with_no_rows_is_a_parse_failure_not_an_empty_pathway`
    asserts is a parse failure — and then appended the article after the closing
    tag. It passed, because section attribution follows the last `<h2>` rather
    than the enclosing div, so the row picked up "First" from outside it. That
    is the test passing for a reason unrelated to credits, and a change to the
    empty-field branch could have flipped it either way.
    """
    got = reader.parse_pathway(section("First", "/a/one", credits=None),
                               "https://catalog.pwcs.edu/p", PUBLISHED)
    assert [c["url"] for c in got["courses"]] == ["https://catalog.pwcs.edu/a/one"]
    assert got["courses"][0]["credits"] is None
    assert got["courses"][0]["section"] == "First", (
        "a credits-less row must still be attributed to its section — the "
        "field it is missing is not the one that places it")
    assert got["rows_without_credits"] == 1, got
    assert got["field_present_no_rows"] is False, (
        "the fixture must not also be a parse failure, or this asserts two "
        "things at once and neither cleanly")


def test_dangling_and_resolved_rows_use_the_same_spelling():
    """`dangling` held raw hrefs while `courses` held absolute URLs, so the two
    lists could not be compared and a caller reading both got two spellings of
    one catalogue."""
    markup = section("First", "/a/one", "/node/1435")
    got = reader.parse_pathway(markup, "https://catalog.pwcs.edu/p", PUBLISHED)
    everything = [c["url"] for c in got["courses"]] + got["dangling"]
    assert all(u.startswith("https://") for u in everything), everything


# What the marker must and must not match. It decides a page's LABEL, and it
# had no test at all — the classification tests drive `classify`, which only
# reaches this on markup that already matches.
MARKER = "field--name-field-degree-section-courses"
MATCHES = [
    ("double quotes", f'<div class="{MARKER}">'),
    ("among other classes", f'<div class="a b {MARKER} c">'),
    ("single quotes", f"<div class='{MARKER}'>"),
    ("spaces round the equals", f'<div class = "{MARKER}">'),
]
REFUSES = [
    # `\b` sits between "courses" and a hyphen, because `-` is not a word
    # character — so a sibling Drupal field extending this name matched, and
    # the page was labelled a pathway.
    ("a longer field name", f'<div class="{MARKER}-teaser">'),
    ("a longer prefix", f'<div class="x-{MARKER}">'),
    ("the token in prose", f'<p>see {MARKER}</p>'),
    ("the token in another attribute", f'<div data-x="{MARKER}">'),
    # A QUOTE IS REQUIRED, and this is why. The first version of the widening
    # allowed the unquoted form, which admits a script string — and the module
    # docstring records script-string occurrences of this token as MEASURED on
    # this catalogue, not imagined.
    ("a script string", f'<script>var s="class={MARKER}"</script>'),
    ("the unquoted form nobody emits", f'<div class={MARKER}>'),
    # A bare `class` is a suffix of several real attribute names.
    ("data-class=", f'<div data-class="{MARKER}">'),
    ("ng-class=", f'<div ng-class="{MARKER}">'),
    (":class=", f'<div :class="{MARKER}">'),
    ("subclass=", f'<div subclass="{MARKER}">'),
]

#: What this expression genuinely cannot see. Written down as tests rather
#: than left implicit, because a reader of the lists above would reasonably
#: infer these were handled. Both would need the markup parsed rather than
#: matched, which is a bigger change than this classifier warrants.
KNOWN_LIMITS = [
    ("markup inside an HTML comment", f'<!-- <div class="{MARKER}"> -->'),
]


@pytest.mark.parametrize("what, markup", MATCHES, ids=lambda v: v)
def test_the_pathway_marker_is_read_in_every_form_markup_writes_it(what, markup):
    """Read in ONE of the three quoting forms, it did not FAIL on the other
    two — it fell through to depth, which is the classification this change
    exists to stop relying on. A CMS template change would have moved 172 rows
    back onto depth silently and every count would still have summed.
    """
    assert pwcs_pages.PATHWAY_FIELD_PRESENT.search(markup), what


@pytest.mark.parametrize("what, markup", REFUSES, ids=lambda v: v)
def test_the_pathway_marker_refuses_a_name_that_merely_contains_it(what, markup):
    assert not pwcs_pages.PATHWAY_FIELD_PRESENT.search(markup), what


@pytest.mark.parametrize("what, markup", KNOWN_LIMITS, ids=lambda v: v)
def test_the_known_limits_are_still_the_known_limits(what, markup):
    """Asserts the marker DOES match — these are documented holes, not bugs.

    If one of them starts refusing, this fails and the list gets shorter,
    which is the direction worth being told about.
    """
    assert pwcs_pages.PATHWAY_FIELD_PRESENT.search(markup), what


#: The four pages #87 found: published at COURSE depth, carrying a pathway's
#: course table. They are the entire reason the classifier exists.
RECLASSIFIED_BY_MARKUP = [
    "https://catalog.pwcs.edu/specialty-programs/center-for-biotechnology-and-engineering",
    "https://catalog.pwcs.edu/specialty-programs/"
    "information-technology-center-for-applied-sciences-interactive-and-information",
    "https://catalog.pwcs.edu/specialty-programs/international-baccalaureate",
    "https://catalog.pwcs.edu/virtual-prince-william/virtual-prince-william-information",
]


@needs_cache
@pytest.mark.parametrize("url", RECLASSIFIED_BY_MARKUP,
                         ids=lambda u: u.rsplit("/", 1)[-1][:40])
def test_the_pages_depth_reads_wrong_are_still_read_by_markup(url):
    """The safety net only guarded one direction.

    `MarkupDrift` fires above `RECLASSIFIED_FLOOR = 10`, which catches the
    marker suddenly matching far too much. Nothing catches it matching too
    little: a drop from four reclassified pages to zero is UNDER the floor, so
    it passes silently and up to 172 published rows go back to being read as
    courses — the same quiet way #87 describes.

    Named individually rather than counted, so the failure says which page.
    """
    markup = source.cached_path(url).read_text(encoding="utf-8")
    assert reader.level(url) == "course", (
        "this page is no longer at course depth, so it is not the case #87 "
        "found and this test is guarding nothing")
    assert reader.classify(url, markup) == "pathway", (
        "depth says course and the markup no longer says pathway, so this "
        "page's course table is about to be read as a course")


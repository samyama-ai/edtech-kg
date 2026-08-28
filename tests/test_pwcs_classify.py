"""How a page gets its label, and how far the markup override reaches.

Depth says what a URL looks like; `classify` says what a page IS. They disagree
on four pages of 960, and reading by depth alone cost 172 published rows that
never became edges (edtech-kg#87).

Split out of `tests/test_pwcs_source.py` when it passed the 500-line review
limit. Split by SUBJECT: this file is classification — the depth rule, the
markup override that beats it, and the two bounds that stop the override
running away. `test_pwcs_source.py` keeps keys and what the cached catalogue
holds; `test_pwcs_pathways.py` keeps the row-and-section parse.

The override is the risky part and most of this file is about its edges,
because it decides a node's LABEL from a regex over raw HTML — and `verify()`
structurally cannot catch it getting that wrong.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from etl import probe_pwcs as source
from etl import pwcs_source as reader
from tests.pwcs_markup import section, titled

CACHE = Path(__file__).resolve().parents[1] / "data" / "pwcs"


def cache_is_complete() -> bool:
    """Every page the sitemap lists is on disk — the same guard
    `test_pwcs_source.py` uses, and for the same reason: a partial cache would
    fetch the remainder from a school district, from a test run."""
    if not CACHE.exists():
        return False
    try:
        urls = source.catalogue_urls(True)
    except Exception:                      # noqa: BLE001 — no cached sitemap
        return False
    return bool(urls) and all(source.cached_path(u).exists() for u in urls)


needs_cache = pytest.mark.skipif(
    not cache_is_complete(),
    reason=("the cached catalogue is incomplete — run `python -m etl.probe_pwcs` "
            "first; a partial cache would fetch the remainder from the district"))


@pytest.fixture(scope="module")
def catalogue():
    return reader.read()


def test_level_names_each_depth_and_refuses_to_guess():
    """It was an `if 1 … elif 2 … else pathway` inside `read()`, so the root
    and anything nested deeper than a pathway were swept into "pathway" and
    parsed for a course table they do not have."""
    assert reader.level("https://catalog.pwcs.edu/band") == "subject"
    assert reader.level("https://catalog.pwcs.edu/band/concert") == "course"
    assert reader.level("https://catalog.pwcs.edu/cte/career-pathways/it") == "pathway"
    assert reader.level("https://catalog.pwcs.edu") is None
    assert reader.level("https://catalog.pwcs.edu/a/b/c/d") is None


def test_an_unexpected_depth_is_counted_not_read_as_a_pathway():
    urls = ["https://catalog.pwcs.edu/band",
            "https://catalog.pwcs.edu/band/concert",
            "https://catalog.pwcs.edu/a/b/c/d"]
    got = reader.read(urls=urls, fetch=lambda u: titled("A page"))
    assert got["unclassified"] == ["https://catalog.pwcs.edu/a/b/c/d"]
    assert len(got["subjects"]) == 1 and len(got["courses"]) == 1
    assert got["pathways"] == []


def test_a_page_that_does_not_parse_is_counted_not_dropped():
    """It was a bare `continue`. A CMS change breaking `parse_course` would
    shrink the graph by however many pages it broke, with nothing said."""
    urls = ["https://catalog.pwcs.edu/band",
            "https://catalog.pwcs.edu/band/concert"]
    got = reader.read(urls=urls,
                      fetch=lambda u: titled("A page") if u.endswith("band") else "<html></html>")
    assert got["unparsed"] == ["https://catalog.pwcs.edu/band/concert"], got["unparsed"]
    assert len(got["subjects"]) == 1
    assert got["courses"] == []


def test_a_page_publishing_a_course_table_is_a_pathway_whatever_its_depth():
    """The #87 fix. Depth is the catalogue's own structure and holds for 956 of
    960 pages; four publish a pathway's course table at COURSE depth. Read by
    depth alone they loaded as `Course`, their tables were never opened, and
    172 published rows never became edges.

    Nothing failed while that was true — the loader and the engine agreed
    about a set that was already short — which is why the markup has to win
    over the address.
    """
    urls = ["https://catalog.pwcs.edu/specialty-programs",
            "https://catalog.pwcs.edu/specialty-programs/it-centre"]

    def fetch(url):
        if url.endswith("it-centre"):
            return titled("IT Centre") + section("Only", "/a/one")
        return titled("Specialty programs")

    got = reader.read(urls=urls, fetch=fetch)
    assert ([r["url"] for r in got["pathways"]]
            == ["https://catalog.pwcs.edu/specialty-programs/it-centre"]), got["pathways"]
    assert got["courses"] == [], "the page was still read as a course"
    # And the disagreement is reported rather than silently resolved.
    assert (got["reclassified"]
            == ["https://catalog.pwcs.edu/specialty-programs/it-centre"]), got


def test_a_page_at_course_depth_with_no_course_table_is_still_a_course():
    """The markup only wins where there IS markup to win with. A page that
    publishes no course table is classified by depth exactly as before, or
    every course in the catalogue would become a pathway."""
    urls = ["https://catalog.pwcs.edu/band",
            "https://catalog.pwcs.edu/band/concert"]
    got = reader.read(urls=urls, fetch=lambda u: titled("A page"))
    assert ([r["url"] for r in got["courses"]]
            == ["https://catalog.pwcs.edu/band/concert"]), got["courses"]
    assert got["pathways"] == [] and got["reclassified"] == [], got


@needs_cache
def test_the_four_reclassified_pages_are_the_ones_measured(catalogue):
    """The figure #87 quotes, read from the catalogue rather than typed.

    The invariant, not the census: every reclassified page is a real published
    page that URL depth would NOT have called a pathway, and it is now in the
    pathway list. A fifth appearing is a fact about the catalogue, not a
    defect, and this says so rather than failing on it.
    """
    reclassified = catalogue["reclassified"]
    assert reclassified, "the reclassification is no longer happening — see #87"
    published = set(catalogue["urls"])
    pathway_urls = {r["url"] for r in catalogue["pathways"]}
    for url in reclassified:
        assert url in published, url
        assert reader.level(url) != "pathway", (url, reader.level(url))
        assert url in pathway_urls, f"{url} was reclassified and not loaded as one"

    # And their tables were actually READ, not just relabelled. #87 exists
    # because 172 published rows never became edges; a page that changes label
    # and contributes no rows has not fixed anything.
    #
    # A floor, not the census. 172 today; asserting that exactly would fail the
    # day the district edits one table, which is not a defect. Asserting a
    # floor fails when the rows stop arriving, which is.
    recovered = sum(len(r["courses"]) for r in catalogue["pathways"]
                    if r["url"] in set(reclassified))
    assert recovered >= 150, (
        f"the four reclassified pages contributed {recovered} resolving rows; "
        f"#87 recovered 172, and a collapse to near zero means the tables are "
        f"being relabelled without being read")


def test_a_pathway_row_naming_a_reclassified_page_does_not_resolve_as_a_course():
    """The course set is an OUTPUT of classification, not an input to it.

    It used to be derived from URL depth before the pages were read — the same
    assumption `classify` exists to correct. Left that way, a page reclassified
    OUT of the courses would still be in the set a pathway row resolves
    against: the row would count as resolved, the loader would write
    `MATCH (c:Course {url: …})` for a node that is now a `:Pathway`, the MATCH
    would find nothing, and the counter would still increment.

    No row in this catalogue names one of the four, which is the only reason
    the single-pass version agreed. This drives the case the data does not
    have.
    """
    urls = ["https://catalog.pwcs.edu/cte/career-pathways/it",   # a real pathway
            "https://catalog.pwcs.edu/specialty/it-centre",      # reclassified
            "https://catalog.pwcs.edu/a/one"]                    # a plain course

    def fetch(url):
        if url.endswith("career-pathways/it"):
            # Its rows name the reclassified page AND a real course.
            return titled("IT pathway") + section(
                "Only", "/specialty/it-centre", "/a/one")
        if url.endswith("it-centre"):
            return titled("IT Centre") + section("Inner", "/a/one")
        return titled("A course")

    got = reader.read(urls=urls, fetch=fetch)
    assert got["reclassified"] == ["https://catalog.pwcs.edu/specialty/it-centre"], got

    pathway = next(r for r in got["pathways"] if r["url"].endswith("career-pathways/it"))
    resolved = {c["url"] for c in pathway["courses"]}
    assert resolved == {"https://catalog.pwcs.edu/a/one"}, (
        "a page that is now a Pathway still resolved as a course")
    assert "https://catalog.pwcs.edu/specialty/it-centre" in pathway["dangling"], (
        "the row naming a reclassified page should be reported, not counted "
        "as a resolved course")

    # And the reclassified page's OWN table is read. Everything above checks
    # the label moved; without this, nothing checks the rows came out — which
    # is the entire point of #87.
    #
    # The regression that slides through otherwise: `pathway_markup[url]` is
    # filled under `if kind == "pathway"`. Tidying that to `level(url)` makes
    # `.pop()` raise, and the natural repair is `.pop(url, "")` — at which
    # point `parse_pathway("")` returns no courses, the four pages load as
    # Pathway nodes with zero INCLUDES edges, and the suite stays green.
    # Verified: that exact mutation passed all 486 tests before this assertion.
    inner = next(r for r in got["pathways"] if r["url"].endswith("it-centre"))
    assert [c["url"] for c in inner["courses"]] == ["https://catalog.pwcs.edu/a/one"], (
        "the reclassified page was labelled a Pathway but its course table "
        "was never read")
    assert inner["courses"][0]["section"] == "Inner"


def test_a_course_page_that_does_not_parse_is_reported_not_just_missing():
    """`course_paths` is built from the parsed records, so a course page that
    fails `parse_course` is not in it — and a pathway row naming that page
    counts as dangling rather than resolved.

    That is the right call for edge-writing: the page will not become a
    `Course` node, so a row naming it must not count as resolved or the count
    and the graph disagree with nothing to say why.

    But it gives `dangling` two causes — no published page at all, and a
    published page that did not parse — and only one of them is what
    `docs/schema.md` claims about the 16 dangling rows today. `unparsed` is
    what separates them, so this drives the case the catalogue does not have
    and asserts both facts are recoverable rather than one hiding the other.
    """
    urls = ["https://catalog.pwcs.edu/band/concert",
            "https://catalog.pwcs.edu/band/jazz",
            "https://catalog.pwcs.edu/cte/career-pathways/music"]

    def fetch(url):
        if url.endswith("career-pathways/music"):
            return titled("Music") + section("Only", "/band/concert", "/band/jazz")
        if url.endswith("band/jazz"):
            return "<html></html>"          # published, but no <h1> to read
        return titled("Concert Band")

    got = reader.read(urls=urls, fetch=fetch)

    assert got["unparsed"] == ["https://catalog.pwcs.edu/band/jazz"], got["unparsed"]
    assert [c["url"] for c in got["pathways"][0]["courses"]] == \
        ["https://catalog.pwcs.edu/band/concert"]
    # Absolute, the same spelling `courses` uses — so the two lists can be
    # compared without one caller re-deriving the other's form.
    assert got["pathways"][0]["dangling"] == \
        ["https://catalog.pwcs.edu/band/jazz"], got["pathways"][0]

    # The point of the test: the row dangles AND the reason is recoverable.
    # Reading `dangling` alone would say the catalogue publishes no page for
    # it, which is false — it publishes one that could not be read.
    assert got["unparsed"][0] in got["pathways"][0]["dangling"]


def test_pathway_markup_is_released_as_each_page_is_parsed():
    """The second pass reads each pathway's page out of a dict the first pass
    filled. It pops rather than reads, so the dict shrinks as it goes instead
    of holding every page for the life of the call — 1.2 MB today across 42
    pages, which is small, but a dict that only grows is the shape that stops
    being small without anyone noticing.

    The first version of this test asserted only that `parse_pathway` was
    called with the pathway's url, which is true whether the entry is popped or
    read and says nothing about the name on the test. This one reads the
    caller's own dict at the moment it hands over a page: `.pop()` happens
    before the call, so by then the page being parsed is already gone.

    Two pathways, so the counts distinguish the two implementations — popping
    gives [1, 0] and reading would give [2, 2].
    """
    import sys

    held_during = []
    original = reader.parse_pathway

    def spy(markup, url, course_paths):
        held_during.append(len(sys._getframe(1).f_locals["pathway_markup"]))
        return original(markup, url, course_paths)

    urls = ["https://catalog.pwcs.edu/cte/career-pathways/music",
            "https://catalog.pwcs.edu/cte/career-pathways/art"]
    reader.parse_pathway = spy
    try:
        got = reader.read(urls=urls,
                          fetch=lambda u: titled("A pathway") + section("Only", "/a/one"))
    finally:
        reader.parse_pathway = original

    assert len(got["pathways"]) == 2, "both pages must classify as pathways"
    assert held_during == [1, 0], (
        f"the dict held {held_during} pages while parsing; popping leaves "
        f"[1, 0] and reading would leave [2, 2]")


@pytest.mark.parametrize("markup,why", [
    ("<!-- field--name-field-degree-section-courses -->", "an HTML comment"),
    ("<p>the field--name-field-degree-section-courses class</p>", "body prose"),
    ('<script>var x="field--name-field-degree-section-courses";</script>', "a script string"),
    ('<input value="field--name-field-degree-section-courses">', "a reflected input value"),
])
def test_the_field_name_outside_a_class_attribute_does_not_reclassify(markup, why):
    """The pattern decides a node's LABEL, so matching the token anywhere in the
    document is too loose. All four of these classified as pathway before it was
    bound to a class attribute — measured, not supposed.

    It was also looser than `COURSE_ROW`, which already requires the token
    inside a real `class="…"`: the classifier was weaker than the row parser it
    gates.
    """
    page = titled("A course") + markup
    assert reader.classify("https://catalog.pwcs.edu/band/x", page) == "course", why


def test_the_field_name_inside_a_class_attribute_still_reclassifies():
    """The fix must not be so tight that it stops seeing the real thing — the
    four pages #87 is about are found by exactly this."""
    page = titled("IT Centre") + section("Only", "/a/one")
    assert reader.classify("https://catalog.pwcs.edu/band/x", page) == "pathway"


@pytest.mark.parametrize("url,depth", [
    ("https://catalog.pwcs.edu", 0),
    ("https://catalog.pwcs.edu/band", 1),
    ("https://catalog.pwcs.edu/band/concert", 2),
    ("https://catalog.pwcs.edu/a/b/c/d", 4),
])
def test_the_markup_override_applies_at_every_depth_as_documented(url, depth):
    """`classify` is documented as unconditional and every other test drives
    depth 2, because all four real pages are depth 2. A later "let us be
    conservative" narrowing to `if level(url) == "course" and …` would pass the
    whole suite otherwise.

    Depth 0 and 4 have no level at all, so this also pins that a page with the
    field lands in `pathway` rather than in `unclassified` — the docstring says
    so and nothing checked it.
    """
    page = titled("X") + section("Only", "/a/one")
    assert reader.classify(url, page) == "pathway", depth


def test_a_deep_page_publishing_the_field_is_reported_as_reclassified():
    """The read()-level counterpart: a depth-4 page with a course table must
    reach `pathways` and `reclassified`, not `unclassified`."""
    urls = ["https://catalog.pwcs.edu/a/b/c/d", "https://catalog.pwcs.edu/a/one"]

    def fetch(url):
        if url.endswith("/d"):
            return titled("Deep") + section("Only", "/a/one")
        return titled("A course")

    got = reader.read(urls=urls, fetch=fetch)
    assert got["reclassified"] == ["https://catalog.pwcs.edu/a/b/c/d"], got
    assert [r["url"] for r in got["pathways"]] == ["https://catalog.pwcs.edu/a/b/c/d"]
    assert got["unclassified"] == [], "a page with a course table is not unclassified"


def test_wholesale_reclassification_is_refused_rather_than_loaded():
    """`verify()` cannot catch this. It compares the engine against the
    loader's own tallies, and if every page becomes a Pathway both move
    together — the load reports success and the graph is wrong. That is the
    same failure #87 is about, one level up.

    The realistic trigger is the CMS rendering the course-table class in a
    shared template or footer partial. Four of 960 is a catalogue fact; a tenth
    of the catalogue is a parser reading something it should not.

    Both bounds must trip. The fraction alone would make any small fixture
    unloadable — one page of two is 50% — and the floor alone would fire on a
    district that legitimately published a dozen more specialty programs.
    """
    urls = [f"https://catalog.pwcs.edu/band/course-{n}" for n in range(40)]
    everything = titled("X") + section("Only", "/a/one")

    with pytest.raises(reader.MarkupDrift, match="markup drift"):
        reader.read(urls=urls, fetch=lambda u: everything)


def test_a_few_reclassified_pages_are_still_loaded_normally():
    """The ceiling must not fire on the case it exists to allow — otherwise
    #87's own four pages would refuse to load."""
    urls = [f"https://catalog.pwcs.edu/band/course-{n}" for n in range(20)]
    plain = titled("A course")
    table = titled("Centre") + section("Only", "/band/course-1")

    got = reader.read(urls=urls,
                      fetch=lambda u: table if u.endswith("course-0") else plain)
    assert got["reclassified"] == ["https://catalog.pwcs.edu/band/course-0"]
    assert len(got["courses"]) == 19


# --------------------------------------------------------------------------
# the invariant #74 rests on, measured rather than assumed
# --------------------------------------------------------------------------

@needs_cache
def test_narrowing_the_denominator_drops_no_prerequisite_and_no_edge():
    """edtech-kg#74 leaves the 240 edges alone ONLY because of this.

    The fix narrows the denominator from 960 pages to 791 courses and narrows
    resolution with it. That is safe if — and only if — none of the 169 pages
    removed was contributing a prerequisite, AND no prerequisite pointed at
    one. The issue asserted both from a one-off measurement.

    BOTH halves in one test, over one pass of the cache: they are two
    directions of a single claim, and each is meaningless without the other.
    A page could state no prerequisite and still be the TARGET of one, which
    is the case that would silently drop a real edge.
    """
    from etl import probe_pwcs as probe

    urls = source.catalogue_urls(True)
    markup = {u: source.cached_path(u).read_text(encoding="utf-8") for u in urls}
    kind_of = {u: reader.classify(u, markup[u]) for u in urls}
    by_path = {probe.path_of(u): kind_of[u] for u in urls}

    states_one, targets = [], []
    for url in urls:
        parsed = probe.parse_course(markup[url], url)
        if kind_of[url] != "course":
            if parsed and (parsed.get("prerequisite_links")
                           or parsed.get("field_present_no_links")):
                states_one.append(url)
            continue
        for link in (parsed or {}).get("prerequisite_links") or []:
            targets.append(by_path.get(probe.path_of(link["href"]), "OFF-CATALOGUE"))

    assert states_one == [], "a page that is not a course now states a prerequisite"
    assert targets, "no prerequisite links found — the cache is not the catalogue"
    assert set(targets) == {"course"}


@needs_cache
def test_the_document_quotes_the_figures_the_probe_produces():
    """`docs/sources/course-prerequisites.md` is where these numbers are read.

    Nothing tied the page to the probe, so putting the old 229-of-960 back
    into the table left the whole suite green — the fix was in the code and
    the wrong number was still on the page a reader opens. Every figure below
    is pulled out of the document by pattern and compared to a run over the
    cached catalogue.
    """
    import re

    from etl import probe_pwcs as probe

    doc = (Path(__file__).resolve().parents[1] / "docs" / "sources"
           / "course-prerequisites.md").read_text()
    result = probe.probe(quiet=True)

    def figure(pattern: str) -> str:
        found = re.search(pattern, doc)
        assert found, f"the page no longer states {pattern!r}"
        return found.group(1).replace(",", "")

    assert int(figure(r"\| Course pages \| \*\*([\d,]+)\*\*")) == result["courses"]
    assert int(figure(r"\| Pages in the sitemap \| \*\*([\d,]+)\*\*")) == result["population"]
    assert int(figure(r"\| Linking at least one prerequisite \| \*\*([\d,]+)\*\*")) \
        == result["stating_a_prerequisite"]
    assert figure(r"\| Linking at least one prerequisite \|[^|]*\|[^|]*?\*\*([\d.]+%)\*\*") \
        == probe.pct(result["stating_a_prerequisite"], result["courses"])
    assert int(figure(r"\| \*\*Resolvable prerequisite edges\*\* \| \*\*([\d,]+)\*\*")) \
        == result["resolvable_edges"]

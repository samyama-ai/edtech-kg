"""Reading the catalogue — keys, and the parse that got it wrong once.

`parse_pathway` found 71 of 218 rows in its first version, because a pathway
publishes several course lists and the bound stopped at the first. A partial
parse returning plausible numbers is the failure this repo keeps hitting, so
the fixtures here are the thing that stops it recurring.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from etl import probe_pwcs as source
from etl import pwcs_source as reader
from tests.pwcs_markup import section, titled

CACHE = Path(__file__).resolve().parents[1] / "data" / "pwcs"

# `read()` walks 960 pages. Cached they are local and instant; cold it is 960
# requests to a school district from a test run. `data/` is gitignored, so a
# fresh clone has none of it, and these would hammer the source rather than
# fail. Skipped instead — with the command that makes them runnable.
# A PARTIAL cache is worse than none: `read()` walks the sitemap, finds most
# pages locally and fetches the rest — from a school district, from a test run.
#
# Compared against the SITEMAP, not against a threshold. "900 of ~960" was a
# number that contradicted the argument beside it: sixty missing pages is sixty
# live fetches, which is exactly what the guard says it prevents. And
# `glob("*")` counted any entry — a subdirectory, a half-written download — so
# it was a weak proxy for the thing it claimed to measure.


def cache_is_complete() -> bool:
    """Every page the sitemap lists is on disk. Exact, and cheap: the sitemap
    itself is cached, so this reads no network."""
    if not CACHE.exists():
        return False
    try:
        urls = source.course_urls(True)
    except Exception:                      # noqa: BLE001 — no cached sitemap
        return False
    return bool(urls) and all(source.cached_path(u).exists() for u in urls)


needs_cache = pytest.mark.skipif(
    not cache_is_complete(),
    reason=("the cached catalogue is incomplete — run `python -m etl.probe_pwcs` "
            "first; a partial cache would fetch the remainder from the district"))

# --------------------------------------------------------------------------
# keys


def test_a_requirement_id_is_stable():
    same = (reader.requirement_id("https://a/x", "Teacher recommendation"),
            reader.requirement_id("https://a/x", "Teacher  recommendation\n"))
    assert same[0] == same[1], "whitespace should normalise, so a re-run MERGEs"


def test_two_districts_sharing_a_path_get_different_requirement_ids():
    """The defect 577975e fixed, asserted rather than remembered: the id was
    derived from the course PATH, and a path does not carry the district."""
    a = reader.requirement_id("https://one.edu/maths/algebra-1", "Teacher recommendation")
    b = reader.requirement_id("https://two.edu/maths/algebra-1", "Teacher recommendation")
    assert a != b


def test_an_href_becomes_the_absolute_url_the_key_is_built_on():
    assert reader.absolute("/art/1") == "https://catalog.pwcs.edu/art/1"
    assert reader.absolute("/art/1/") == "https://catalog.pwcs.edu/art/1", "trailing slash"
    assert reader.absolute("/art/1#top") == "https://catalog.pwcs.edu/art/1", "fragment"


def test_segments_counts_the_catalogue_levels():
    assert reader.segments("https://catalog.pwcs.edu/band") == ["band"]
    assert reader.segments("https://catalog.pwcs.edu/band/concert") == ["band", "concert"]


@pytest.fixture(scope="module")
def catalogue():
    """One `read()` for every test that needs the real catalogue.

    It walks ~960 cached pages and re-parses each one. Three tests called it
    independently, so the cache was read three times over to answer three
    questions about the same result.
    """
    return reader.read()


# --------------------------------------------------------------------------
# parse_pathway — the parse that got it wrong the first time


@needs_cache
def test_the_three_levels_account_for_every_sitemap_page(catalogue):
    """791 courses, 127 subjects, 42 pathways. The probe reports all 960 as
    courses (#74); the split has to add up or one of the three is wrong.

    A page can leave the sitemap total in TWO ways, and this used to blame the
    first for both: it can be classified as none of the three, or it can fail
    to parse and never reach the classifier at all. `read()` counts them
    separately now, so a CMS change breaking `parse_course` reports itself
    rather than reading as a classification fault.
    """
    data = catalogue
    total = len(data["subjects"]) + len(data["courses"]) + len(data["pathways"])
    assert data["unparsed"] == [], (
        f"{len(data['unparsed'])} sitemap page(s) returned no record at all: "
        f"{data['unparsed'][:3]}")
    assert total == len(data["urls"]), (
        f"{len(data['urls'])} pages in the sitemap, {total} classified, "
        f"{len(data['unclassified'])} unclassified, {len(data['unparsed'])} unparsed")
    # The invariant, not the census. Asserting 127/791/42 fails the day the
    # district publishes one more course — which is not a defect, and a test
    # that cries about it teaches people to ignore it. What must hold is that
    # every page lands in exactly one bucket and none is left unclassified.
    assert data["unclassified"] == [], data["unclassified"]
    assert data["courses"], "no courses classified at all"


@needs_cache
def test_no_prerequisite_crosses_out_of_the_course_level(catalogue):
    """The claim edtech-kg#74 rests on: reclassifying 169 pages does not touch
    the 240 edges, because no page outside the 791 is at either end of one.

    **Both assertions below hold when nothing was parsed.** An empty
    `prerequisite_links` on every record satisfies the loop, and an empty
    `depths` satisfies `<= {2}` — so a CMS change that stopped the prerequisite
    field parsing would have turned this into a confident statement about
    zero links. The count is asserted first, so the claim rests on something
    measured rather than on an absence.
    """
    data = catalogue
    links = [link for r in data["courses"] for link in r["prerequisite_links"]]
    assert len(links) >= 240, (
        f"only {len(links)} prerequisite link(s) parsed; the catalogue publishes "
        f"240, so this test would otherwise pass on having read nothing")

    for record in data["subjects"] + data["pathways"]:
        assert not record["prerequisite_links"], record["url"]
    depths = {len(reader.segments(link["href"])) for link in links}
    assert depths == {2}, f"a prerequisite points outside the course level: {depths}"


def test_the_normalisation_rule_names_every_url_keyed_label():
    """Course, Subject and Pathway are all keyed on the address of a published
    page, and the rule that says how that address is spelled has to cover all
    three or it covers none of them."""
    text = (Path(__file__).resolve().parents[1]
            / "schema" / "edtech_kg.cypher").read_text()
    # `str.index` raises ValueError naming a substring, from which nobody can
    # tell that a heading was renamed. `find` and an assertion say it.
    start, end = text.find("NORMALISATION"), text.find("CREATE CONSTRAINT ON (c:Course)")
    assert start != -1, "the schema no longer states a NORMALISATION rule"
    assert end > start, "the Course constraint no longer follows the rule"
    rule = text[start:end]
    for label in ("Subject.url", "Pathway.url"):
        assert label in rule, f"the normalisation rule does not mention {label}"


# --------------------------------------------------------------------------
# parse_pathway, continued — the fields on a row


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


def test_a_pathway_row_pointing_at_a_subject_page_does_not_count_as_resolved():
    """`published` includes subject and pathway pages. A row pointing at one
    counted as a resolved course edge and then wrote nothing — the count and
    the graph disagreeing, with nothing to say why. No row does that today;
    that is a property of this catalogue, not of the parser."""
    urls = ["https://catalog.pwcs.edu/band",                       # a subject
            "https://catalog.pwcs.edu/band/concert",               # a course
            "https://catalog.pwcs.edu/cte/career-pathways/music"]  # a pathway

    def fetch(url):
        if reader.level(url) == "pathway":
            # One row naming the course, one naming the SUBJECT page.
            return titled("Music") + section("Only", "/band/concert", "/band")
        return titled("A page")

    got = reader.read(urls=urls, fetch=fetch)
    pathway = got["pathways"][0]
    assert [c["url"] for c in pathway["courses"]] == \
        ["https://catalog.pwcs.edu/band/concert"]
    assert pathway["dangling"] == ["https://catalog.pwcs.edu/band"], pathway["dangling"]


def test_an_absolute_url_drops_the_query_and_keeps_the_root_slash():
    """The schema's normalisation rule says the query is DROPPED; `absolute`
    kept it, so an href carrying `?utm_source=x` produced a second key for a
    page already loaded — and a constraint in 1.1.0 declares the key without
    enforcing it, so nothing would have caught the duplicate.

    `rstrip("/")` on a root href gave a URL with no path at all, which is a
    different string from the sitemap's: the MATCH finds nothing and the edge
    is silently not written."""
    assert reader.absolute("/art/1?utm_source=x") == "https://catalog.pwcs.edu/art/1"
    assert reader.absolute("/art/1?a=1#top") == "https://catalog.pwcs.edu/art/1"
    assert reader.absolute("/") == "https://catalog.pwcs.edu/"
    assert reader.absolute("/art/1/") == "https://catalog.pwcs.edu/art/1"


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


def test_an_href_that_is_already_absolute_is_left_alone():
    """Real markup carries absolute and protocol-relative hrefs as well as
    root-relative ones. Neither appears in this catalogue today, which is why
    nothing exercised them."""
    assert reader.absolute("https://catalog.pwcs.edu/art/1") == \
        "https://catalog.pwcs.edu/art/1"
    # Protocol-relative: the scheme comes from the base, the host does not.
    assert reader.absolute("//other.example/z") == "https://other.example/z"


def test_a_document_relative_href_resolves_against_the_site_root(monkeypatch):
    """`urljoin` with the SITEMAP as base resolves "algebra-1" against the
    sitemap's DIRECTORY, which is not where catalogue pages live.

    The real sitemap sits at the root, so both spellings agree today and no
    fixture using it can tell them apart. The sitemap is moved into a
    subdirectory here — which is where a district that reorganises its site
    would put it — so the difference is visible.
    """
    monkeypatch.setattr(source, "SITEMAP",
                        "https://catalog.pwcs.edu/feeds/sitemap.xml")
    assert reader.absolute("algebra-1") == "https://catalog.pwcs.edu/algebra-1", \
        "a document-relative href resolved against the sitemap's directory"
    assert reader.absolute("/art/1") == "https://catalog.pwcs.edu/art/1"


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

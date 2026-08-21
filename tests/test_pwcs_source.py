"""Reading the catalogue — keys, and the parse that got it wrong once.

`parse_pathway` found 71 of 218 rows in its first version, because a pathway
publishes several course lists and the bound stopped at the first. A partial
parse returning plausible numbers is the failure this repo keeps hitting, so
the fixtures here are the thing that stops it recurring.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from etl import load_pwcs as loader
from etl import pwcs_source as reader
from etl.engine import Unquotable

CACHE = Path(__file__).resolve().parents[1] / "data" / "pwcs"

# `read()` walks 960 pages. Cached they are local and instant; cold it is 960
# requests to a school district from a test run. `data/` is gitignored, so a
# fresh clone has none of it, and these would hammer the source rather than
# fail. Skipped instead — with the command that makes them runnable.
needs_cache = pytest.mark.skipif(
    not CACHE.exists() or not any(CACHE.iterdir()),
    reason="no cached catalogue in data/pwcs — run `python -m etl.probe_pwcs` first")

# --------------------------------------------------------------------------
# keys
# --------------------------------------------------------------------------

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
# --------------------------------------------------------------------------

def row(path: str, credits: str = "1") -> str:
    return (f'<article about="{path}" class="node row degree-row">'
            f'<div class="col-10"><a href="{path}">A course</a></div>'
            f'<span class="field field--name-field-credits field__item">{credits}</span>'
            f'</article>')


def section(title: str, *paths: str) -> str:
    return (f'<h2 class="field field--name-field-degree-section-title '
            f'field__item">{title}</h2>'
            f'<div class="field field--name-field-degree-section-courses">'
            + "".join(row(p) for p in paths) + "</div>")


PUBLISHED = {"/a/one", "/a/two", "/b/three"}


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
    assert {reader.segments(c["url"])[-1]: c["section"] for c in got["courses"]} \
        == {"one": "First", "two": "Second"}


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
    """Five of 202 real rows point at a Drupal node id with no published alias.
    Counting them as absent would understate what the district publishes."""
    markup = section("First", "/a/one", "/node/1435")
    got = reader.parse_pathway(markup, "https://catalog.pwcs.edu/p", PUBLISHED)
    assert len(got["courses"]) == 1
    assert got["dangling"] == ["/node/1435"]


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


# --------------------------------------------------------------------------
# what the catalogue actually holds — read from the cache, not asserted
# --------------------------------------------------------------------------

@needs_cache
def test_the_three_levels_account_for_every_sitemap_page(catalogue):
    """795 courses, 127 subjects, 38 pathways. The probe reports all 960 as
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
    # The invariant, not the census. Asserting 127/795/38 fails the day the
    # district publishes one more course — which is not a defect, and a test
    # that cries about it teaches people to ignore it. What must hold is that
    # every page lands in exactly one bucket and none is left unclassified.
    assert data["unclassified"] == [], data["unclassified"]
    assert data["courses"], "no courses classified at all"


@needs_cache
def test_no_prerequisite_crosses_out_of_the_course_level(catalogue):
    """The claim #74 rests on: reclassifying 165 pages does not touch the 240
    edges, because no page outside the 795 is at either end of one."""
    data = catalogue
    for record in data["subjects"] + data["pathways"]:
        assert not record["prerequisite_links"], record["url"]
    depths = {len(reader.segments(link["href"]))
              for r in data["courses"] for link in r["prerequisite_links"]}
    assert depths <= {2}, f"a prerequisite points outside the course level: {depths}"


# --------------------------------------------------------------------------
# reading the catalogue
# --------------------------------------------------------------------------

def test_a_comment_is_stripped_but_a_url_in_a_literal_is_not():
    """Splitting on `//` unconditionally truncates a statement carrying a URL
    at the scheme. No schema statement does today — the URLs are in comments —
    which is the only reason the naive split never did damage."""
    assert loader.strip_comment("CREATE INDEX ON :C(year);  // annual") \
        == "CREATE INDEX ON :C(year);  "
    assert loader.strip_comment("MERGE (n {url: 'https://x/y'})") \
        == "MERGE (n {url: 'https://x/y'})"
    assert loader.strip_comment('MERGE (n {u: "a//b"}) // t') == 'MERGE (n {u: "a//b"}) '
    assert loader.strip_comment("// whole line") == ""


# --------------------------------------------------------------------------
# what the catalogue actually holds — read from the cache, not asserted
# --------------------------------------------------------------------------

@needs_cache
def test_no_page_is_left_unclassified(catalogue):
    """The classifier was `if 1 … elif 2 … else pathway`, so a depth-0 or
    depth-4 page would have been read as a pathway and parsed for a course
    table it does not have. Counted now, not guessed at."""
    assert catalogue["unclassified"] == []


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
# --------------------------------------------------------------------------

def test_a_credit_value_is_normalised_like_a_section_title():
    """One went through `html.unescape` and whitespace collapsing and the other
    did not, for no reason anyone chose."""
    markup = section("First", "/a/one").replace(
        'field__item">1</span>', 'field__item">  1 &amp; a half\n</span>')
    got = reader.parse_pathway(markup, "https://catalog.pwcs.edu/p", PUBLISHED)
    assert got["courses"][0]["credits"] == "1 & a half"


# --------------------------------------------------------------------------
# classification, driven with synthetic pages so odd depths can exist
# --------------------------------------------------------------------------

def test_level_names_each_depth_and_refuses_to_guess():
    """It was an `if 1 … elif 2 … else pathway` inside `read()`, so the root
    and anything nested deeper than a pathway were swept into "pathway" and
    parsed for a course table they do not have."""
    assert reader.level("https://catalog.pwcs.edu/band") == "subject"
    assert reader.level("https://catalog.pwcs.edu/band/concert") == "course"
    assert reader.level("https://catalog.pwcs.edu/cte/career-pathways/it") == "pathway"
    assert reader.level("https://catalog.pwcs.edu") is None
    assert reader.level("https://catalog.pwcs.edu/a/b/c/d") is None


def titled(name: str) -> str:
    return f"<html><h1>{name}</h1></html>"


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
    assert pathway["dangling"] == ["/band"], pathway["dangling"]


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


def test_a_page_publishing_a_course_table_at_the_wrong_depth_is_reported():
    """Pages are classified by URL depth, and four in this catalogue publish a
    pathway course table at COURSE depth — so their rows are never read and
    172 published INCLUDES edges are never written. Raised as #87.

    Measured and reported rather than reclassified: reclassifying moves the
    node and edge totals three documents quote, which is its own change."""
    urls = ["https://catalog.pwcs.edu/specialty-programs",
            "https://catalog.pwcs.edu/specialty-programs/it-centre"]

    def fetch(url):
        if url.endswith("it-centre"):
            return titled("IT Centre") + section("Only", "/a/one")
        return titled("Specialty programs")

    got = reader.read(urls=urls, fetch=fetch)
    assert got["misfiled"] == ["https://catalog.pwcs.edu/specialty-programs/it-centre"]
    # And it is still loaded as a course, which is the point of reporting it.
    assert len(got["courses"]) == 1 and got["pathways"] == []


@needs_cache
def test_the_misfiled_count_is_the_one_the_loader_reports(catalogue):
    """The figure quoted in #87 and printed by the loader, read from the
    catalogue rather than typed."""
    assert len(catalogue["misfiled"]) == 4, catalogue["misfiled"]

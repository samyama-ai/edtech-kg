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
    same = (loader.requirement_id("https://a/x", "Teacher recommendation"),
            loader.requirement_id("https://a/x", "Teacher  recommendation\n"))
    assert same[0] == same[1], "whitespace should normalise, so a re-run MERGEs"


def test_two_districts_sharing_a_path_get_different_requirement_ids():
    """The defect 577975e fixed, asserted rather than remembered: the id was
    derived from the course PATH, and a path does not carry the district."""
    a = loader.requirement_id("https://one.edu/maths/algebra-1", "Teacher recommendation")
    b = loader.requirement_id("https://two.edu/maths/algebra-1", "Teacher recommendation")
    assert a != b


def test_an_href_becomes_the_absolute_url_the_key_is_built_on():
    assert loader.absolute("/art/1") == "https://catalog.pwcs.edu/art/1"
    assert loader.absolute("/art/1/") == "https://catalog.pwcs.edu/art/1", "trailing slash"
    assert loader.absolute("/art/1#top") == "https://catalog.pwcs.edu/art/1", "fragment"


def test_segments_counts_the_catalogue_levels():
    assert loader.segments("https://catalog.pwcs.edu/band") == ["band"]
    assert loader.segments("https://catalog.pwcs.edu/band/concert") == ["band", "concert"]


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
    got = loader.parse_pathway(markup, "https://catalog.pwcs.edu/p", PUBLISHED)
    assert len(got["courses"]) == 3, got["courses"]


def test_each_row_is_attributed_to_the_section_it_sits_under():
    markup = section("First", "/a/one") + section("Second", "/a/two")
    got = loader.parse_pathway(markup, "https://catalog.pwcs.edu/p", PUBLISHED)
    assert {c["url"].rsplit("/", 2)[-2] + "/" + c["url"].rsplit("/", 1)[-1]: c["section"]
            for c in got["courses"]} == {"a/one": "First", "a/two": "Second"}


def test_a_row_before_any_section_title_has_no_section():
    got = loader.parse_pathway(
        f'<div class="field field--name-field-degree-section-courses">{row("/a/one")}</div>',
        "https://catalog.pwcs.edu/p", PUBLISHED)
    assert got["courses"][0]["section"] is None


def test_a_section_title_is_unescaped():
    markup = section("Journalism &amp; Broadcasting", "/a/one")
    got = loader.parse_pathway(markup, "https://catalog.pwcs.edu/p", PUBLISHED)
    assert got["courses"][0]["section"] == "Journalism & Broadcasting"


def test_a_row_pointing_outside_the_sitemap_is_reported_not_dropped():
    """Five of 202 real rows point at a Drupal node id with no published alias.
    Counting them as absent would understate what the district publishes."""
    markup = section("First", "/a/one", "/node/1435")
    got = loader.parse_pathway(markup, "https://catalog.pwcs.edu/p", PUBLISHED)
    assert len(got["courses"]) == 1
    assert got["dangling"] == ["/node/1435"]


def test_a_rendered_field_with_no_rows_is_a_parse_failure_not_an_empty_pathway():
    """The same distinction the probe draws for the prerequisite field: the
    field would not be rendered at all if there were nothing in it."""
    markup = '<div class="field field--name-field-degree-section-courses"></div>'
    got = loader.parse_pathway(markup, "https://catalog.pwcs.edu/p", PUBLISHED)
    assert got["field_present_no_rows"] is True


def test_a_pathway_with_no_such_field_is_not_a_parse_failure():
    got = loader.parse_pathway("<html></html>", "https://catalog.pwcs.edu/p", PUBLISHED)
    assert got["field_present_no_rows"] is False
    assert got["courses"] == []


# --------------------------------------------------------------------------
# what the catalogue actually holds — read from the cache, not asserted
# --------------------------------------------------------------------------

@needs_cache
def test_the_three_levels_account_for_every_sitemap_page():
    """795 courses, 127 subjects, 38 pathways. The probe reports all 960 as
    courses (#74); the split has to add up or one of the three is wrong."""
    data = loader.read()
    total = len(data["subjects"]) + len(data["courses"]) + len(data["pathways"])
    assert total == len(data["urls"]), (
        f"{len(data['urls'])} pages in the sitemap, {total} classified")
    # The invariant, not the census. Asserting 127/795/38 fails the day the
    # district publishes one more course — which is not a defect, and a test
    # that cries about it teaches people to ignore it. What must hold is that
    # every page lands in exactly one bucket and none is left unclassified.
    assert data["unclassified"] == [], data["unclassified"]
    assert data["courses"], "no courses classified at all"


@needs_cache
def test_no_prerequisite_crosses_out_of_the_course_level():
    """The claim #74 rests on: reclassifying 165 pages does not touch the 240
    edges, because no page outside the 795 is at either end of one."""
    data = loader.read()
    for record in data["subjects"] + data["pathways"]:
        assert not record["prerequisite_links"], record["url"]
    depths = {len(loader.segments(link["href"]))
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


@needs_cache
def test_no_page_is_left_unclassified():
    """The classifier was `if 1 … elif 2 … else pathway`, so a depth-0 or
    depth-4 page would have been read as a pathway and parsed for a course
    table it does not have. Counted now, not guessed at."""
    assert reader.read()["unclassified"] == []


def test_the_normalisation_rule_names_every_url_keyed_label():
    """Course, Subject and Pathway are all keyed on the address of a published
    page, and the rule that says how that address is spelled has to cover all
    three or it covers none of them."""
    text = (Path(__file__).resolve().parents[1]
            / "schema" / "edtech_kg.cypher").read_text()
    rule = text[text.index("NORMALISATION"):text.index("CREATE CONSTRAINT ON (c:Course)")]
    for label in ("Subject.url", "Pathway.url"):
        assert label in rule, f"the normalisation rule does not mention {label}"



def test_a_credit_value_is_normalised_like_a_section_title():
    """One went through `html.unescape` and whitespace collapsing and the other
    did not, for no reason anyone chose."""
    markup = section("First", "/a/one").replace(
        'field__item">1</span>', 'field__item">  1 &amp; a half\n</span>')
    got = loader.parse_pathway(markup, "https://catalog.pwcs.edu/p", PUBLISHED)
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

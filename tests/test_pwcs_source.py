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
        urls = source.catalogue_urls(True)
    except Exception:                      # noqa: BLE001 — no cached sitemap
        return False
    return bool(urls) and all(source.cached_path(u).exists() for u in urls)


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


needs_cache = pytest.mark.skipif(
    not cache_is_complete(),
    reason=("the cached catalogue is incomplete — run `python -m etl.probe_pwcs` "
            "first; a partial cache would fetch the remainder from the district"))


@pytest.fixture(scope="module")
def catalogue():
    """One `read()` for every test that needs the real catalogue.

    It walks ~960 cached pages and re-parses each one. Three tests called it
    independently, so the cache was read three times over to answer three
    questions about the same result.
    """
    return reader.read()


@needs_cache
def test_the_three_levels_account_for_every_sitemap_page(catalogue):
    """791 courses, 127 subjects, 42 pathways. The split has to add up or one
    of the three is wrong — and the probe now classifies the same way (#74),
    so a drift here is a drift between the reader and the console too.

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
    # Both schema files. Naming one is how a guard survives the sentence it
    # guards moving to the other (#157).
    text = "\n".join(
        f.read_text(encoding="utf-8")
        for f in sorted((Path(__file__).resolve().parents[1] / "schema")
                        .glob("*.cypher")))
    # `str.index` raises ValueError naming a substring, from which nobody can
    # tell that a heading was renamed. `find` and an assertion say it.
    start, end = text.find("NORMALISATION"), text.find("CREATE CONSTRAINT ON (c:Course)")
    assert start != -1, "the schema no longer states a NORMALISATION rule"
    assert end > start, "the Course constraint no longer follows the rule"
    rule = text[start:end]
    for label in ("Subject.url", "Pathway.url"):
        assert label in rule, f"the normalisation rule does not mention {label}"


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

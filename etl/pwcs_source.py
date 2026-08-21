"""Reading one district's published catalogue.

Parsing only — nothing here talks to an engine. `etl/probe_pwcs.py` measures the
catalogue and caches its pages; this turns those pages into the three things the
schema declares, and `etl/load_pwcs.py` writes them.

**Nothing is scraped from prose.** Every edge comes from a Drupal *entity
reference* — a typed link to another page on the same site — so an edge either
lands on a published page or provably does not.

What the sitemap holds, by path depth — the catalogue's own structure:

    /band                                       127  Subject
    /band/concert-band                          791  Course
    /career-and-technical-education-cte/...       38  Pathway

**The probe reports all 960 as courses. They are not.** No page at depth 1 or 3
states a prerequisite and no prerequisite points at one, so the 240 edges are
unaffected — but the rate is 229 of 795, not 229 of 960. Raised as #74.
"""

from __future__ import annotations

import bisect
import hashlib
import html
import re
import urllib.parse

from etl import probe_pwcs as source

# A pathway page lists its courses in a typed field, exactly as a course page
# lists its prerequisites — entity references, each carrying a credit value.
#
# One course row. `<article about="…" class="… degree-row …">` is markup the
# CMS emits only for a course inside a programme's course table, which is why
# the rows are matched directly rather than by bounding the enclosing field.
# The first version did bound the field, with a lookahead terminator, and found
# 71 of 218 rows: a pathway publishes SEVERAL course lists, one per named
# section, and the bound stopped at the first. A partial parse that returns
# plausible numbers is the failure mode this repo keeps hitting, so the rows are
# now read wherever the CMS types them.
# The ROW, and the credits looked for INSIDE it — not one pattern requiring
# both. Requiring the credits field meant a `degree-row` article without one
# matched nothing at all: not counted in `rows`, not in `courses`, not in
# `dangling`. A published course simply disappeared, and the pathway's own
# total was the only place it could have shown.
COURSE_ROW = re.compile(
    r'<article about="([^"]+)"[^>]*class="[^"]*degree-row[^"]*".*?</article>',
    re.S)
ROW_CREDITS = re.compile(r'field--name-field-credits[^>]*>([^<]*)<', re.S)

# Each course list sits under a named section — "Construction Pathway",
# "Design / Pre-Construction Pathway". That is the district's own grouping and
# it goes on the edge, so a pathway with two routes through it is not flattened
# into one undifferentiated bag of courses.
#
# Regex over markup, like COURSE_ROW: there is no published API for this
# catalogue, and a CMS template change makes either pattern match nothing. For
# the rows that is caught — PATHWAY_FIELD_PRESENT below separates "no rows" from
# "the field did not render". A section title has no such tell, so a template
# change here degrades quietly to every row carrying `section: None` rather than
# failing. `parse_pathway` counts the rows it attributed to no section for that
# reason: the number is on the page rather than in nobody's notice.
SECTION_TITLE = re.compile(
    r'field--name-field-degree-section-title[^>]*>([^<]*)<', re.S)

# A pathway page that renders the field but yields no rows is a parse failure,
# not a pathway with no courses — the same distinction the probe draws for the
# prerequisite field. Counting it as empty would understate the graph silently.
PATHWAY_FIELD_PRESENT = re.compile(r'field--name-field-degree-section-courses')


def segments(url: str) -> list[str]:
    return [s for s in urllib.parse.urlparse(url).path.strip("/").split("/") if s]


def absolute(href: str) -> str:
    """A catalogue-relative href as the absolute URL the key is built on.

    Course is keyed on the ABSOLUTE url, not the path — the path does not carry
    the district, and `/mathematics/algebra-1` is a path two districts can both
    publish (schema/edtech_kg.cypher). Resolution stays by path, as the probe
    does it, because that is what the sitemap comparison needs; only the key is
    absolute.

    The normalisation is the one the schema writes down: fragment dropped,
    QUERY DROPPED, trailing slash removed. The query was kept, so a href
    carrying `?utm_source=x` produced a second key for a page already loaded —
    and a constraint in 1.1.0 declares the key without enforcing it, so nothing
    would have caught the duplicate. No href in this catalogue has a query
    today, which is the only reason it never fired.

    `rstrip("/")` on a root href gave `https://catalog.pwcs.edu` with no path
    at all — a different string from the sitemap's, so the MATCH finds nothing
    and the edge is silently not written. The slash is only stripped when
    something is left underneath it.
    """
    # Joined against the site ROOT, not the sitemap's own URL. `urljoin` with
    # `SITEMAP` as the base resolves a document-relative href — "algebra-1",
    # no leading slash — against the sitemap's DIRECTORY, which is not where
    # catalogue pages live. Every href in this catalogue is root-relative
    # today, which is the only reason it never showed.
    root = urllib.parse.urlunparse(
        urllib.parse.urlparse(source.SITEMAP)._replace(
            path="/", params="", query="", fragment=""))
    parsed = urllib.parse.urlparse(urllib.parse.urljoin(root, href))
    path = parsed.path.rstrip("/") or "/"
    return urllib.parse.urlunparse(
        (parsed.scheme, parsed.netloc, path, "", "", ""))


def parse_pathway(markup: str, url: str, published: set[str]) -> dict:
    """The courses a CTE pathway is made of, as the district publishes them.

    Typed entity references with a credit value each — the same shape as the
    prerequisite field, not prose and not navigation. Rows whose target is not
    in the sitemap are reported, never silently dropped.
    """
    # Sections in document order, so each row can be attributed to the section
    # it appears under. A row before the first section title has none.
    marks = [(m.start(), " ".join(html.unescape(m.group(1)).split()))
             for m in SECTION_TITLE.finditer(markup)]
    starts = [start for start, _ in marks]

    def section_at(position: int) -> str | None:
        """Which section title precedes this position.

        `bisect`, not a re-scan. This walked the whole `marks` list per row and
        was called twice per row, so a pathway with many sections cost
        rows x sections x 2 — pointless on a list that is already in document
        order.
        """
        # `bisect_right`, not `bisect_left`: a row whose offset EQUALS a title
        # offset belongs to that title, and `bisect_left` gave it the previous
        # one — or None. The two offsets cannot collide in today's markup, since
        # the title element precedes the row it heads, so this is a latent
        # off-by-one rather than an observed fault.
        index = bisect.bisect_right(starts, position)
        return marks[index - 1][1] if index else None

    courses, dangling, rows, unsectioned, uncredited = [], [], 0, 0, 0
    for match in re.finditer(COURSE_ROW, markup):
        rows += 1
        href = match.group(1)
        found = ROW_CREDITS.search(match.group(0))
        if found is None:
            # Counted, not dropped. The district publishes the course either
            # way; only the credit value is missing.
            uncredited += 1
        credits = found.group(1) if found else None
        path = source.path_of(href)
        # Counted for EVERY row, resolving or not. It was computed inside the
        # resolving branch, so a template change that broke section titles on a
        # page whose rows mostly dangle would have shown a small number and
        # read as fine.
        if section_at(match.start()) is None:
            unsectioned += 1
        if path in published:
            courses.append({"url": absolute(href),
                            # Same treatment as the section title: unescaped
                            # and whitespace-collapsed. One went through
                            # html.unescape and the other did not, for no
                            # reason anyone chose.
                            "credits": (" ".join(html.unescape(credits).split())
                                        or None) if credits is not None else None,
                            "section": section_at(match.start())})
        else:
            # The SAME representation as `courses`. `dangling` held the raw
            # href while `courses` held the absolute URL, so the two lists
            # could not be compared, and a caller reading both got two
            # spellings of one catalogue.
            dangling.append(absolute(href))
    return {
        "url": url,
        "courses": courses,
        "dangling": dangling,
        # Field rendered, nothing extracted — reported, never read as absence.
        "field_present_no_rows": bool(PATHWAY_FIELD_PRESENT.search(markup)) and not rows,
        # Rows that sit under no section title. A CMS template change to
        # SECTION_TITLE has no other tell; this is it.
        "rows_without_a_section": unsectioned,
        # Rows the district published with no credit value. Zero today.
        "rows_without_credits": uncredited,
    }


LEVELS = {1: "subject", 2: "course", 3: "pathway"}


def level(url: str) -> str | None:
    """What the catalogue's URL DEPTH says a page is. `None` for anything else
    — the root, or something nested deeper than a pathway.

    A function so it can be checked directly. It was an `if/elif/else` inside
    `read()`, and the `else` swept every unexpected depth into "pathway",
    where it would be parsed for a course table it does not have.

    **Depth alone is not the classifier — see `classify`.** Four pages publish
    a pathway's course table at course depth, and calling them courses cost
    172 published edges (#87).
    """
    return LEVELS.get(len(segments(url)))


def classify(url: str, markup: str) -> str | None:
    """What a page IS, from what it publishes and then from its depth.

    Depth is the catalogue's own structure and it holds for 956 of 960 pages.
    It does not hold for four, which publish the pathway course-table field at
    COURSE depth — two specialty programmes, International Baccalaureate and
    Virtual Prince William. Classified by depth they loaded as `Course`, their
    course tables were never read, and 172 published rows never became edges
    (#87). Nothing failed: the loader and the engine agreed about a set that
    was already short.

    So the field wins over the depth. A page that renders a course table IS a
    pathway whatever its URL says — the district's own markup is the better
    evidence, and it is the evidence the rows come from.

    Depth still decides everything else, because a subject index and a course
    are not distinguishable by any field either of them carries.
    """
    if PATHWAY_FIELD_PRESENT.search(markup):
        return "pathway"
    return level(url)


def read(use_cache: bool = True, urls: list[str] | None = None,
         fetch=None) -> dict:
    """Every page in the sitemap, split by what the catalogue says it is.

    Depth 1 is a subject index, 2 a course, 3 a CTE pathway. **Anything else is
    counted, not guessed at.** The classifier was `if 1 … elif 2 … else
    pathway`, so a depth-0 page — the catalogue root — or a depth-4 page would
    have been read as a pathway and parsed for a course table it does not have.
    Neither exists today (measured: 127 subjects, 791 courses, 42 pathways),
    which is the only reason a bare `else` looked harmless.

    A pathway's course rows resolve against the COURSE paths, not against every
    published page. `published` includes subject and pathway pages, so a row
    pointing at one of those counted as resolved and then wrote no edge — the
    count and the graph would disagree with nothing to say why. Zero rows do
    that today; it is a property of this catalogue, not of the parser.

    **Depth is not a reliable classifier, and this now measures by how much.**
    `unparsed` counts sitemap pages that returned no record — it was a bare
    `continue`, so a CMS change breaking `parse_course` would shrink the graph
    with nothing said. `misfiled` counts pages classified as something other
    than a pathway that nonetheless render the pathway course-table field:
    4 today, holding 172 resolvable rows that are therefore never written as
    INCLUDES edges. Raised as #87. Reported rather than reclassified here,
    because reclassifying changes the node and edge totals three documents
    quote and that is its own change, not a review fix.
    """
    urls = source.course_urls(use_cache) if urls is None else urls
    fetch = fetch or (lambda u: source.fetch(u, use_cache))
    published = {source.path_of(u) for u in urls} - {None}

    # TWO passes, because the course set is now an OUTPUT of classification
    # rather than an input to it. It used to be derived from URL depth before
    # the loop, which is the same assumption `classify` exists to correct — so
    # deriving it that way would have left pathway rows resolving against a
    # course set that includes four pages no longer classified as courses.
    buckets = {"subject": [], "course": [], "pathway": []}
    unclassified, unparsed, reclassified = [], [], []
    pathway_markup = {}
    for url in urls:
        markup = fetch(url)
        record = source.parse_course(markup, url)
        if record is None:
            # Counted, not dropped. A page with no `<h1>`, or one titled "Page
            # not found", returns None — and so would every page the day the
            # CMS renames its heading class.
            unparsed.append(url)
            continue
        kind = classify(url, markup)
        if kind != level(url):
            # What the depth would have said, and what the markup says
            # instead. Reported so the disagreement stays visible rather than
            # being silently resolved — it is how #87 was found.
            reclassified.append(url)
        if kind is None:
            unclassified.append(url)
            continue
        if kind == "pathway":
            pathway_markup[url] = markup
        buckets[kind].append(record)

    course_paths = {source.path_of(r["url"]) for r in buckets["course"]} - {None}
    for record in buckets["pathway"]:
        # Resolved against the COURSE paths, not every published page: a row
        # pointing at a subject or pathway page would otherwise count as
        # resolved and then write no edge.
        record.update(parse_pathway(pathway_markup[record["url"]],
                                    record["url"], course_paths))
    subjects, courses, pathways = (buckets["subject"], buckets["course"],
                                   buckets["pathway"])
    return {"urls": urls, "published": published, "course_paths": course_paths,
            "subjects": subjects, "courses": courses, "pathways": pathways,
            "unclassified": unclassified, "unparsed": unparsed,
            "reclassified": reclassified}


def requirement_id(course_url: str, text: str) -> str:
    """sha1("<course URL>|<normalised text>"), per the schema.

    The course URL and not its path: the key of a dependent node has to be at
    least as specific as the key of the node it depends on, or "Teacher
    recommendation" collides between two districts publishing the same path.
    """
    normalised = " ".join(text.split())
    return hashlib.sha1(f"{course_url}|{normalised}".encode()).hexdigest()

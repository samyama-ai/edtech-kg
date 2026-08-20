"""Reading one district's published catalogue.

Parsing only — nothing here talks to an engine. `etl/probe_pwcs.py` measures the
catalogue and caches its pages; this turns those pages into the three things the
schema declares, and `etl/load_pwcs.py` writes them.

**Nothing is scraped from prose.** Every edge comes from a Drupal *entity
reference* — a typed link to another page on the same site — so an edge either
lands on a published page or provably does not.

What the sitemap holds, by path depth — the catalogue's own structure:

    /band                                       127  Subject
    /band/concert-band                          795  Course
    /career-and-technical-education-cte/...       38  Pathway

**The probe reports all 960 as courses. They are not.** No page at depth 1 or 3
states a prerequisite and no prerequisite points at one, so the 240 edges are
unaffected — but the rate is 229 of 795, not 229 of 960. Raised as #74.
"""

from __future__ import annotations

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
COURSE_ROW = re.compile(
    r'<article about="([^"]+)"[^>]*class="[^"]*degree-row[^"]*"'
    r'(?:(?!</article>).)*?'
    r'field--name-field-credits[^>]*>([^<]*)<', re.S)

# Each course list sits under a named section — "Construction Pathway",
# "Design / Pre-Construction Pathway". That is the district's own grouping and
# it goes on the edge, so a pathway with two routes through it is not flattened
# into one undifferentiated bag of courses.
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
    """
    return urllib.parse.urljoin(source.SITEMAP, href).split("#")[0].rstrip("/")


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

    def section_at(position: int) -> str | None:
        name = None
        for start, title in marks:
            if start < position:
                name = title
            else:
                break
        return name

    courses, dangling, rows = [], [], 0
    for match in re.finditer(COURSE_ROW, markup):
        rows += 1
        href, credits = match.group(1), match.group(2)
        path = source.path_of(href)
        if path in published:
            courses.append({"url": absolute(href),
                            # Same treatment as the section title: unescaped
                            # and whitespace-collapsed. One went through
                            # html.unescape and the other did not, for no
                            # reason anyone chose.
                            "credits": " ".join(html.unescape(credits).split()) or None,
                            "section": section_at(match.start())})
        else:
            dangling.append(href)
    return {
        "url": url,
        "courses": courses,
        "dangling": dangling,
        # Field rendered, nothing extracted — reported, never read as absence.
        "field_present_no_rows": bool(PATHWAY_FIELD_PRESENT.search(markup)) and not rows,
    }


def read(use_cache: bool = True) -> dict:
    """Every page in the sitemap, split by what the catalogue says it is."""
    urls = source.course_urls(use_cache)
    published = {source.path_of(u) for u in urls} - {None}

    subjects, courses, pathways = [], [], []
    for url in urls:
        markup = source.fetch(url, use_cache)
        record = source.parse_course(markup, url)
        if record is None:
            continue
        depth = len(segments(url))
        if depth == 1:
            subjects.append(record)
        elif depth == 2:
            courses.append(record)
        else:
            record.update(parse_pathway(markup, url, published))
            pathways.append(record)
    return {"urls": urls, "published": published, "subjects": subjects,
            "courses": courses, "pathways": pathways}


def requirement_id(course_url: str, text: str) -> str:
    """sha1("<course URL>|<normalised text>"), per the schema.

    The course URL and not its path: the key of a dependent node has to be at
    least as specific as the key of the node it depends on, or "Teacher
    recommendation" collides between two districts publishing the same path.
    """
    normalised = " ".join(text.split())
    return hashlib.sha1(f"{course_url}|{normalised}".encode()).hexdigest()

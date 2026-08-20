"""Load one district's published catalogue into the graph.

    python -m etl.load_pwcs --url http://localhost:8200 --graph edtech

Prince William County Schools publishes `catalog.pwcs.edu` on Clean Catalog, a
Drupal product. `etl/probe_pwcs.py` measured what is in it; this loads it.

**Nothing here is scraped from prose.** Every edge below is published by the
district as a Drupal *entity reference* — a typed link to another page on the
same site — so an edge either lands on a published page or provably does not.
That is the property `docs/sources/course-prerequisites.md` measured at 240 of
240, and it is why this catalogue loads cleanly where the Credential Registry
did not (#53: 0 of 150 prerequisite strings resolve).

What the sitemap holds, by path depth — the catalogue's own structure:

    /band                                       127  Subject
    /band/concert-band                          795  Course
    /career-and-technical-education-cte/...       38  Pathway

**The probe reports all 960 as courses. They are not.** 127 are subject index
pages and 38 are CTE pathway pages; 795 are courses. No page at depth 1 or 3
states a prerequisite and no prerequisite points at one, so the 240 edges are
unaffected — but the rate they are quoted against is 229 of 795, not 229 of 960.
Raised as #74; this loader states both figures rather than quietly picking one.

The engine takes no query parameters in 1.1.0, so values are inlined. `lit()` is
the whole of the defence and is used for every value without exception.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from etl import probe_pwcs as source

DEFAULT_URL = "http://localhost:8200"
SCHEMA = Path(__file__).resolve().parent.parent / "schema" / "edtech_kg.cypher"

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


# --------------------------------------------------------------------------
# Engine
# --------------------------------------------------------------------------

class Engine:
    def __init__(self, url: str, graph: str = "default") -> None:
        self.url = url.rstrip("/")
        self.graph = graph
        self.statements = 0
        self.retries = 0

    def run(self, query: str, attempts: int = 4) -> dict:
        payload = json.dumps({"query": query, "graph": self.graph}).encode()
        result = None
        for attempt in range(attempts):
            request = urllib.request.Request(
                f"{self.url}/api/query", data=payload,
                headers={"Content-Type": "application/json"})
            try:
                result = json.loads(urllib.request.urlopen(request, timeout=120).read())
                break
            except urllib.error.HTTPError as exc:
                body = exc.read().decode()[:300]
                # 4xx will fail identically every time; retrying only delays
                # the report. Transient 5xx are worth another go.
                if exc.code in (429, 500, 502, 503, 504) and attempt < attempts - 1:
                    self.retries += 1
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError(f"{exc.code} on: {query[:160]}\n{body}") from exc
            except (urllib.error.URLError, OSError, TimeoutError,
                    json.JSONDecodeError) as exc:
                if attempt < attempts - 1:
                    self.retries += 1
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError(f"unreachable on: {query[:160]}\n{exc}") from exc
        # The engine answers 200 with an `error` key for a parse failure, so a
        # rejected statement is not an HTTP error and would otherwise pass.
        if result is None or "error" in result:
            raise RuntimeError(f"{(result or {}).get('error', 'no response')}\n"
                               f"  on: {query[:160]}")
        self.statements += 1
        return result

    def scalar(self, query: str):
        records = self.run(query)["records"]
        return records[0][0] if records and records[0] else None


def upsert(engine: Engine, label: str, key: str, value: str, props: dict) -> None:
    """MERGE the key, then SET the rest — two statements, deliberately.

    **`MERGE (n:L {k: v}) SET n.p = x` does not parse in 1.1.0.** The parser
    accepts `ON CREATE SET` and `ON MATCH SET` after a MERGE but not a bare
    SET, which is a Cypher form every other implementation takes. Raised as #75.

    `ON CREATE SET` alone would be one statement and is the obvious workaround —
    but it fires only on insert, so re-running after the district renames a
    course leaves the old name in the graph with nothing to show for it. A
    separate MATCH … SET always refreshes, which is what a re-runnable loader
    has to do.
    """
    engine.run(f"MERGE (n:{label} {{{key}: {lit(value)}}})")
    if props:
        assignments = ", ".join(f"n.{name} = {lit(v)}" for name, v in props.items())
        engine.run(f"MATCH (n:{label} {{{key}: {lit(value)}}}) SET {assignments}")


class Unquotable(Exception):
    """A value 1.1.0 has no way to express as a string literal."""


def lit(value) -> str:
    """A Cypher literal. 1.1.0 takes no parameters, so this is the defence.

    **1.1.0 supports no escape sequence inside a string literal.** Measured
    against the engine, all three of these are parse errors:

        'Governor\\'s'      backslash escape
        'Governor''s'       doubled quote, the SQL form
        "say \\"hi\\""       backslash escape in a double-quoted string

    A backslash is not an escape character at all; it is stored as itself. So
    the quote character is the only thing that ends a literal, and the only way
    to carry one is to wrap the value in the *other* quote. Raised as #76.

    That leaves one value this engine cannot express: a string containing both
    an apostrophe and a double quote. It raises rather than mangling, because
    the alternative is a course silently loaded under a different name than the
    district published — and nothing downstream would show it.

    `regulatory-affairs-kg/etl/cypher.py` reached the same conclusion against
    the same engine and selects the quote per value too — worth knowing that two
    independent measurements agree. Its MCP server does not: `quoted()` escapes
    with backslashes, so every tool call carrying an apostrophe is a statement
    the engine rejects. Raised there as #24.
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if "'" not in text:
        return f"'{text}'"
    if '"' not in text:
        return f'"{text}"'
    raise Unquotable(
        f"1.1.0 cannot express a string holding both quote characters, and "
        f"there is no escape sequence to fall back on: {text[:120]!r}")


# --------------------------------------------------------------------------
# Reading the catalogue
# --------------------------------------------------------------------------

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
                            "credits": credits.strip() or None,
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


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------

DISTRICT = "Prince William County Schools"
CATALOGUE = "catalog.pwcs.edu"


def load(engine: Engine, data: dict, quiet: bool = False) -> dict:
    """Every write is a MERGE.

    A constraint in 1.1.0 declares the key; it does not reject a duplicate
    CREATE (schema/edtech_kg.cypher). So re-running this must converge, and
    only MERGE gives that.
    """
    def say(message: str) -> None:
        if not quiet:
            print(message, flush=True)

    published = data["published"]
    by_path = {source.path_of(r["url"]): r["url"]
               for r in data["subjects"] + data["courses"] + data["pathways"]}

    say(f"  subjects   {len(data['subjects']):>5,}")
    for record in data["subjects"]:
        upsert(engine, "Subject", "url", record["url"],
               {"name": record["title"], "district": DISTRICT, "source": CATALOGUE})

    say(f"  courses    {len(data['courses']):>5,}")
    for record in data["courses"]:
        upsert(engine, "Course", "url", record["url"],
               {"name": record["title"], "district": DISTRICT, "source": CATALOGUE})

    say(f"  pathways   {len(data['pathways']):>5,}")
    for record in data["pathways"]:
        kind = ("career pathway" if "career-pathways" in record["url"]
                else "specialty program")
        upsert(engine, "Pathway", "url", record["url"],
               {"name": record["title"], "kind": kind,
                "district": DISTRICT, "source": CATALOGUE})

    # Course -> Subject, from the catalogue's own URL hierarchy. The parent path
    # is the subject page; a course whose parent is not published is left
    # unattached rather than attached to something invented.
    in_subject = 0
    for record in data["courses"]:
        parent = "/" + segments(record["url"])[0]
        if parent not in published:
            continue
        engine.run(
            f"MATCH (c:Course {{url: {lit(record['url'])}}}), "
            f"(s:Subject {{url: {lit(by_path[parent])}}}) MERGE (c)-[:IN_SUBJECT]->(s)")
        in_subject += 1
    say(f"  IN_SUBJECT {in_subject:>5,}")

    # Course -> Course. The edge this graph exists for.
    requires = 0
    for record in data["courses"]:
        for link in record["prerequisite_links"]:
            path = source.path_of(link["href"])
            if path not in published:
                continue        # measured at zero; never assumed to be zero
            engine.run(
                f"MATCH (a:Course {{url: {lit(record['url'])}}}), "
                f"(b:Course {{url: {lit(by_path[path])}}}) "
                f"MERGE (a)-[:REQUIRES]->(b)")
            requires += 1
    say(f"  REQUIRES   {requires:>5,}")

    # The condition that is NOT a course reference. A node, not an edge — see
    # the schema: asserting a REQUIRES to a course that was never named would
    # invent a link the source does not make.
    requirements = 0
    for record in data["courses"] + data["pathways"] + data["subjects"]:
        text = record.get("requirements_text")
        if not text:
            continue
        label = "Course" if len(segments(record["url"])) == 2 else "Pathway"
        if label == "Pathway" and len(segments(record["url"])) == 1:
            continue
        upsert(engine, "Requirement", "id", requirement_id(record["url"], text),
               {"text": " ".join(text.split()), "source": CATALOGUE})
        engine.run(
            f"MATCH (n:{label} {{url: {lit(record['url'])}}}), "
            f"(r:Requirement {{id: {lit(requirement_id(record['url'], text))}}}) "
            f"MERGE (n)-[:HAS_REQUIREMENT]->(r)")
        requirements += 1
    say(f"  HAS_REQ    {requirements:>5,}")

    # Pathway -> Course, with the section and the credit value the district
    # publishes.
    #
    # **An edge MERGE in 1.1.0 ignores the property map.** `MERGE (a)-[e:R
    # {s:'one'}]->(b)` followed by the same with `{s:'two'}` leaves ONE edge,
    # holding 'one'; the pattern matches on start, type and end alone. So two
    # edges between the same pathway and course cannot be told apart, and a
    # loader that MERGEs per row loses the second silently, with no error and
    # no trace in the counts. Raised as #77.
    #
    # 17 of the 202 published rows are a course appearing in two named sections
    # of the same pathway — a real fact about the catalogue, not a duplicate.
    # Rather than write 202 statements and let 17 disappear, the rows are
    # grouped here and the sections joined onto the one edge the engine can
    # hold. The collapse is counted and reported, so the number that vanished
    # is on the page rather than in the difference between two other numbers.
    grouped: dict[tuple[str, str], dict] = {}
    for record in data["pathways"]:
        for course in record["courses"]:
            entry = grouped.setdefault((record["url"], course["url"]),
                                       {"sections": [], "credits": course["credits"]})
            if course["section"] and course["section"] not in entry["sections"]:
                entry["sections"].append(course["section"])
    collapsed = sum(len(e["sections"]) - 1 for e in grouped.values()
                    if len(e["sections"]) > 1)

    includes = 0
    for (pathway, course), entry in grouped.items():
        engine.run(
            f"MATCH (p:Pathway {{url: {lit(pathway)}}}), "
            f"(c:Course {{url: {lit(course)}}}) "
            f"MERGE (p)-[e:INCLUDES]->(c)")
        engine.run(
            f"MATCH (:Pathway {{url: {lit(pathway)}}})-[e:INCLUDES]->"
            f"(:Course {{url: {lit(course)}}}) "
            f"SET e.section = {lit(' | '.join(entry['sections']) or None)}, "
            f"e.sections = {lit(len(entry['sections']))}, "
            f"e.credits = {lit(entry['credits'])}")
        includes += 1
    if collapsed:
        say(f"  {collapsed} published rows are a course in a second section of the "
            f"same pathway; the engine holds one edge per pair, so the section "
            f"names are joined onto it")
    say(f"  INCLUDES   {includes:>5,}")

    return {"subjects": len(data["subjects"]), "courses": len(data["courses"]),
            "pathways": len(data["pathways"]), "in_subject": in_subject,
            "requires": requires, "requirements": requirements,
            "includes": includes, "rows_collapsed_into_an_edge": collapsed,
            "pathway_rows_published": sum(len(p["courses"]) for p in data["pathways"]),
            "pathway_rows_unresolvable": sum(len(p["dangling"]) for p in data["pathways"])}


def apply_schema(engine: Engine, quiet: bool = False) -> int:
    """The constraints, from the schema file — not retyped here.

    A copy would drift from the file the tests execute, which is the defect
    this repo keeps finding: two things that should be one, with only one
    maintained.
    """
    text = SCHEMA.read_text()
    statements = [s.strip() for s in
                  "\n".join(line.split("//")[0] for line in text.splitlines()).split(";")
                  if s.strip()]
    for statement in statements:
        engine.run(statement)
    if not quiet:
        print(f"  schema     {len(statements):>5,} statements")
    return len(statements)


def verify(engine: Engine, loaded: dict) -> list[str]:
    """Does the graph hold what the loader says it wrote?

    Counted from the engine, not from the loader's own tallies — a loader that
    reports what it *intended* to write is the one failure this cannot catch
    by itself.
    """
    problems = []
    for label, expected in (("Subject", loaded["subjects"]),
                            ("Course", loaded["courses"]),
                            ("Pathway", loaded["pathways"])):
        got = engine.scalar(f"MATCH (n:{label}) RETURN count(n)")
        if got != expected:
            problems.append(f"{label}: loader wrote {expected:,}, engine holds {got:,}")
    for edge, expected in (("REQUIRES", loaded["requires"]),
                           ("IN_SUBJECT", loaded["in_subject"]),
                           ("INCLUDES", loaded["includes"]),
                           ("HAS_REQUIREMENT", loaded["requirements"])):
        got = engine.scalar(f"MATCH ()-[e:{edge}]->() RETURN count(e)")
        if got != expected:
            problems.append(f"{edge}: loader wrote {expected:,}, engine holds {got:,}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--graph", default="edtech")
    parser.add_argument("--live", action="store_true",
                        help="Re-fetch from the district rather than the cache.")
    parser.add_argument("--reset", action="store_true",
                        help="Delete this district's nodes before loading.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    engine = Engine(args.url, args.graph)
    started = time.time()
    quiet = args.json

    if not quiet:
        print(f"\nLoading {DISTRICT} — {CATALOGUE}\n")

    data = read(use_cache=not args.live)
    if not quiet:
        print(f"  read       {len(data['urls']):>5,} pages from the sitemap")

    if args.reset:
        engine.run(f"MATCH (n) WHERE n.source = {lit(CATALOGUE)} DETACH DELETE n")

    apply_schema(engine, quiet)
    loaded = load(engine, data, quiet)

    problems = verify(engine, loaded)
    elapsed = time.time() - started
    result = {"district": DISTRICT, "source": CATALOGUE, **loaded,
              "statements": engine.statements, "retries": engine.retries,
              "elapsed_seconds": round(elapsed, 1), "problems": problems}

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"\n  {engine.statements:,} statements in {elapsed:.1f}s")
        if problems:
            print("\n  MISMATCH between what was written and what the engine holds:")
            for problem in problems:
                print(f"    {problem}")
        else:
            print("  verified — every count read back from the engine\n")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())

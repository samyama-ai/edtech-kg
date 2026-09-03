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

Those are DEPTHS, and they sum to 960. The loaded classification is 127
subjects, 791 courses and 42 pathways, which also sums to 960 — four pages move
from Course to Pathway because their markup says so.

See `pwcs_pages.classify`.

**The probe classifies before it counts** (#74). It quotes its prerequisite
rate against the 791 courses, the same denominator this loader writes, so the
console and the graph now agree. The 240 edges were never affected either way:
no page at depth 1 or 3 states a prerequisite and no prerequisite points at
one.

Reading the catalogue is `etl/pwcs_source.py`; talking to the engine is
`etl/engine.py`. Split out when this file reached 616 lines — over the size
review will read, so it went unexamined. What is left here is the writing:
which statements, in what order, and the read-back that checks they landed.
"""

from __future__ import annotations

import argparse
import json
import time

from etl.cypher_script import apply_schema
from etl.engine import Engine, Unquotable, lit, upsert
from etl.pwcs_edges import pathway_edges, prerequisite_pairs
from etl.pwcs_pages import markers_in
from etl.pwcs_source import read, requirement_id, segments
from etl import probe_pwcs as source

DEFAULT_URL = "http://localhost:8200"


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------

DISTRICT = "Prince William County Schools"
CATALOGUE = "catalog.pwcs.edu"


def load(engine: Engine, data: dict, quiet: bool = False) -> dict:
    """Every write is a MERGE.

    A constraint in 1.1.0 declares the key; it does not reject a duplicate
    CREATE (schema/edtech_kg.cypher). So re-running this must converge on the
    rows the catalogue still has, and only MERGE gives that.

    **MERGE converges for additions and never removes.** A row the district
    has deleted since the last load stays in the graph, so a re-run is only
    equal to the catalogue when it starts from `--reset`. `verify()` holds the
    graph to the catalogue rather than to this run's writes, and reports a
    surplus as exactly that.
    """
    def say(message: str) -> None:
        if not quiet:
            print(message, flush=True)

    # **Resolve against what PARSED, not against the sitemap.**
    #
    # `published` is every URL in the sitemap. `by_path` holds only pages that
    # `parse_course` returned a record for — it returns None for a page with no
    # `<h1>` or one titled "Page not found". So a page listed in the sitemap but
    # 404ing, or one whose heading markup the CMS changes, is in `published` and
    # absent from `by_path`, and `by_path[parent]` raises KeyError mid-load,
    # after partial writes.
    #
    # Every loop below tests `by_path` and counts what it could not resolve. A
    # sitemap entry that did not parse is exactly the "reported, never silently
    # dropped" case this file argues for everywhere else, and it was the one
    # place that would have crashed instead.
    by_path = {source.path_of(r["url"]): r["url"]
               for r in data["subjects"] + data["courses"] + data["pathways"]}
    unparsed = {p for p in data["published"] if p not in by_path}
    if unparsed:
        say(f"  {len(unparsed)} sitemap page(s) did not parse and cannot be "
            f"linked to: {sorted(unparsed)[:3]}")

    # A page whose markup disagrees with its URL depth. The markup wins — a
    # page rendering a course table IS a pathway — and the disagreement is
    # printed rather than silently resolved, because it is how #87 was found
    # and it is how the next one will be.
    if data.get("reclassified"):
        say(f"  {len(data['reclassified'])} page(s) publish a pathway course "
            f"table at course depth and are loaded as pathways, not courses "
            f"(#87): {sorted(data['reclassified'])[:2]}")

    say(f"  subjects   {len(data['subjects']):>5,}")
    for record in data["subjects"]:
        upsert(engine, "Subject", "url", record["url"],
               {"name": record["title"], "district": DISTRICT, "source": CATALOGUE})

    say(f"  courses    {len(data['courses']):>5,}")
    described = graded = 0
    for record in data["courses"]:
        # edtech-kg#137. The catalogue publishes both and nothing read them, so
        # `Q9` and `Q14` reached for properties no loader wrote and returned
        # null against a loaded district — the "parses, returns null, looks
        # like an answer" failure the schema's own PROPERTIES block describes.
        #
        # OMITTED rather than written empty when a course has neither. Writing
        # "" would make `c.description IS NOT NULL` true for every course and
        # turn a real absence into a measured presence — and absence is common
        # here: measured over the 791 courses `read()` classifies as courses,
        # 783 carry a description and 781 carry grade levels — so 8 and 10
        # publish neither. An earlier figure of 478 was counted over raw cache
        # FILES, which include subject and pathway pages.
        properties = {"name": record["title"], "district": DISTRICT,
                      "source": CATALOGUE}
        if record.get("description"):
            properties["description"] = record["description"]
            described += 1
        if record.get("grade_levels"):
            # JOINED, not a list. The engine's property values are scalars, and
            # this is how the catalogue prints them — "10, 11, 12".
            properties["grade_levels"] = ", ".join(record["grade_levels"])
            graded += 1
        upsert(engine, "Course", "url", record["url"], properties)
    say(f"    with a description  {described:>5,}")
    say(f"    with grade levels   {graded:>5,}")

    say(f"  pathways   {len(data['pathways']):>5,}")
    # `kind` is OMITTED where the catalogue states none, rather than defaulted
    # (#156). **On a re-loaded graph the omission has no effect** — `upsert`
    # cannot unwrite a property and 1.1.0 offers no way to, so the corrected
    # split appears on a fresh engine only. The measurement is on `upsert`.
    kinds: dict[str, int] = {}
    unstated = contradictory = 0
    for record in data["pathways"]:
        properties = {"name": record["title"], "district": DISTRICT,
                      "source": CATALOGUE}
        stated = markers_in(record["url"])
        if len(stated) == 1:
            kind = stated.pop()
            properties["kind"] = kind
            kinds[kind] = kinds.get(kind, 0) + 1
        elif stated:
            # Reported apart from silence: both leave `kind` absent, and a
            # district contradicting itself is not a district saying nothing.
            contradictory += 1
        else:
            unstated += 1
        upsert(engine, "Pathway", "url", record["url"], properties)
    for kind, count in sorted(kinds.items()):
        say(f"    {kind:<18} {count:>5,}")
    say(f"    {'kind unstated':<18} {unstated:>5,}")
    if contradictory:   # two sections named for one page
        say(f"    {'kind contradictory':<18} {contradictory:>5,}")

    # Course -> Subject, from the catalogue's own URL hierarchy. The parent
    # path is the subject page; a course whose parent is not published is left
    # unattached rather than attached to something invented.
    #
    # **Resolved against the SUBJECT index.** This looked the parent up in
    # `by_path` — every published page — and then wrote `MATCH (s:Subject …)`.
    # A course whose parent path is a pathway page resolved, the MATCH found
    # nothing, no edge was written and the counter still incremented. The third
    # place in this loader with that shape, after REQUIRES and INCLUDES; the
    # index each edge resolves against now matches the label it writes.
    subject_by_path = {source.path_of(r["url"]): r["url"] for r in data["subjects"]}
    in_subject, orphaned, off_level_parents = 0, 0, []
    for record in data["courses"]:
        parts = segments(record["url"])
        if not parts:
            # The catalogue root has no segments, so `[0]` was an IndexError
            # mid-load rather than a page reported as unattachable. No course
            # sits at depth 0 today; `pwcs_source.level` returns None for it
            # and it never reaches this list — which is why this never fired.
            orphaned += 1
            continue
        parent = "/" + parts[0]
        if parent not in subject_by_path:
            if parent in by_path:
                off_level_parents.append(by_path[parent])
            else:
                orphaned += 1
            continue
        engine.run(
            f"MATCH (c:Course {{url: {lit(record['url'])}}}), "
            f"(s:Subject {{url: {lit(subject_by_path[parent])}}}) "
            f"MERGE (c)-[:IN_SUBJECT]->(s)")
        in_subject += 1
    say(f"  IN_SUBJECT {in_subject:>5,}")
    if orphaned:
        say(f"  {orphaned} course(s) have no published subject page; left "
            f"unattached rather than attached to something invented")
    if off_level_parents:
        say(f"  {len(off_level_parents)} course(s) sit under a published page "
            f"that is not a subject; no edge written, and not counted as one: "
            f"{sorted(off_level_parents)[:3]}")

    # Course -> Course. The edge this graph exists for. Deduped and resolved
    # in `prerequisite_pairs`, which states why.
    course_by_path = {source.path_of(r["url"]): r["url"] for r in data["courses"]}
    prerequisites = prerequisite_pairs(data["courses"], by_path, course_by_path)
    if prerequisites["duplicated"]:
        say(f"  {prerequisites['duplicated']} prerequisite link(s) name a course "
            f"already named by the same page; one edge each, counted once")
    unresolved = prerequisites["unresolved"]
    if prerequisites["off_level"]:
        say(f"  {len(prerequisites['off_level'])} prerequisite link(s) point at a "
            f"published page that is not a course; no edge written, and not "
            f"counted as one: {sorted(prerequisites['off_level'])[:3]}")

    requires = 0
    for a, b in prerequisites["pairs"]:
        engine.run(
            f"MATCH (a:Course {{url: {lit(a)}}}), "
            f"(b:Course {{url: {lit(b)}}}) "
            f"MERGE (a)-[:REQUIRES]->(b)")
        requires += 1
    say(f"  REQUIRES   {requires:>5,}")
    if unresolved:
        say(f"  {unresolved} prerequisite link(s) point at a page that did not "
            f"parse — counted, not dropped")

    # The condition that is NOT a course reference. A node, not an edge — see
    # the schema: asserting a REQUIRES to a course that was never named would
    # invent a link the source does not make.
    # Courses and pathways only. Subjects were in this loop behind two
    # conditionals that cancelled out — the second `continue` could never fire
    # for a record the first had already labelled — so a subject page carrying a
    # requirement was silently skipped. None does today (measured: 0 of 127),
    # which is why it had to be counted rather than left to a reader to notice.
    skipped_subjects = sum(1 for r in data["subjects"] if r.get("requirements_text"))
    if skipped_subjects:
        say(f"  {skipped_subjects} subject page(s) state a requirement; not "
            f"loaded — a subject is not a thing a student enrols in")

    # The label comes from the LIST the record was read out of, not from
    # counting the segments of its URL. Depth is how `pwcs_source` classifies a
    # page in the first place, so re-deriving it here means one page can be a
    # Pathway to the reader and a Course to the loader the moment the district
    # publishes a pathway at a different depth — and the MATCH below would then
    # look for a label the node does not carry, write no edge, and still count
    # one.
    requirements = 0
    unquotable = []
    for label, records in (("Course", data["courses"]),
                           ("Pathway", data["pathways"])):
        for record in records:
            text = record.get("requirements_text")
            if not text:
                continue
            # A value carrying BOTH quote characters cannot be expressed in
            # 1.1.0 and `lit()` refuses it — correctly. Raising here aborted
            # the load after thousands of writes, so one unrepresentable
            # condition cost the whole run. Counted and skipped instead: losing
            # one row loudly beats losing the run at row 12,000. Measured at
            # zero for this catalogue, which `tests/test_engine.py` asserts.
            try:
                lit(text)
            except Unquotable:
                unquotable.append(record["url"])
                continue
            node_id = requirement_id(record["url"], text)
            upsert(engine, "Requirement", "id", node_id,
                   {"text": " ".join(text.split()), "source": CATALOGUE})
            engine.run(
                f"MATCH (n:{label} {{url: {lit(record['url'])}}}), "
                f"(r:Requirement {{id: {lit(node_id)}}}) "
                f"MERGE (n)-[:HAS_REQUIREMENT]->(r)")
            requirements += 1
    say(f"  HAS_REQ    {requirements:>5,}")
    if unquotable:
        say(f"  {len(unquotable)} requirement(s) hold both quote characters and "
            f"cannot be written as a 1.1.0 literal; skipped and named rather "
            f"than aborting the load: {sorted(unquotable)[:3]}")

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
    # 58 of the 374 resolving rows are a course appearing in two named sections
    # of the same pathway — a real fact about the catalogue, not a duplicate.
    # Rather than write 374 statements and let 58 disappear, the rows are
    # grouped in `pathway_edges` and the sections joined onto the one edge the
    # engine can hold; the collapse is counted and reported, so the number that
    # vanished is on the page rather than in the difference between two others.
    edges = pathway_edges(data["pathways"], by_path, course_by_path)
    grouped, collapsed = edges["grouped"], edges["collapsed"]
    if edges["off_level"]:
        say(f"  {len(edges['off_level'])} pathway row(s) name a published page "
            f"that is not a course; no edge written, and not counted as one: "
            f"{sorted(edges['off_level'])[:3]}")
    if edges["unlinkable"]:
        say(f"  {edges['unlinkable']} pathway row(s) name a page that did not "
            f"parse; counted, not linked")
    if edges["conflicting"]:
        say(f"  {edges['conflicting']} course(s) carry different credit values "
            f"in different sections of one pathway; the first is kept and the "
            f"difference is reported rather than lost")
    if collapsed:
        say(f"  {collapsed} published rows are a course in a second section of "
            f"the same pathway; the engine holds one edge per pair, so the "
            f"section names are joined onto it")

    # Two statements per edge, not one. `MERGE (p)-[e:INCLUDES]->(c) SET e.x`
    # does not parse in 1.1.0 — the parser takes `ON CREATE SET` / `ON MATCH
    # SET` after a MERGE but not a bare SET (#75) — and `ON CREATE SET` alone
    # fires only on insert, so a re-run after the district edits a section name
    # would keep the old one. The MATCH … SET always refreshes, which is what a
    # re-runnable loader needs. Same trade as `upsert`, for the same reason.
    includes = 0
    for (pathway, course), entry in grouped.items():
        engine.run(
            f"MATCH (p:Pathway {{url: {lit(pathway)}}}), "
            f"(c:Course {{url: {lit(course)}}}) "
            f"MERGE (p)-[:INCLUDES]->(c)")
        engine.run(
            f"MATCH (:Pathway {{url: {lit(pathway)}}})-[e:INCLUDES]->"
            f"(:Course {{url: {lit(course)}}}) "
            f"SET e.section = {lit(' | '.join(entry['sections']) or None)}, "
            # `sections` is how many NAMED sections this edge covers, which is
            # what `section` joins. `rows` is how many published rows folded
            # into it — the number the schema comment promises, and the two
            # differ the moment a row repeats a section or carries none.
            f"e.sections = {lit(len(entry['sections']))}, "
            f"e.rows = {lit(entry['rows'])}, "
            f"e.credits = {lit(entry['credits'])}")
        includes += 1
    say(f"  INCLUDES   {includes:>5,}")

    return {"subjects": len(data["subjects"]), "courses": len(data["courses"]),
            "pathways": len(data["pathways"]), "in_subject": in_subject,
            "requires": requires, "requirements": requirements,
            "includes": includes, "rows_collapsed_into_an_edge": collapsed,
            "pathway_rows_published": sum(len(p["courses"]) for p in data["pathways"]),
            "pathway_rows_unresolvable": sum(len(p["dangling"]) for p in data["pathways"])}


def verify(engine: Engine, loaded: dict) -> list[str]:
    """Does the graph hold this catalogue, and only this catalogue?

    **The contract is "the graph equals the catalogue", not "everything this
    run wrote landed."** Those are different checks and the code used to argue
    for one while performing the other.

    It matters because MERGE converges for ADDITIONS and never removes
    anything. The district drops a prerequisite; a re-run writes everything
    else correctly and the stale edge stays; the engine then holds more than
    the loader wrote, and this exits non-zero on a load that did exactly what
    it should. That is not a false alarm under this contract — the graph no
    longer equals the catalogue — but the message has to say so, and say what
    to do about it, rather than reporting a bare mismatch.

    So: **a re-run after anything is removed at the source needs `--reset`.**
    `load()` says the same, and a surplus is reported differently from a
    shortfall below.

    Counted from the engine, not from the loader's own tallies — a loader that
    reports what it *intended* to write is the one failure this cannot catch
    by itself.

    **Scoped to this catalogue**, the same way `--reset` is. Counting every
    `:Course` in the graph works only while one district is loaded; the first
    second district makes this exit non-zero with a mismatch that is not a
    fault. The loader's tallies are per-catalogue, so what they are checked
    against has to be too.

    Edges are scoped by their start node's `source` — where the edge was written
    from. No edge here spans two districts, and none can: every pattern above
    matches both ends inside one catalogue.
    """
    where = f"n.source = {lit(CATALOGUE)}"
    problems = []

    def mismatch(kind: str, name: str, expected: int, got: int) -> str:
        if got > expected:
            return (f"{name}: loader wrote {expected:,}, engine holds {got:,} — "
                    f"{got - expected:,} more {kind}(s) than this catalogue "
                    f"contains. MERGE never removes, so this is what a source "
                    f"row being deleted looks like on a re-run. Re-run with "
                    f"--reset.")
        return (f"{name}: loader wrote {expected:,}, engine holds {got:,} — "
                f"{expected - got:,} {kind}(s) did not land.")
    for label, expected in (("Subject", loaded["subjects"]),
                            ("Course", loaded["courses"]),
                            ("Pathway", loaded["pathways"]),
                            # Requirement was written and never read back. It
                            # is the one label whose key is derived rather than
                            # taken from the source, so a collision in
                            # `requirement_id` would silently merge two
                            # conditions into one node — and nothing checked.
                            ("Requirement", loaded["requirements"])):
        got = engine.scalar(f"MATCH (n:{label}) WHERE {where} RETURN count(n)")
        if got != expected:
            problems.append(mismatch("node", label, expected, got))
    # A node that exists, carries its key, and has none of its properties.
    #
    # `upsert` MERGEs the key and SETs the rest in a SECOND statement, because
    # a bare SET after MERGE does not parse in 1.1.0 (#75). Pre-rendering every
    # value stops an Unquotable from landing the first without the second — but
    # the second request can still fail on its own: retries exhausted, a 4xx, a
    # parse error from a value nobody expected. The node is then half written,
    # and a COUNT cannot see it, because counting is exactly what it passes.
    #
    # Recoverable, since the loader is re-runnable. But nothing said it had
    # happened, and "verified" appeared on the console either way.
    for label, prop in (("Subject", "name"), ("Course", "name"),
                        ("Pathway", "name"), ("Requirement", "text")):
        half = engine.scalar(
            f"MATCH (n:{label}) WHERE {where} AND n.{prop} IS NULL RETURN count(n)")
        if half:
            problems.append(
                f"{label}: {half:,} node(s) carry the key and no `{prop}` — the "
                f"MERGE landed and the SET that follows it did not. Re-running "
                f"the loader repairs them.")

    for edge, expected in (("REQUIRES", loaded["requires"]),
                           ("IN_SUBJECT", loaded["in_subject"]),
                           ("INCLUDES", loaded["includes"]),
                           ("HAS_REQUIREMENT", loaded["requirements"])):
        got = engine.scalar(f"MATCH (n)-[e:{edge}]->() WHERE {where} RETURN count(e)")
        if got != expected:
            problems.append(mismatch("edge", edge, expected, got))
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

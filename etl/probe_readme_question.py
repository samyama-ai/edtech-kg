"""The question the README opens with, answered by the engine.

edtech-kg#6 asks for a README that opens with **one question, one Cypher
query, one results table** — the house convention — rather than with
architecture. The repo's front door had a title, a badge and a paragraph about
what the project is.

The reason this is a probe and not a paragraph someone typed: **the results
table on the front page is the most-read set of figures in the repo, and it
was going to be the least checked.** Every other number here comes from a
record; the one a reader sees first should not be the exception.

    SAMYAMA_URL=http://localhost:8200 python -m etl.probe_readme_question
    SAMYAMA_URL=http://localhost:8200 python -m etl.probe_readme_question --record

Needs a graph with the district loaded — `etl/load_pwcs.py`. It reads and
writes nothing.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys

from etl.engine import Engine
from etl.provenance import write_record

ROOT = pathlib.Path(__file__).resolve().parents[1]
RECORD = ROOT / "docs" / "sources" / "readme-question-measured.json"
RECORD_NOTE = (
    "Measured by `python -m etl.probe_readme_question --record` against a "
    "graph with the district loaded. The README's opening question, its query "
    "and its answer come from here — `tests/test_readme.py` fails if the page "
    "and this file disagree. The front page's table is the most-read set of "
    "figures in this repo and was the only one with no run behind it.")

#: The question, spelled once. `docs/questions.md` calls it Q61 and the README
#: asks it in a student's words; both are this query.
QUESTION = "If I skip Algebra 1, what does that close off later?"

#: **The query the README prints, character for character.** Recorded rather
#: than paraphrased: a probe that measures a DIFFERENT query from the one on
#: the page proves the page's table is reproducible by something nobody can
#: see. `tests/test_readme.py` compares this string with the page's fenced
#: block.
QUERY = """MATCH (blocked:Course)-[:REQUIRES*1..8]->(:Course {name: 'Algebra 1'})
MATCH (blocked)-[:IN_SUBJECT]->(s:Subject)
RETURN s.name AS subject, count(DISTINCT blocked) AS closed_off
ORDER BY closed_off DESC LIMIT 5"""

GATE = "Algebra 1"

#: **The heading the page opens with, character for character** — the same
#: question in the page's own words rather than the student's. Recorded like
#: `QUERY` is, and for the same reason: the test that checks the question comes
#: FIRST needs a needle that is actually the question. Its first version
#: reduced `QUESTION` through a `split` chain to the single character `"I"`, so
#: it asserted that some capital I appeared before the badges — true of any
#: page with `IB` in the body, and still true with the question moved back to
#: the bottom, which is the exact regression it was advertised as catching.
HEADING = "> ### If a student doesn't pass Algebra 1, what closes off?"

#: The depth bound in `QUERY`, read OFF the query rather than repeated. The
#: depth probe exists to justify this bound, so a probe that stopped short of
#: it could only ever verify part of it.
BOUND = int(re.search(r"REQUIRES\*1\.\.(\d+)", QUERY).group(1))


def rows(engine: Engine, statement: str) -> list:
    return engine.run(statement).get("records") or []


class Unmeasured(RuntimeError):
    """The engine did not answer a count this page quotes."""


def count(engine: Engine, statement: str) -> int:
    """One count, or a refusal — never a silent zero.

    `int(rows[0][0]) if rows else 0` wrote a **0** into the record for a
    graph that answered nothing, and the README states these two as
    denominators: "out of 791 in the graph (240 REQUIRES edges)". A zero
    denominator published as a measurement is the failure this probe exists
    to prevent, arriving through the fallback rather than through the answer.

    Same shape as `etl/snapshot.py:_count` and `etl/scratch_engine.py`, both
    of which record this guard failing open before.
    """
    answered = rows(engine, statement)
    if not answered or not answered[0] or answered[0][0] is None:
        raise Unmeasured(
            f"the engine did not answer `{statement}`, so a figure the page "
            f"quotes as a denominator cannot be measured. Refusing rather "
            f"than recording a zero.")
    try:
        return int(answered[0][0])
    except (TypeError, ValueError) as unreadable:
        raise Unmeasured(
            f"the engine answered {answered[0][0]!r} to `{statement}`, which "
            f"is not a number.") from unreadable


def measure(url: str) -> dict:
    engine = Engine(url)

    # The page's own query, run as the page prints it.
    table = [{"subject": r[0], "closed_off": int(r[1])}
             for r in rows(engine, QUERY.replace("\n", " ")) if r[0]]

    # And the total behind it, which the page states as a sentence. The table
    # is a top-5 by subject; the sentence is the count of courses, and the two
    # are different questions about one answer.
    # **`BOUND` and `GATE`, not repeated literals.** These two carried
    # `*1..8` and `"Algebra 1"` written out again, so changing the bound in
    # `QUERY` left them measuring 8 — the same drift this probe exists to
    # guard against, one file inward.
    reached = rows(engine, f'MATCH (blocked:Course)-[:REQUIRES*1..{BOUND}]->'
                           f'(gate:Course) WHERE gate.name = "{GATE}" '
                           f'WITH blocked RETURN blocked.name')
    closed = sorted({r[0] for r in reached if r[0]})
    subjects = rows(engine, f'MATCH (blocked:Course)-[:REQUIRES*1..{BOUND}]->'
                            f'(gate:Course) WHERE gate.name = "{GATE}" '
                            f'WITH blocked MATCH (blocked)-[:IN_SUBJECT]->(s:Subject) '
                            f'WITH s RETURN s.name')

    # The denominators the README quotes beside the answer, from the same run.
    courses = count(engine, "MATCH (c:Course) WITH c RETURN count(c)")
    edges = count(engine, "MATCH ()-[r:REQUIRES]->() RETURN count(r)")

    # How deep the chains actually run, so the bound in QUERY is justified
    # rather than assumed. Asked of the engine at increasing depths: the
    # answer stops growing at the real depth.
    depths = {}
    for depth in range(1, BOUND + 1):
        found = rows(engine, f'MATCH (l:Course)-[:REQUIRES*1..{depth}]->'
                             f'(g:Course) WHERE g.name = "{GATE}" '
                             f'WITH l RETURN l.name')
        depths[depth] = len({f[0] for f in found if f[0]})

    return {
        "_": RECORD_NOTE,
        "question": QUESTION,
        "heading": HEADING,
        "query": QUERY,
        "bound": BOUND,
        "gate": GATE,
        "courses_in_graph": courses,
        "requires_edges": edges,
        "closes_off": len(closed),
        "subjects": len({s[0] for s in subjects if s[0]}),
        "table": table,
        "distinct_by_depth": depths,
    }


def report(found: dict) -> None:
    print(f"  {found['question']}\n")
    print(f"  {found['closes_off']} courses across {found['subjects']} "
          f"subjects, out of {found['courses_in_graph']:,} in the graph "
          f"({found['requires_edges']} REQUIRES edges)\n")
    print(f"  {'subject':<32} closed_off")
    for row in found["table"]:
        print(f"    {row['subject']:<32} {row['closed_off']:>5}")
    print(f"\n  distinct by depth: {found['distinct_by_depth']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m etl.probe_readme_question",
        description=__doc__.strip().splitlines()[0])
    parser.add_argument("--url", default=os.environ.get(
        "SAMYAMA_URL", "http://localhost:8200"))
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--record", action="store_true")
    args = parser.parse_args(argv)

    if args.json and args.record:
        print("--json and --record ask for different things; pick one.",
              file=sys.stderr)
        return 2

    try:
        found = measure(args.url)
    except Unmeasured as unmeasured:
        print(f"{args.url}: {unmeasured}", file=sys.stderr)
        return 3
    if not found["table"]:
        # **A separate refusal from the one below.** `closes_off` counts
        # courses reached; `table` needs the IN_SUBJECT edges too. A graph
        # with Courses loaded and no subjects answered `closes_off: 28`
        # beside an empty table and recorded successfully — and the page-side
        # test iterates the table, so an empty one passed vacuously while the
        # README's table was deleted.
        print(f"{args.url} reached courses but grouped none of them into "
              f"subjects, so the page's table would be empty. Load the "
              f"district fully — `python -m etl.load_pwcs`.", file=sys.stderr)
        return 3
    if not found["closes_off"]:
        # **REFUSED.** An empty answer here is almost always an empty graph,
        # and writing it would put "closes off 0 courses" on the front page of
        # the repo as a measurement.
        print(f"{args.url} answered with nothing for {GATE!r}. Load the "
              f"district first — `python -m etl.load_pwcs`.", file=sys.stderr)
        return 3

    if args.json:
        print(json.dumps(found, indent=2))
        return 0
    report(found)
    if args.record:
        write_record(RECORD, found)
        print(f"\n  -> {RECORD.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

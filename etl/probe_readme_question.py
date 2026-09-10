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
import sys

from etl.engine import Engine
from etl.provenance import write_record

import pathlib

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


def rows(engine: Engine, statement: str) -> list:
    return engine.run(statement).get("records") or []


def measure(url: str) -> dict:
    engine = Engine(url)

    # The page's own query, run as the page prints it.
    table = [{"subject": r[0], "closed_off": int(r[1])}
             for r in rows(engine, QUERY.replace("\n", " ")) if r[0]]

    # And the total behind it, which the page states as a sentence. The table
    # is a top-5 by subject; the sentence is the count of courses, and the two
    # are different questions about one answer.
    reached = rows(engine, 'MATCH (blocked:Course)-[:REQUIRES*1..8]->'
                           '(gate:Course) WHERE gate.name = "Algebra 1" '
                           'WITH blocked RETURN blocked.name')
    closed = sorted({r[0] for r in reached if r[0]})
    subjects = rows(engine, 'MATCH (blocked:Course)-[:REQUIRES*1..8]->'
                            '(gate:Course) WHERE gate.name = "Algebra 1" '
                            'WITH blocked MATCH (blocked)-[:IN_SUBJECT]->(s:Subject) '
                            'WITH s RETURN s.name')

    # The denominators the README quotes beside the answer, from the same run.
    courses = rows(engine, "MATCH (c:Course) WITH c RETURN count(c)")
    edges = rows(engine, "MATCH ()-[r:REQUIRES]->() RETURN count(r)")

    # How deep the chains actually run, so the bound in QUERY is justified
    # rather than assumed. Asked of the engine at increasing depths: the
    # answer stops growing at the real depth.
    depths = {}
    for depth in range(1, 7):
        found = rows(engine, f'MATCH (l:Course)-[:REQUIRES*1..{depth}]->'
                             f'(g:Course) WHERE g.name = "{GATE}" '
                             f'WITH l RETURN l.name')
        depths[depth] = len({f[0] for f in found if f[0]})

    return {
        "_": RECORD_NOTE,
        "question": QUESTION,
        "query": QUERY,
        "gate": GATE,
        "courses_in_graph": int(courses[0][0]) if courses else 0,
        "requires_edges": int(edges[0][0]) if edges else 0,
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

    found = measure(args.url)
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

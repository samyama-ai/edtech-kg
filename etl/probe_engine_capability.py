"""What this engine actually does, asked of it rather than remembered.

    python -m etl.probe_engine_capability            # as prose
    python -m etl.probe_engine_capability --json     # machine-readable
    python -m etl.probe_engine_capability --record   # refresh the committed record

edtech-kg#136. Every engine fact this repo relies on was written into a comment
by hand: `240` REQUIRES edges, `359` rows from a query that should return none,
`0 of 791` from one that should return some. Nothing produced them and nothing
re-runs them, in a repo whose stated rule is that a count reaches a document
through a probe and is never typed.

`431 of 791` is what that costs. It was typed into two files and, when the
question was finally put to the graph, the answer was 463.

**The defects are measured too, not just the capabilities.** Four of the
constructs below are things the engine gets WRONG, and each cost this repo a
review round before it was written down:

- a bare single-node `MATCH (c:Course {url: …})` does not apply its map
- `NOT x IN [a, b]` without parentheses does not negate the membership test
- a bound variable inside a property map is a parse error
- a bare aggregate returns one row on any graph, so `records != []` is not an
  emptiness check

A capability probe that only recorded what works would leave exactly the facts
that cost the most unrecorded.

**Gated on a LOADED district**, because half of these are only distinguishable
against data: a predicate inside a `WHERE` is never evaluated on an empty
graph, which is how the first two got past validation in the first place.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
RECORD = ROOT / "docs" / "sources" / "engine-capability-measured.json"

DEFAULT_URL = os.environ.get("SAMYAMA_URL", "http://localhost:8080")
TENANT = "edtech"

RECORD_NOTE = (
    "One measured run against a loaded district, committed so the prose in "
    "benchmarks/questions/*.cypher and docs/questions.md can be checked "
    "without an engine. Refresh with "
    "`python -m etl.probe_engine_capability --record`.")


class Unreachable(RuntimeError):
    """No engine answered, so nothing here was measured."""


class NoData(RuntimeError):
    """An engine answered and holds no district, so half of this proves nothing."""


def ask(url: str, cypher: str) -> dict:
    """One statement, with the engine's refusal kept rather than raised.

    A construct that ERRORS is a measurement too — `{year: latest}` is a parse
    error and that is the fact worth recording, so an error is returned as a
    result and not as an exception.
    """
    try:
        with urllib.request.urlopen(urllib.request.Request(
                url + "/api/query", method="POST",
                data=json.dumps({"tenant": TENANT, "query": cypher}).encode(),
                headers={"Content-Type": "application/json"}), timeout=120) as answer:
            return json.loads(answer.read())
    except urllib.error.HTTPError as refused:
        return {"error": refused.read().decode(errors="replace")[:300]}
    except (urllib.error.URLError, TimeoutError, OSError) as unreachable:
        raise Unreachable(f"{url} is not answering: {unreachable}") from unreachable


def rows(answer: dict):
    """The result as a document can quote it: a scalar, a row count, or an error."""
    if "error" in answer:
        return {"error": " ".join(answer["error"].split())[:120]}
    records = answer.get("records") or []
    if len(records) == 1 and len(records[0]) == 1:
        return {"value": records[0][0]}
    return {"rows": len(records)}


#: Each construct, what it is asked, and why it is here. The `expected` field
#: is what this repo BELIEVES — the probe records what happens, and the test
#: beside it fails when the two part company. Writing the belief down is the
#: point: an engine that quietly starts behaving correctly is a change this
#: repo needs to notice, not a silent improvement.
CONSTRUCTS = [
    ("requires_edges", "MATCH (:Course)-[r:REQUIRES]->(:Course) RETURN count(r) AS n",
     "The prerequisite edges a loaded district holds. Quoted in tier 4 as 240."),
    ("courses", "MATCH (c:Course) RETURN count(c) AS n",
     "The district's courses. Quoted as 791 in five places."),
    ("chains_any_length",
     "MATCH p = (:Course)-[:REQUIRES*]->(:Course) RETURN count(p) AS n",
     "Every prerequisite path. This is the 359 Q71 reported as cycles."),
    ("chains_length_two_or_more",
     "MATCH p = (:Course)-[:REQUIRES*2..]->(:Course) RETURN count(p) AS n",
     "Paths long enough to have a cut vertex. Quoted in tier 4 and in Q68's "
     "note as 119 — a DIFFERENT figure from the one above, and named "
     "separately because reading them as one is how 119 and 359 end up in the "
     "same paragraph meaning the same thing."),
    ("deepest_chain", "MATCH p = (:Course)-[:REQUIRES*]->(:Course) "
                      "RETURN max(length(p)) AS n",
     "Q66's answer, and a bare aggregate — one row on any graph."),
    ("isolated_courses",
     "MATCH (c:Course) WHERE NOT EXISTS { MATCH (c)-[:REQUIRES]->(:Course) } "
     "AND NOT EXISTS { MATCH (:Course)-[:REQUIRES]->(c) } RETURN count(c) AS n",
     "Q67's answer. Typed as 431 in two files; the graph said 463."),

    # THE DEFECTS. Each cost a review round.
    ("repeated_variable_across_var_length",
     "MATCH p = (c:Course)-[:REQUIRES*1..1]->(c) RETURN count(p) AS n",
     "Q71. Should be 0 — no course requires itself. The engine does not bind a "
     "repeated variable across a variable-length pattern, so it matches every "
     "edge instead."),
    ("in_over_a_node_list",
     "MATCH p = (:Course)-[:REQUIRES*]->(:Course) "
     "WITH p, nodes(p) AS ns UNWIND ns AS x WITH p WHERE x IN nodes(p) "
     "RETURN count(p) AS n",
     "Q68. `IN` over a list of NODES matches nothing either way rather than "
     "refusing."),
    ("bare_single_node_map_absent_url",
     'MATCH (c:Course {url: "https://catalog.pwcs.edu/no/such-course"}) '
     "RETURN count(c) AS n",
     "Should be 0. A bare single-node match does not apply its inline property "
     "map, so this counts the whole label."),
    ("relationship_pattern_map_absent_url",
     'MATCH (:Course)-[:REQUIRES]->(c:Course {url: "https://catalog.pwcs.edu/no/such"}) '
     "RETURN count(*) AS n",
     "Should be 0, and IS — the same syntax inside a relationship pattern "
     "filters correctly. The contrast is the finding."),
    ("not_in_list_unparenthesised",
     'MATCH (c:Course) WHERE NOT c.url IN ["a", "b"] RETURN count(c) AS n',
     "Should be every course. Without parentheses the membership test is not "
     "negated."),
    ("not_in_list_parenthesised",
     'MATCH (c:Course) WHERE NOT (c.url IN ["a", "b"]) RETURN count(c) AS n',
     "The same question written correctly, for the contrast."),
    ("bound_variable_in_property_map",
     "MATCH (c:Course) WITH max(1) AS k "
     "MATCH (d:Course {district: k}) RETURN count(d) AS n",
     "A bound variable inside a property map is a parse error, not a match."),
    ("aggregate_over_an_absent_label",
     "MATCH p = (:NoSuchLabel)-[:REQUIRES*]->(:NoSuchLabel) "
     "RETURN max(length(p)) AS n",
     "One row of null on a graph holding none of the label — which is why "
     "`records != []` is not an emptiness check."),
]


def probe(url: str = DEFAULT_URL, quiet: bool = False) -> dict:
    """Run every construct and report what the engine did with it."""
    held = ask(url, "MATCH (c:Course) RETURN count(c) AS n")
    if "error" in held:
        raise Unreachable(f"{url} answered but refused a count: {held['error']}")
    courses = (held.get("records") or [[0]])[0][0]
    if not courses:
        raise NoData(
            f"the graph at {url} holds no Course nodes. Half of these are only "
            f"distinguishable against data — a predicate inside a WHERE is "
            f"never evaluated on an empty graph, which is how two of the "
            f"defects below got past validation. Load a district first.")

    measured = {}
    for name, cypher, why in CONSTRUCTS:
        measured[name] = {"cypher": " ".join(cypher.split()), "why": why,
                          **rows(ask(url, cypher))}
        if not quiet:
            got = measured[name]
            shown = got.get("error", got.get("value", got.get("rows")))
            print(f"  {name:38} {shown}")
    # The engine's own version, NOT the url it was reached at. A committed
    # `http://localhost:8200` churns on every machine and says nothing; the
    # version is the thing a reader needs to know these were measured against.
    # It is not a build identifier — two builds report 1.7.0 and behave
    # differently — so it is recorded as what the engine claims, not as proof.
    status = ask(url, "RETURN 1 AS ok")
    version = "unknown"
    try:
        with urllib.request.urlopen(url + "/api/status", timeout=30) as answer:
            version = json.loads(answer.read()).get("version", "unknown")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        pass
    return {"engine_version_reported": version, "courses": courses,
            "constructs": measured} if "error" not in status else {}


def main(argv: list[str] | None = None) -> int:
    summary = (__doc__ or "").splitlines()
    parser = argparse.ArgumentParser(description=summary[0] if summary else None)
    parser.add_argument("--url", default=DEFAULT_URL, help="Engine base URL.")
    parser.add_argument("--json", action="store_true", help="Print the result as JSON.")
    parser.add_argument("--record", action="store_true",
                        help=f"Write {RECORD.name} from this run.")
    args = parser.parse_args(argv)
    try:
        result = probe(args.url, quiet=args.json or args.record)
    except NoData as empty:
        print(f"\nrefused: {empty}", file=sys.stderr)
        return 1
    except Unreachable as gone:
        print(f"\nunreachable: {gone}", file=sys.stderr)
        return 2

    if args.record:
        # `_` first and written by the writer, not left in the file for a
        # refresh to preserve by accident — the shape the licence record uses.
        RECORD.parent.mkdir(parents=True, exist_ok=True)
        RECORD.write_text(json.dumps(
            {"_": RECORD_NOTE,
             "retrieved_at": datetime.date.today().isoformat(),
             **result}, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {RECORD.relative_to(ROOT)}")
    elif args.json:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

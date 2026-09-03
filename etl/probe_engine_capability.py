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

from etl.engine import ENGINE_VERSION, RETRIED, Engine, Refused

ROOT = pathlib.Path(__file__).resolve().parents[1]
RECORD = ROOT / "docs" / "sources" / "engine-capability-measured.json"

DEFAULT_URL = os.environ.get("SAMYAMA_URL", "http://localhost:8080")
GRAPH = "edtech"

RECORD_NOTE = (
    "One measured run against a loaded district, committed so the prose in "
    "benchmarks/questions/*.cypher and docs/questions.md can be checked "
    "without an engine. Refresh with "
    "`python -m etl.probe_engine_capability --record`.")


class Unreachable(RuntimeError):
    """No engine answered, so nothing here was measured."""


class NoData(RuntimeError):
    """An engine answered and holds no district, so half of this proves nothing."""


def ask(engine: Engine, cypher: str) -> dict:
    """One statement, through the repo's own client.

    THREE things this used to get wrong by writing its own request, and all
    three are already solved in `etl/engine.py`:

    - It sent `{"tenant": …}`. `/api/query` takes `graph`, which is what
      `etl/engine.py`, `demo/demo.py` and the README all use — so the probe
      was selecting nothing and measuring whatever the default is. On this
      build no key isolates anything (edtech-kg#149), but a probe that names
      the wrong field cannot be evidence either way.
    - It flattened a transport failure into `{"error": …}`, so a dying
      engine's 500 would be committed as the recorded fact for a construct.
      `Engine.run` retries transient 5xx and RAISES when it finally fails,
      which keeps a refusal and a failure apart. That distinction was
      consolidated once already, with a comment saying three copies existed;
      this was the fourth.
    - It had no retry at all.

    An engine REFUSAL is returned rather than raised, because a construct the
    engine rejects is a measurement and one of the defects here is exactly
    that. It arrives in BOTH shapes — this build answers a parse error with
    400, and `etl/engine.py` documents a 200 carrying an `error` key as well —
    and `Engine` raises `Refused` for each, so neither aborts the run. The
    earlier version handled only the 400 and its docstring claimed otherwise,
    so a 200-shaped refusal would have killed the probe with a message blaming
    the transport for a measurement.
    """
    try:
        return engine.run(cypher)
    except Refused as refused:
        if refused.code not in RETRIED:
            # `refused.detail`, not a split on the message. The 4xx and 200
            # shapes put the engine's text on opposite sides of the newline, so
            # splitting recovered the message from one and the query location
            # from the other — measured: a 200-shaped refusal recorded
            # `"  on: X"` as the fact about the construct.
            return {"error": " ".join(refused.detail.split())[:300]}
        # A RETRIED code arriving here means the retries were exhausted. `< 500`
        # sent 429 down the measurement path, so a rate-limited engine wrote
        # `{"error": "429 on: …"}` into the committed record as the fact about
        # a construct — the exact failure this split exists to prevent.
        raise Unreachable(
            f"{engine.url} returned {refused.code} on `{cypher[:60]}` after "
            f"retries — a dying engine, not a fact about the construct") from refused
    except RuntimeError as failed:
        raise Unreachable(f"{engine.url} failed on `{cypher[:60]}`: {failed}") from failed


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
    ("in_over_a_node_list_from_a_separate_match",
     "MATCH p = (:Course)-[:REQUIRES*2..]->(:Course) MATCH (x:Course) "
     "WITH p, x WHERE x IN nodes(p) RETURN count(*) AS n",
     "Q68's shape. Should be > 0 — some course is on some path. `x` comes from "
     "its own MATCH, and against a node list from elsewhere the test matches "
     "NOTHING."),
    ("not_in_over_a_node_list_from_a_separate_match",
     "MATCH p = (:Course)-[:REQUIRES*2..]->(:Course) MATCH (x:Course) "
     "WITH p, x WHERE NOT (x IN nodes(p)) RETURN count(*) AS n",
     "The negation of the above. Should be very large. Also 0 — which is the "
     "finding: it matches nothing EITHER WAY rather than refusing, so Q68 "
     "answers \"there are no articulation points\" on a graph that has them."),
    ("in_over_a_node_list_unwound_from_the_path",
     "MATCH p = (:Course)-[:REQUIRES*]->(:Course) WITH p, nodes(p) AS ns "
     "UNWIND ns AS x WITH p, x WHERE x IN nodes(p) RETURN count(p) AS n",
     "The CONTRAST, and the reason the two above are recorded separately. "
     "Unwound from the path itself the same operator works. An earlier version "
     "of this probe measured only this shape, dropped `x` before the WHERE and "
     "recorded the scoping result as evidence about membership — which is the "
     "unchallengeable figure this probe exists against."),
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


def probe(url: str = DEFAULT_URL, graph: str = GRAPH, quiet: bool = False) -> dict:
    """Run every construct and report what the engine did with it."""
    engine = Engine(url, graph)

    # The reachability check FIRST, and it raises. The previous shape ran a
    # ping at the END and returned `{}` when it failed — and `main()` read that
    # as success, wrote a record holding only `_` and `retrieved_at`, printed
    # "wrote …" and exited 0. The artefact this whole probe exists to make
    # trustworthy was overwritten with nothing, and the next test run died on a
    # KeyError. A path that writes no measurement must not exit 0.
    version = engine_version(url)
    held = ask(engine, "MATCH (c:Course) RETURN count(c) AS n")
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
                          **rows(ask(engine, cypher))}
        if not quiet:
            got = measured[name]
            shown = got.get("error", got.get("value", got.get("rows")))
            print(f"  {name:38} {shown}")
    return {"engine_version_reported": version, "graph": graph,
            "constructs": measured}


def engine_version(url: str) -> str:
    """What the engine calls itself — NOT a build identifier.

    Recorded instead of the url, which is `http://localhost:8200` on one
    machine and something else on the next and says nothing either way. Two
    builds report 1.7.0 and answer the same query differently, so this is what
    the engine claims and not proof of anything. `README.md` pins the image at
    1.1.0 and the running engine reports 1.7.0 — the tag is not the version,
    which is worth knowing before treating either as reproducible.
    """
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/api/status", timeout=30) as answer:
            reported = json.loads(answer.read()).get("version")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as gone:
        raise Unreachable(f"{url}/api/status did not answer: {gone}") from gone
    if reported and reported != ENGINE_VERSION:
        # The pinned build is what every other figure in this repo was measured
        # against — `tests/test_engine_version.py` asserts it. A record taken
        # from a different engine would pass every check here and quietly mean
        # something else, which is the drift this whole probe exists to remove.
        raise Unreachable(
            f"{url} reports {reported} and this repo pins {ENGINE_VERSION}. "
            f"Recording against a different build would give figures the rest "
            f"of the documents do not describe.")
    if not reported:
        # RAISED, not recorded as "unknown". The record's only provenance field
        # silently becoming meaningless while `--record` prints "wrote …" and
        # exits 0 is a weaker version of the empty-record rule this probe
        # already has.
        raise Unreachable(f"{url}/api/status reports no version")
    return reported


def main(argv: list[str] | None = None) -> int:
    summary = (__doc__ or "").splitlines()
    parser = argparse.ArgumentParser(description=summary[0] if summary else None)
    parser.add_argument("--url", default=DEFAULT_URL, help="Engine base URL.")
    parser.add_argument("--graph", default=GRAPH, help="Graph to measure.")
    parser.add_argument("--json", action="store_true", help="Print the result as JSON.")
    parser.add_argument("--record", action="store_true",
                        help=f"Write {RECORD.name} from this run.")
    args = parser.parse_args(argv)
    try:
        result = probe(args.url, args.graph, quiet=args.json or args.record)
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

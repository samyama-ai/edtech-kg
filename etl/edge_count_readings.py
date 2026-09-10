"""How this engine REPORTS its edges — which is not the same as what it holds.

Split out of `etl/snapshot.py` at the 500-line review limit, and split by
SUBJECT rather than by length. That module moves a graph and checks the
counts came back; this one measures the disagreement between two ways of
asking how many edges there are, which is a question about the engine and
would be just as true with no snapshot involved.

`/api/status` reports **2,834** edges for a graph holding **1,417** when that
graph was built by Cypher `CREATE`, and **1,417** for the same graph imported
from a snapshot. Two readings fit:

  (a) the endpoint double-counts on the Cypher-loaded side;
  (b) it counts stored adjacency entries, two per edge, and the IMPORTED
      graph holds only one — under which the endpoint is right and the
      import is LOSSY.

The difference decides whether the dataset card warns readers off a working
endpoint, or a demo opens on a graph missing half its edges. A per-type
`()-[r:T]->()` count is identical under both and settles nothing.

**The undirected count also settles nothing**, and an earlier version of this
argument claimed it did. It comes back at exactly twice directed for all four
types on both engines — 480/240, 1446/723, 632/316, 276/138, no self-loop
residue, no exceptions — which is the signature of a query-level doubling rule
at least as much as of a traversal over stored entries.

**The reverse expansion settles it**, because it does not rest on undirected
semantics at all. Bind the HEAD label and walk the edge backwards: under (b),
with one entry held at the tail, the imported graph could not answer from the
head. Measured on 1.1.0, both engines answer 1,417, per type and in total. So
(b) is excluded.

`storage.nodes` matching at 1,098 is NOT evidence — (b) predicts that too.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from etl.engine import Engine, identifier


#: **The graph this repo loads into.** Everything here built `Engine(url)`
#: with no graph, so it all worked on `default` while `etl/load_pwcs.py` and
#: `demo/demo.py` both default to `edtech` and `README.md` creates that tenant
#: explicitly. Either the import landed in `edtech` and `verify` read `default`
#: and found zeros, or it landed in `default` and the walkthrough opened on an
#: empty graph.
DEFAULT_GRAPH = "edtech"


class Refused(RuntimeError):
    """The engine would not do what the snapshot needs."""


def _count(engine: Engine, query: str) -> int:
    """One count, or a refusal.

    **Never `or 0`.** `int(rows[0][0]) if rows and rows[0] else 0` turned "I
    could not measure this" into "the graph holds none of these" — and the
    pre-import guard is built on this function, so an unreadable answer read
    as an empty engine and the import merged into somebody's graph.
    `Engine.scalar` exists to keep those apart.
    """
    answered = engine.scalar(query)
    if answered is None:
        raise Refused(
            f"{engine.url} did not answer a count for `{query}`, so what the "
            f"graph holds could not be measured. Refusing rather than reading "
            f"an unmeasurable graph as an empty one.")
    try:
        return int(answered)
    except (TypeError, ValueError) as unreadable:
        raise Refused(
            f"{engine.url} answered {answered!r} to `{query}`, which is not a "
            f"number.") from unreadable

#: The same four edges with their end labels, so the reverse expansion can be
#: written with both ends bound. `both_directions` needs the HEAD label to
#: force the planner to start there and walk the edge backwards.
EDGE_ENDS = (
    ("REQUIRES", "Course", "Course"),
    ("IN_SUBJECT", "Course", "Subject"),
    ("INCLUDES", "Pathway", "Course"),
    ("HAS_REQUIREMENT", "Course", "Requirement"),
)


def storage_reported(url: str) -> dict:
    """What `/api/status` says the instance holds — recorded, not trusted."""
    try:
        with urllib.request.urlopen(f"{url.rstrip('/')}/api/status",
                                    timeout=30) as answer:
            return (json.loads(answer.read() or b"{}") or {}).get("storage", {})
    except (urllib.error.URLError, TimeoutError, OSError) as gone:
        raise Refused(f"{url}/api/status: {gone}") from gone


def both_directions(url: str, graph: str = DEFAULT_GRAPH) -> dict:
    """Every edge type counted directed AND undirected.

    **This is what tells the two readings of 2,834 apart**, and the first
    version of this measurement recorded neither.

    Reading (a): `/api/status` double-counts edges on a Cypher-loaded graph.
    Reading (b): it counts stored adjacency entries, two per edge, and the
    IMPORTED graph holds only one — under which the endpoint is right and the
    import is lossy. `verify` cannot separate them, because it only ever asks
    `()-[r:T]->()`, which is identical under both.

    **The undirected count alone does NOT separate them**, and an earlier
    version of this docstring claimed it did. Undirected comes back at
    exactly 2x directed for all four types on both engines — 480/240,
    1446/723, 632/316, 276/138, no self-loop residue, no exceptions. That is
    the signature of a query-level doubling rule at least as much as of a
    traversal over stored entries, and if it is doubling then this function
    discriminates nothing.

    **The INBOUND expansion does separate them**, because it does not depend
    on undirected semantics at all. `MATCH (c:Course)<-[r:INCLUDES]-(p:Pathway)`
    starts at a Course and walks the edge backwards. Under (b) — one stored
    adjacency entry per edge, held at the tail — the imported graph could not
    answer it from a Course start. Measured on 1.1.0: both engines answer
    316, and 240 for the reverse of REQUIRES. So (b) is excluded.

    It is also the query the demo's correctness already rests on:
    `demo/demo.py:213` runs this pattern and `docs/questions.md:115` makes
    the reverse edge a supported question.

    `storage.nodes` matching at 1,098 is NOT evidence here — (b) predicts
    matching node counts too. It reads as corroboration and is not.
    """
    engine = Engine(url, graph=graph)
    directed, undirected, inbound = {}, {}, {}
    for kind, tail, head in EDGE_ENDS:
        name = identifier(kind)
        directed[kind] = _count(
            engine, f"MATCH ()-[r:{name}]->() RETURN count(r)")
        undirected[kind] = _count(
            engine, f"MATCH ()-[r:{name}]-() RETURN count(r)")
        # Planner-forced reverse expansion: the HEAD label is bound first and
        # the edge is walked backwards to the tail.
        inbound[kind] = _count(
            engine, f"MATCH ({identifier(head).lower()[:1]}:{identifier(head)})"
                    f"<-[r:{name}]-(:{identifier(tail)}) RETURN count(r)")
    return {"directed": directed, "undirected": undirected,
            "inbound": inbound,
            "directed_total": sum(directed.values()),
            "undirected_total": sum(undirected.values()),
            "inbound_total": sum(inbound.values())}

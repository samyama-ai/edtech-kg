"""How the engine REPORTS its edges, held to what it holds.

Split out of `tests/test_snapshot.py` at the 500-line review limit, and split
by SUBJECT, mirroring the split already made in `etl/`. That file drives a
snapshot round trip; this one drives the measurement that decides whether
`/api/status` may be trusted about edges — a question about the ENGINE, true
with no snapshot involved.

**`/api/status` IS THE WRONG PLACE TO READ EDGE COUNTS**, and it is the
obvious place. Measured on 1.1.0, two engines side by side holding the same
graph — one built by Cypher `CREATE`, one imported from the snapshot taken
from it:

    /api/status edges     Cypher-loaded 2,834      imported 1,417
    per-type Cypher       both 1,417 (240 + 723 + 316 + 138)
    reverse expansion     both 1,417

The reverse expansion is the reading that matters: it excludes the
alternative, in which the endpoint is right and the IMPORT dropped half the
adjacency. The undirected count does not — it is exactly twice directed
everywhere, which is as much a doubling rule as a traversal.
"""

from __future__ import annotations

from etl import snapshot


class Graph:
    """An engine answering fixed counts, so `counts` can be driven.

    `scalar` as well as `run`: `counts` reads through `Engine.scalar` now, so
    that "I could not measure this" and "the graph holds none of these" stay
    apart — the pre-import guard is built on it.
    """

    def __init__(self, held=None, url="http://engine.test"):
        self.held = held or {}
        self.asked = []
        self.url = url

    def run(self, statement):
        self.asked.append(statement)
        for name, n in self.held.items():
            if f":{name})" in statement or f":{name}]" in statement:
                return {"records": [[n]]}
        return {"records": [[0]]}

    def scalar(self, statement):
        rows = self.run(statement).get("records") or []
        return rows[0][0] if rows and rows[0] else None


def test_counts_never_ask_api_status():
    """**The trap.** `/api/status` reports 2,834 edges for a graph holding
    1,417 when that graph was built by Cypher, and 1,417 for the same graph
    imported from a snapshot. Either number is right about something; neither
    is right about both, so the check cannot use it.
    """
    engine = Graph({"Course": 791, "REQUIRES": 240})
    snapshot.counts(engine)
    assert engine.asked, "counts asked the engine nothing"
    for statement in engine.asked:
        assert "status" not in statement.lower()
        assert statement.startswith("MATCH"), statement


def test_both_directions_asks_all_three_shapes():
    """**The undirected query mutated green.** Flipping `]-()` to `]->()`
    changed nothing in the suite, and that function backs the whole card
    paragraph — collapsed into two copies of one count, the record would say
    1,417 undirected and the argument would be gone with nothing noticing.
    The inbound form is the one that actually discriminates, so it is pinned
    hardest.
    """
    engine = Graph({"REQUIRES": 240, "IN_SUBJECT": 723,
                    "INCLUDES": 316, "HAS_REQUIREMENT": 138})
    # Patched on `etl.edge_count_readings`, where `both_directions` now
    # lives and resolves its own `Engine` — patching the name re-exported by
    # `etl.snapshot` changes nothing the function reads.
    import etl.edge_count_readings as ecr
    original, seen = ecr.Engine, []
    ecr.Engine = lambda url, graph=None: seen.append(graph) or engine
    try:
        ecr.both_directions("http://engine.test")
    finally:
        ecr.Engine = original
    assert seen == ["edtech"], f"both_directions read graph {seen}"
    outbound = [q for q in engine.asked if "]->()" in q]
    undirected = [q for q in engine.asked if "]-()" in q and "]->()" not in q]
    inbound = [q for q in engine.asked if "<-[" in q]
    assert len(outbound) == 4, engine.asked
    assert len(undirected) == 4, (
        "the undirected counts are not being asked undirected")
    assert len(inbound) == 4, (
        "the reverse expansion — the reading that excludes a lossy import — "
        "is not being asked")

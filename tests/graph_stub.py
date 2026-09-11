"""An engine answering fixed counts, so `etl/snapshot.py` can be driven.

Shared because three test files needed it — `test_snapshot`,
`test_snapshot_properties` and `test_edge_count_readings` — and three copies
of a stub is how they drift into disagreeing about what an engine does.

`scalar` as well as `run`: `counts` reads through `Engine.scalar` so that
"I could not measure this" and "the graph holds none of these" stay apart.
The pre-import guard is built on that distinction.
"""

from __future__ import annotations


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

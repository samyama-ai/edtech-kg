"""The Completion key, and the guard protecting the day it changed.

Split out of `etl/load_education.py` at the 500-line review limit, and split
by SUBJECT: that module decides what a load writes, this one decides how a
completion is IDENTIFIED — and identity is the thing a re-run depends on.

Six parts, `majornum` among them: without it, 16,800 Completion nodes
disappear in this slice and 3,524 of those merges also lose an award count.

The CIP part is hashed in its CANONICAL form. It was hashed as `str()`
produced it, which dropped the leading zero from every code below `10.0000` —
so the key changed when that was fixed, and `refuse_a_graph_keyed_the_old_way`
exists because idempotence measured against one key does not transfer to
another.
"""

from __future__ import annotations

import hashlib

from etl.cip import cip_code
from etl.engine import Engine, Refused
from etl.graph_writer import quote

#: The data year. Part of the key, so it is defined once, here — the
#: loader imports it rather than keeping its own copy.
YEAR = 2022

#: How many ids to try before deciding a graph was keyed differently.
#: One match proves the keys agree; a graph loaded by this version
#: matches on the first.
SAMPLE_FOR_KEY_CHECK = 25


def completion_id(row: dict) -> str:
    """The Completion key, spelled exactly as `schema/edtech_kg.cypher` does.

    Six parts. `majornum` is one of them: without it,
    16,800 Completion nodes disappear in this slice, and
    3,524 of those merges also lose an award count.
    Measured by `etl/probe_completion_key.py` — these figures were in three
    files and no run, and two of them were the same number wearing different
    labels.
    """
    parts = (row["unitid"], cip_code(row["cipcode_6digit"]), row["award_level"],
             row["majornum"], row["race"], row["sex"], YEAR)
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()


def refuse_a_graph_keyed_the_old_way(engine: Engine, completions: list[dict],
                                     dry_run: bool = False) -> None:
    """Refuse a graph whose Completion ids were built the old way.

    **`completion_id` hashes the NORMALISED CIP now**, so every id in this
    slice differs from the one the previous version produced. That is correct
    — the key should be built from the canonical form — but it means the
    idempotence this loader measures holds only against a graph loaded by
    THIS version.

    Run it over a graph built by the previous code and every lookup misses:
    a second full set of about 51,000 Completion nodes lands beside the old
    ones, `already_present` reports 0, and nothing raises. The loader's whole
    selling point is that idempotence is measured, and this is the one case
    where the measurement does not transfer — so it is refused rather than
    documented and hoped for.

    Sampled rather than counted in full: if the graph holds completions and
    NONE of a sample of the ids this run would write is already there, the
    ids were built differently. A graph loaded by this version matches on the
    first one.
    """
    if dry_run or not completions:
        return
    held = engine.scalar("MATCH (c:Completion) WITH c RETURN count(c)")
    if held is None or not int(held):
        return
    for row in completions[:SAMPLE_FOR_KEY_CHECK]:
        found = engine.scalar(
            f"MATCH (c:Completion) WHERE c.id = {quote(completion_id(row))} "
            f"WITH c RETURN count(c)")
        if found and int(found):
            return
    raise Refused(
        0,
        f"{engine.url} holds {int(held):,} Completion nodes and none of them "
        f"carries an id this version would write. The key changed when CIP "
        f"codes were normalised, so loading over this graph would add a "
        f"second full set beside the first rather than matching it. Drop the "
        f"Completion nodes, or point this at a fresh graph.")

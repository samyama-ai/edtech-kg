"""The three defects `engine-behaviours.md` records from prose, made runnable.

    python -m etl.probe_engine_defects --url http://localhost:8224
    python -m etl.probe_engine_defects --url ... --record

`docs/engine-behaviours.md` closes by naming this as the obvious next step:
`probe_engine_capability` covers the query constructs, and **`REMOVE`, `tenant`
and the `MERGE` index behaviour are recorded from the issues that measured
them** — in shells, by hand, which is the one thing this repo says a figure may
never be.

Three defects, all in the "wrong answer, no error" class:

  * **#163 — a removed property is gone from the row and still returned by
    every read.** The issue calls REMOVE a silent no-op; the whole-row read
    this module's docstring promised, and the first version never took, shows
    otherwise. `REMOVE` DOES change the stored node — the key disappears from
    it — while a projection, a projection behind a `WITH`, a projection with
    no `WHERE`, and a `WHERE p.k = ...` filter all keep answering with the
    pre-write value. That is worse than the issue describes, not milder: an
    export shows the property gone while every query still finds it.
  * **#149 — `tenant` is ignored on `/api/query`.** Every tenant sees one
    graph, including a tenant that has never existed. Creating one returns 201
    and dropping one returns 204, so the API accepts the calls and scopes
    nothing.
  * **#169 — `MERGE` ignores the constraint's index and scans.** Write rate
    falls roughly as 1/n while `MATCH` on the same constrained property stays
    flat, which turns bulk loading from linear into quadratic.

**This probe needs an engine it may write to and corrupt.** It creates nodes,
tries to delete them, and deliberately leaves a graph whose tenant separation
does not work. Point it at a scratch instance, never at `:8200`:

    docker run -d --name sg-defects -p 8224:8080 \\
        public.ecr.aws/f9f6l5u4/samyama-graph:1.1.0

**A defect that has been FIXED must fail loudly, not quietly pass.** Every
check below records what it observed and whether that still matches the
recorded defect, so an engine upgrade that fixes one shows up as a changed
record rather than as a probe that prints nothing.
"""

from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import sys
import urllib.error
import urllib.request

from etl.engine import Engine, Refused
from etl.engine_bench import (FULL_SIZES, SIZES,
                              merge_ignores_the_index)
from etl.provenance import write_record

ROOT = pathlib.Path(__file__).resolve().parents[1]
RECORD = ROOT / "docs" / "sources" / "engine-defects-measured.json"
RECORD_NOTE = ("Measured by `python -m etl.probe_engine_defects --record` "
               "against a SCRATCH engine. Each entry says what was observed "
               "and whether the defect it was written for is still present.")

#: Deliberately not the engine's own label names. A scratch label keeps the
#: MERGE timings honest — #169's own control is that the same statement against
#: a nearly-empty label runs at full speed, so measuring into a label something
#: else has filled would report the other thing's size.
LABEL = "DefectProbe"

#: The image these findings were measured against. A DEFAULT for `--image`,
#: not a fact the probe establishes — nothing in the API reports it.
DEFAULT_IMAGE = "public.ecr.aws/f9f6l5u4/samyama-graph:1.1.0"


class Unusable(RuntimeError):
    """The engine refused something the probe needs in order to measure."""


def api(url: str, path: str, method: str = "GET",
        payload: dict | None = None) -> tuple[int, dict | None]:
    """One raw API call, returning the STATUS as well as the body.

    `Engine` is the right client for queries and is used for them. This exists
    because #149 is a claim about status codes — that create returns 201 and
    drop returns 204 while neither scopes anything — and a client that raises
    on status has thrown that evidence away before the probe can read it.
    """
    body = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        f"{url.rstrip('/')}{path}", data=body, method=method,
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            return response.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as refused:
        raw = refused.read()
        try:
            return refused.code, json.loads(raw) if raw else None
        except json.JSONDecodeError:
            return refused.code, None
    except (urllib.error.URLError, TimeoutError, OSError) as gone:
        raise Unusable(f"{path}: {gone}") from gone


def one(engine: Engine, cypher: str) -> list:
    """One query's records, or [] — never None, so callers can index safely."""
    return engine.run(cypher).get("records") or []


def scalar(engine: Engine, cypher: str):
    """The first cell of the first row, or None.

    Careful about the engine's own trap: a bare aggregate returns one row over
    an EMPTY graph, so `records != []` is not an emptiness check here and the
    value has to be read rather than the row counted.
    """
    rows = one(engine, cypher)
    return rows[0][0] if rows and rows[0] else None


def remove_is_a_no_op(engine: Engine) -> dict:
    """#163 — does `REMOVE` remove anything?

    Read back three ways, because a single projection could be served from a
    cache and the finding would then be about caching rather than about
    REMOVE. A projection, a count-by-value and a whole-row read have to agree.

    The first version of this docstring promised three and `readings()`
    returned two — the whole-row read was described and never taken.
    """
    key = "probe://remove/1"
    engine.run(f'CREATE (p:{LABEL} {{url: "{key}", kind: "gone-please"}})')

    def readings() -> dict:
        # A whole-row read too. A projection asks the engine for one
        # property and could be answered from a cache of that projection; the
        # node itself carries whatever it carries.
        rows = one(engine, f'MATCH (p:{LABEL}) WHERE p.url = "{key}" RETURN p')
        node = rows[0][0] if rows and rows[0] else None
        # The engine returns a node as {id, labels, properties}. Reading
        # `"kind" in node` looks right and is always False — the first version
        # did exactly that, and reported REMOVE as FIXED while the printout
        # above it showed the property plainly surviving. A defect probe
        # reporting a false ABSENCE is its worst available outcome, and this
        # one got there by guessing at a payload shape instead of reading it.
        props = (node or {}).get("properties") if isinstance(node, dict) else None
        return {
            "projection": scalar(
                engine, f'MATCH (p:{LABEL}) WHERE p.url = "{key}" RETURN p.kind'),
            "count_by_value": scalar(
                engine, f'MATCH (p:{LABEL}) WHERE p.kind = "gone-please" '
                        f'RETURN count(p)'),
            "row_has_the_key": isinstance(props, dict) and "kind" in props,
            "row_value": (props or {}).get("kind"),
        }

    before = readings()
    engine.run(f'MATCH (p:{LABEL}) WHERE p.url = "{key}" REMOVE p.kind')
    after_remove = readings()

    # The sharpest form: the same statement is asked to return what it has
    # just claimed to remove.
    returned = scalar(
        engine, f'MATCH (p:{LABEL}) WHERE p.url = "{key}" '
                f'REMOVE p.kind RETURN p.kind')

    # `SET x = null` is the other spelling people reach for when REMOVE fails.
    engine.run(f'MATCH (p:{LABEL}) WHERE p.url = "{key}" SET p.kind = null')
    after_set_null = readings()

    stale = reads_disagree_with_the_row(before, after_remove)
    return {
        "issue": 163,
        "before": before,
        "after_remove": after_remove,
        "remove_then_return_gave": returned,
        "after_set_null": after_set_null,
        # The finding, as a boolean, so a fix is a CHANGED RECORD rather than
        # a probe that quietly prints different prose.
        # Named for what was measured. "survives" was the issue's framing and
        # the measurement does not support it — the ROW loses the key while
        # every read keeps returning the old value.
        "reads_stale_after_remove": stale,
        "reads_stale_after_set_null":
            reads_disagree_with_the_row(before, after_set_null),
        "row_lost_the_key_on_remove": not after_remove["row_has_the_key"],
        "remove_is_a_no_op_on_the_row": after_remove["row_has_the_key"]
                                        and after_remove["row_value"] is not None,
        # Untestable here: the container mounts no volume, so a restart empties
        # the graph and the re-read answers about nothing. Recorded as unknown
        # rather than guessed at.
        "staleness_survives_restart": None,
        "still_defective": stale,
    }


def reads_disagree_with_the_row(before: dict, after: dict) -> bool:
    """**The defect, stated the way the measurement actually supports it.**

    #163 says REMOVE "parses, matches, reports success and changes nothing".
    Adding the whole-row read that this module's docstring had promised and
    never taken shows that is not what happens. Measured on 1.1.0:

        after CREATE      row: key present, 'keep'   projection 'keep'
        after REMOVE      row: KEY GONE              projection 'keep'
        after SET = null  row: key back, null        projection 'keep'

    So REMOVE *does* change the stored node. What does not change is what any
    property READ returns — a projection, a projection behind a `WITH`, a
    projection with no `WHERE` at all, and a `WHERE p.kind = ...` filter all
    keep answering with the pre-write value, while `WHERE p.kind IS NULL`
    matches nothing.

    That is a worse defect than the issue describes rather than a milder one:
    the graph and the answers disagree, so an export shows the property gone
    while every query still finds it.

    **Whether this is a cache is NOT established.** The obvious test — restart
    and re-read — is void here: the container holds no volume, so a restart
    empties the graph and the re-read is answering about nothing. It is
    recorded as unknown rather than guessed at.

    True when a read still reports what the row no longer holds.
    """
    if before["projection"] is None:
        # Nothing was there to survive; the measurement is void, not negative.
        return False

    # Spelled out, one named condition at a time. The first version of this
    # was a chained `a == b is not None`, and its replacement was
    # `A and B and not C or D` — which parses as `(A and B and not C) or D`
    # and is not what it reads as. Both are the same mistake: a verdict a
    # reviewer cannot check by looking at it.
    projection_is_stale = after["projection"] == before["projection"]
    filter_is_stale = after["count_by_value"] == before["count_by_value"]
    row_no_longer_holds_it = (not after["row_has_the_key"]
                              or after["row_value"] is None)
    return projection_is_stale and filter_is_stale and row_no_longer_holds_it


def tenant_is_ignored(url: str, engine: Engine) -> dict:
    """#149 — does `tenant` on /api/query scope anything?

    Asks for a count under four tenants including one that has never existed.
    The status codes are recorded too: the claim is not that the API rejects
    the calls, it is that it accepts them and scopes nothing, and only the
    codes distinguish those.
    """
    engine.run(f'CREATE (t:{LABEL} {{url: "probe://tenant/1"}})')
    baseline = scalar(engine, f"MATCH (n:{LABEL}) WITH n RETURN count(n)")

    # BOTH `id` and `name`. Sending only `id` returns 422 "missing field
    # `name`" — which the first version of this probe recorded as the API
    # refusing the call, contradicting #149's report of a 201. The issue was
    # right and the probe was measuring its own bug. A defect probe that
    # reports a false ABSENCE of a defect is the worst outcome available to
    # it, so the payload the engine documents is used and the status is
    # asserted below rather than merely stored.
    created, _ = api(url, "/api/tenants", "POST",
                     {"id": "probe-scratch", "name": "probe-scratch"})
    if created != 201:
        raise Unusable(
            f"creating a tenant answered {created}, not 201. #149's claim is "
            f"that the API ACCEPTS these calls and scopes nothing; if it no "
            f"longer accepts them the finding needs re-stating, not "
            f"re-recording.")
    counts = {}
    for tenant in ("default", "probe-scratch", "nonexistent-tenant-xyz"):
        status, body = api(url, "/api/query", "POST", {
            "query": f"MATCH (n:{LABEL}) WITH n RETURN count(n)",
            "tenant": tenant})
        records = (body or {}).get("records") or []
        counts[tenant] = records[0][0] if records and records[0] else None
    dropped, _ = api(url, "/api/tenants/probe-scratch", "DELETE")
    after_drop = scalar(engine, f"MATCH (n:{LABEL}) WITH n RETURN count(n)")

    seen = set(counts.values())
    return {
        "issue": 149,
        "baseline": baseline,
        "counts_by_tenant": counts,
        "create_status": created,
        "delete_status": dropped,
        "nodes_after_dropping_the_tenant": after_drop,
        "every_tenant_sees_one_graph": len(seen) == 1 and baseline in seen,
        # The compounding consequence: dropping a tenant does not drop data.
        "dropping_a_tenant_deleted_nothing": after_drop == baseline,
        "still_defective": len(seen) == 1 and baseline in seen,
    }


def measure(url: str, full: bool = False, image: str = DEFAULT_IMAGE) -> dict:
    engine = Engine(url)
    status, body = api(url, "/api/status")
    if status != 200:
        raise Unusable(f"{url} answered {status} at /api/status")
    nodes = ((body or {}).get("storage") or {}).get("nodes")
    if nodes:
        # REFUSED, not a warning. This probe writes tens of thousands of nodes
        # and cannot remove them (that is defect #163), so running it against
        # a loaded graph corrupts the graph — which is exactly how :8200 came
        # to hold four copies of one district (#149).
        raise Unusable(
            f"{url} already holds {nodes} nodes. This probe writes and cannot "
            f"clean up — point it at a scratch engine:\n"
            f"  docker run -d --name sg-defects -p 8224:8080 "
            f"public.ecr.aws/f9f6l5u4/samyama-graph:1.1.0")

    return {
        "_": RECORD_NOTE,
        # `retrieved_at` and `engine_version_reported`, matching
        # `engine-capability-measured.json`. The two records describe the same
        # engine and were written with different key names for the same two
        # facts, so a consumer reading both had to know which probe wrote
        # which.
        "retrieved_at": datetime.datetime.now(datetime.timezone.utc)
                                .strftime("%Y-%m-%d"),
        # **An assertion by whoever ran this, not a measurement.** The engine
        # does not report the image it came from, so this was a literal in the
        # source and would have quietly claimed 1.1.0 for a run against any
        # other build. It is a flag now, and the key says what it is.
        "image_asserted": image,
        # The tag and the binary disagree, and a figure attributed to a tag
        # cannot be checked against a version the engine does not admit to.
        # This one IS observed.
        "engine_version_reported": (body or {}).get("version"),
        "url": url,
        "remove": remove_is_a_no_op(engine),
        "tenant": tenant_is_ignored(url, engine),
        "merge": merge_ignores_the_index(engine,
                                         FULL_SIZES if full else SIZES),
    }


def report(measured: dict) -> None:
    print(f"  image asserted {measured['image_asserted']}, engine reports "
          f"{measured['engine_version_reported']}\n")
    for key, title in (("remove", "#163  REMOVE"),
                       ("tenant", "#149  tenant"),
                       ("merge", "#169  MERGE index")):
        found = measured[key]
        verdict = "STILL DEFECTIVE" if found["still_defective"] else "FIXED"
        print(f"  {title:<22} {verdict}")

    remove = measured["remove"]
    after = remove["after_remove"]
    print(f"\n  REMOVE: the ROW lost the key "
          f"({remove['row_lost_the_key_on_remove']}), and every READ still "
          f"returns {after['projection']!r} — "
          f"projection {after['projection']!r}, "
          f"filter matched {after['count_by_value']}, "
          f"REMOVE..RETURN gave {remove['remove_then_return_gave']!r}")

    tenant = measured["tenant"]
    print(f"  tenant: create {tenant['create_status']}, "
          f"delete {tenant['delete_status']}, counts "
          f"{tenant['counts_by_tenant']}")

    print("\n  nodes in label |    MERGE |   CREATE |    MATCH   (per sec)")
    for point in measured["merge"]["points"]:
        print(f"  {point['nodes_at_start']:>14,} | {point['merge_per_sec']:>8} "
              f"| {point['create_per_sec']:>8} | {point['match_per_sec']:>8}")
    print(f"  MERGE into a fresh label: "
          f"{measured['merge']['merge_into_a_fresh_label_per_sec']}/sec")
    print(f"  over that range MERGE fell {measured['merge']['merge_fell_by']}x, "
          f"MATCH {measured['merge']['match_fell_by']}x")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m etl.probe_engine_defects")
    parser.add_argument("--url", default="http://localhost:8224",
                        help="A SCRATCH engine. It will be written to.")
    parser.add_argument("--full", action="store_true",
                        help=f"Sample to {FULL_SIZES[-1]:,} nodes rather than "
                             f"{SIZES[-1]:,}. Slow.")
    parser.add_argument("--image", default=DEFAULT_IMAGE,
                        help="Recorded as an assertion — the engine does not "
                             "report which image it came from.")
    parser.add_argument("--record", action="store_true")
    args = parser.parse_args(argv)

    try:
        measured = measure(args.url, full=args.full, image=args.image)
    except Unusable as gone:
        print(f"unusable: {gone}", file=sys.stderr)
        return 2
    except Refused as refused:
        print(f"the engine refused a statement the probe needs: {refused}",
              file=sys.stderr)
        return 3

    report(measured)
    if args.record:
        write_record(RECORD, measured)
        print(f"\n  -> {RECORD.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

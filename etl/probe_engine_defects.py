"""The three defects `engine-behaviours.md` records from prose, made runnable.

    python -m etl.probe_engine_defects --url http://localhost:8224
    python -m etl.probe_engine_defects --url ... --record

`docs/engine-behaviours.md` closes by naming this as the obvious next step:
`probe_engine_capability` covers the query constructs, and **`REMOVE`, `tenant`
and the `MERGE` index behaviour are recorded from the issues that measured
them** — in shells, by hand, which is the one thing this repo says a figure may
never be.

Three defects, all in the "wrong answer, no error" class:

  * **#163 — `REMOVE` is a silent no-op.** It parses, matches the node, returns
    it, reports success, and the property is unchanged. `REMOVE p.k RETURN p.k`
    returns the value it has just claimed to remove.
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
import time
import urllib.error
import urllib.request

from etl.engine import Engine, Refused
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
    """
    key = "probe://remove/1"
    engine.run(f'CREATE (p:{LABEL} {{url: "{key}", kind: "gone-please"}})')

    def readings() -> dict:
        return {
            "projection": scalar(
                engine, f'MATCH (p:{LABEL}) WHERE p.url = "{key}" RETURN p.kind'),
            "count_by_value": scalar(
                engine, f'MATCH (p:{LABEL}) WHERE p.kind = "gone-please" '
                        f'RETURN count(p)'),
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

    survived = after_remove["projection"] == before["projection"] is not None
    return {
        "issue": 163,
        "before": before,
        "after_remove": after_remove,
        "remove_then_return_gave": returned,
        "after_set_null": after_set_null,
        # The finding, as a boolean, so a fix is a CHANGED RECORD rather than
        # a probe that quietly prints different prose.
        "property_survives_remove": survived,
        "property_survives_set_null":
            after_set_null["projection"] == before["projection"] is not None,
        "still_defective": survived,
    }


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
    # refusing the call, contradicting #169's report of a 201. The issue was
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


#: Label sizes at which the write rate is sampled. #169 measured to 37,141 and
#: found the fall continues; this stops at 8,000 so a probe run costs about a
#: minute rather than an hour. **The trend is the finding, not the endpoint** —
#: a 1/n fall is visible across this range, and `--full` extends it for anyone
#: re-measuring the published table.
SIZES = (1000, 4000, 8000, 16000)
FULL_SIZES = SIZES + (32000,)

#: Writes timed at each size. The first version used 40 and the result was not
#: usable: MERGE came out FASTER at 2,000 nodes than at 500, which is the
#: opposite of the finding, because forty round trips is short enough for
#: process warm-up to dominate. Raised, and every timing is preceded by an
#: untimed warm-up of the same statement shape.
BATCH = 150
WARMUP = 30


def rate(engine: Engine, statement, count: int) -> float:
    """Writes per second for `count` calls of `statement(i)`.

    Wall clock over the whole batch rather than a per-call mean: the figure
    that matters for a bulk load is throughput, and a mean of per-call times
    hides the round trip that dominates it.
    """
    # Warm up OUTSIDE the timer, with the same statement shape. The engine
    # caches parsed ASTs and chosen plans, so the first call of a shape pays
    # for parsing and planning that none of the rest do — and at small batch
    # sizes that single call decided the rate.
    for i in range(-WARMUP, 0):
        engine.run(statement(i))
    start = time.perf_counter()
    for i in range(count):
        engine.run(statement(i))
    elapsed = time.perf_counter() - start
    return round(count / elapsed, 1) if elapsed else 0.0


def merge_ignores_the_index(engine: Engine, sizes=SIZES) -> dict:
    """#169 — does `MERGE` use the constraint's index?

    Three rates at each size, on the SAME label and the same key:

      * `MERGE` on the constrained property — the one under suspicion
      * `CREATE` into the label, doing no lookup at all — the floor
      * `MATCH … WHERE key = …`, which does the same lookup MERGE needs

    If MERGE used the index it would track MATCH. The control that isolates
    the cause is the fourth: the same MERGE statement against a fresh, nearly
    empty label. #169 measured that at full speed, which is what shows the
    cost belongs to the size of the label being merged into rather than to the
    statement.
    """
    engine.run(f"MATCH (n:{LABEL}Bench) DETACH DELETE n")
    try:
        engine.run(f"CREATE CONSTRAINT ON (n:{LABEL}Bench) "
                   f"ASSERT n.id IS UNIQUE")
    except Refused:
        # Already declared, or the engine refuses a re-declaration. Either way
        # the index either exists or does not, and the measurement below is
        # what decides — so this is not fatal and is recorded, not swallowed.
        pass

    filled, points = 0, []
    for size in sizes:
        # Fill up to `size` with CREATE, which #169 measured as flat — so the
        # fill itself does not decide the rates being compared.
        while filled < size:
            engine.run(f'CREATE (n:{LABEL}Bench {{id: "fill-{filled}"}})')
            filled += 1

        merge_rate = rate(
            engine, lambda i, s=size: f'MERGE (n:{LABEL}Bench '
                                     f'{{id: "m-{s}-{i}"}})', BATCH)
        create_rate = rate(
            engine, lambda i, s=size: f'CREATE (n:{LABEL}Bench '
                                     f'{{id: "c-{s}-{i}"}})', BATCH)
        match_rate = rate(
            engine, lambda i, s=size: f'MATCH (n:{LABEL}Bench) '
                                     f'WHERE n.id = "fill-{i}" '
                                     f'WITH n RETURN n.id', BATCH)
        # Every timed CREATE and MERGE above added a node, and so did their
        # warm-ups. Counted rather than estimated: an undercount here makes
        # the NEXT size fill fewer nodes than it reports, and the whole table
        # is a claim about label size.
        filled += 2 * (BATCH + WARMUP)
        points.append({"nodes_in_label": size, "merge_per_sec": merge_rate,
                       "create_per_sec": create_rate,
                       "match_per_sec": match_rate})

    # The isolating control: identical MERGE, nearly empty label.
    engine.run(f"MATCH (n:{LABEL}Fresh) DETACH DELETE n")
    fresh = rate(engine, lambda i: f'MERGE (n:{LABEL}Fresh {{id: "f-{i}"}})',
                 BATCH)

    first, last = points[0], points[-1]
    return {
        "issue": 169,
        "batch": BATCH,
        "points": points,
        "merge_into_a_fresh_label_per_sec": fresh,
        "merge_fell_by": round(first["merge_per_sec"] / last["merge_per_sec"], 1)
                         if last["merge_per_sec"] else None,
        "match_fell_by": round(first["match_per_sec"] / last["match_per_sec"], 1)
                         if last["match_per_sec"] else None,
        "still_defective": merge_is_still_defective(points),
    }


def merge_is_still_defective(points: list[dict]) -> bool:
    """MERGE degraded and MATCH did not. **Both halves are required.**

    A loaded machine slows everything, and that is not this bug — a verdict
    keyed on MERGE alone would report #169 present on any busy laptop. A
    verdict keyed on the ratio between them would report it present on an
    engine where MERGE had been fixed and MATCH had regressed.

    Its own function, not an expression inside the measurement, so the tests
    can drive THIS logic rather than a copy of it. A test that reimplements
    the rule it checks agrees with itself and proves nothing.

    Deliberately a shape test and not a threshold on a rate: absolute timings
    vary run to run, and a probe that fails when the machine is busy would be
    switched off.
    """
    if not points:
        return False
    first, last = points[0], points[-1]
    if not (first["merge_per_sec"] and last["merge_per_sec"]):
        return False
    return (last["merge_per_sec"] < first["merge_per_sec"] / 2
            and last["match_per_sec"] > first["match_per_sec"] / 2)


def measure(url: str, full: bool = False) -> dict:
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
        "measured_at": datetime.datetime.now(datetime.timezone.utc)
                               .strftime("%Y-%m-%d"),
        "image": "public.ecr.aws/f9f6l5u4/samyama-graph:1.1.0",
        # The tag and the binary disagree, and a figure attributed to a tag
        # cannot be checked against a version the engine does not admit to.
        "version_reported": (body or {}).get("version"),
        "remove": remove_is_a_no_op(engine),
        "tenant": tenant_is_ignored(url, engine),
        "merge": merge_ignores_the_index(engine,
                                         FULL_SIZES if full else SIZES),
    }


def report(measured: dict) -> None:
    print(f"  image tag 1.1.0, engine reports "
          f"{measured['version_reported']}\n")
    for key, title in (("remove", "#163  REMOVE"),
                       ("tenant", "#149  tenant"),
                       ("merge", "#169  MERGE index")):
        found = measured[key]
        verdict = "STILL DEFECTIVE" if found["still_defective"] else "FIXED"
        print(f"  {title:<22} {verdict}")

    remove = measured["remove"]
    print(f"\n  REMOVE: before {remove['before']['projection']!r}, "
          f"after {remove['after_remove']['projection']!r}; "
          f"REMOVE..RETURN gave {remove['remove_then_return_gave']!r}")

    tenant = measured["tenant"]
    print(f"  tenant: create {tenant['create_status']}, "
          f"delete {tenant['delete_status']}, counts "
          f"{tenant['counts_by_tenant']}")

    print("\n  nodes in label |    MERGE |   CREATE |    MATCH   (per sec)")
    for point in measured["merge"]["points"]:
        print(f"  {point['nodes_in_label']:>14,} | {point['merge_per_sec']:>8} "
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
    parser.add_argument("--record", action="store_true")
    args = parser.parse_args(argv)

    try:
        measured = measure(args.url, full=args.full)
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

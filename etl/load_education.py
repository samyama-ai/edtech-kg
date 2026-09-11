"""Load the national spine — programmes, occupations, institutions, completions.

    python -m etl.load_education --url http://localhost:8200
    python -m etl.load_education --url ... --dry-run     # count, write nothing

edtech-kg#7, on the slice edtech-kg#23 chose: **Virginia, 2022**. That
document did the arithmetic and this loader does not re-argue it.

**Every write is a lookup and a conditional CREATE, not a MERGE.** #169
measured `MERGE` ignoring the constraint's index and scanning, so its cost per
write grows with the label: 692/sec at 1,500 nodes, 35/sec at 37,141. Over a
190,770-row slice that is quadratic — about 3.8 hours against about 11 minutes
for the same work done as `MATCH`-then-`CREATE`, measured at 300/sec and flat.
`docs/first-load.md` records the measurement; this is the loader that acts on
it.

**Counts come from the graph, never from the input.** A loader that reports
what it issued has reported its own intentions. Every figure below is read
back with a `MATCH ... RETURN count(...)`, and the gap between issued and held
is reported rather than assumed to be zero — on this engine it is not always.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import time

from etl.engine import ENGINE_VERSION, Engine, Refused
from etl.graph_writer import Writer, quote  # noqa: F401
from etl.provenance import write_record

ROOT = pathlib.Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "education"
FIPS, YEAR = 51, 2022

#: Seconds between rate samples. A minute is short enough to show the shape
#: over a 25-minute load and long enough that the sampling costs nothing.
CURVE_EVERY = 60

#: The labels this loader writes, DECLARED rather than left to be inferred.
#:
#: `tests/test_the_declared_schema.py` derives "how many of the sixteen
#: labels hold nothing" by scanning the loaders for `(n:Label` — which works
#: for a loader that writes literal labels and is blind to one that
#: parameterises them, as this one does. It reported four written where the
#: answer is seven, so the dataset card would have understated the graph and
#: the check would have agreed with it.
WRITES = ("Institution", "Programme", "Completion")

RECORD = ROOT / "docs" / "sources" / "national-spine-measured.json"
RECORD_NOTE = (
    "Measured by `python -m etl.load_education --record`, which loads the "
    "slice TWICE: `issued`/`in_graph` are the first pass and `second_run` is "
    "the same load repeated against the graph it just made. `second_run."
    "nodes_and_edges_created` is the idempotence claim, and it is the "
    "loader's whole design — the first version created 2,000 duplicate edges "
    "on a second pass and only the gap column showed it.  `issued` is what "
    "this loader sent; `in_graph` is what the graph answered when asked "
    "afterwards. They are stored separately on purpose — a loader reporting "
    "only what it issued is reporting its own intentions, and on 1.1.0 a "
    "unique constraint does not reject a duplicate, so the two can differ "
    "with nothing raised. Every figure the dataset card and "
    "docs/national-spine.md quote about the load comes from here.")


def shown(path: pathlib.Path) -> pathlib.Path:
    """A path as a reader wants it — inside the repo, relative to it.

    `relative_to` RAISES on a path outside the tree rather than returning it
    unchanged, so a repointed cache or record turned a message into a
    ValueError. It happened twice here, once in a refusal and once in an
    argparse help string, and in both places the path was for a human.
    """
    try:
        return path.relative_to(ROOT)
    except ValueError:
        return path


class Missing(RuntimeError):
    """A downloaded table this loader needs is not in `data/`."""


def held(name: str, cache: pathlib.Path | None = None) -> dict:
    # **The cache is a PARAMETER, not a module global a test reassigns.**
    # The engine-backed tests repointed `loader.CACHE` around each call,
    # which is not concurrency-safe: under pytest-xdist two workers share the
    # module and one would read the other's slice.
    path = (cache or CACHE) / f"{name}-{FIPS}-{YEAR}.json"
    if not path.exists():
        raise Missing(
            f"{shown(path)} is not here. Run "
            f"`python -m etl.download_education` first — `data/` is "
            f"gitignored, so a fresh clone has none of it.")
    return json.loads(path.read_text(encoding="utf-8"))


#: IPEDS files an institution-level TOTAL under this code. It is not a
#: programme — it is the sum of the others — and loading it as one made
#: `sum(c.awards)` over the graph about twice the awards actually conferred.
#: Measured on Virginia 2022: 141,688 awards under `99` against 141,908 under
#: every real code combined, because the first is the total of the second.
GRAND_TOTAL_CIP = "99"


def cip_code(raw) -> str:
    """The CIP key, in ONE canonical form: six digits, zero-padded.

    **The API returns `cipcode_6digit` as an int**, so `str()` dropped the
    leading zero from every code below `10.0000` — `01.0000` arrived as
    `"10000"`. 70 of 664 `Programme` nodes carried a short key.

    That is not cosmetic. `docs/sources/cip-soc-crosswalk.md` keys on the
    dotted form (`01.0000`), so a join against a stripped code fails, and
    fails QUIETLY — the query returns rows, just fewer. Every programme whose
    CIP begins with zero drops out, about a tenth of them.

    Digits-only rather than dotted, because 594 of the 664 already-loaded
    nodes are digits-only and the crosswalk reader can drop a dot far more
    safely than this can invent one — it accepts both, so the join normalises
    on the way in rather than needing a second form stored here.
    """
    digits = str(raw).replace(".", "").strip()
    if not digits.isdigit():
        raise Refused(0, f"not a CIP code: {raw!r}")
    return digits.zfill(6)


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


#: Every field that reaches a Cypher literal, per table. Named rather than
#: discovered, because a field added to a write and not to this list is a
#: field the pre-flight silently stops covering.
WRITTEN_FIELDS = {
    "institutions": ("unitid", "inst_name", "state_abbr"),
    "completions": ("unitid", "cipcode_6digit", "award_level", "majornum",
                    "race", "sex", "awards_6digit"),
}


def refuse_unwritable(institutions: list[dict],
                      completions: list[dict] | None = None) -> None:
    """Raise if any value cannot be written, BEFORE the first write.

    **This covered institutions only, and its own docstring said "any".** Six
    completion fields reach a literal — `cipcode_6digit`, `award_level`,
    `majornum`, `race`, `sex`, `awards` — plus the Programme CIP, and a bad
    value in any of them raised at row 40,000. That is exactly the
    partial-graph-with-no-rollback case this function exists to close, still
    open through the larger of the two tables.

    They are numeric from the API today, so the exposure is low — but that
    argument was not written down and nothing asserted it, which is what made
    it a gap rather than a decision.

    There is no transaction here and no teardown, so discovering an
    unwritable value part-way leaves the graph part-loaded with no way back.
    (An earlier version of this said 1.1.0's scoped `DETACH DELETE` removes
    more than it names. That was measured and is FALSE — a scoped delete
    scopes; see the comment in `tests/test_load_education_engine.py`. The
    argument for checking first does not need it.)
    """
    for table, rows in (("institutions", institutions),
                        ("completions", completions or [])):
        for row in rows:
            for field in WRITTEN_FIELDS[table]:
                value = row.get(field)
                if value is not None:
                    quote(value)          # raises Refused, naming the value


def load(engine: Engine, dry_run: bool = False,
         only_awarded: bool = True, limit: int | None = None,
         cache: pathlib.Path | None = None) -> dict:
    """The spine, in dependency order — nodes before the edges that need them.

    `only_awarded` drops rows recording **zero** completions. Measured on
    this slice: 190,770 rows, of which 132,284 say nobody of that demographic
    finished that programme. Those are 69% of the volume and carry nothing a
    question asks for — "which programmes lead where" is not answered by a
    node saying nobody took one.

    It is a flag rather than a filter written into the walk, because it IS a
    scope decision: a zero row is a real IPEDS observation, and `--all-rows`
    loads them. The count of what was skipped is recorded either way, so the
    slice cannot be mistaken for the whole.
    """
    started = time.monotonic()
    writer = Writer(engine, dry_run)

    # **BOTH tables are read before either is written.** The old order wrote
    # all 147 institutions and only then called `held("completions")`, so a
    # missing completions cache exited 2 with institutions already in the
    # graph — the same partial-write this function's own comment says is
    # closed.
    institutions = held("institutions", cache)["rows"]
    completions = held("completions", cache)["rows"]
    # **CHECKED BEFORE ANYTHING IS WRITTEN.** A `quote()` refusal used to
    # raise part-way through, leaving a graph half loaded with no rollback —
    # this engine has no transaction to roll back to. One unwritable
    # institution name in a 58,317-row load would have left tens of thousands
    # of nodes behind and a non-zero exit, which is the worst of both.
    #
    # The scan is over the values that actually reach a literal, and it costs
    # a fraction of a second against a load measured in minutes.
    refuse_unwritable(institutions, completions)
    for row in institutions:
        writer.node("Institution", "unitid", row["unitid"],
                    {"unitid": row["unitid"], "name": row.get("inst_name") or "",
                     "state": row.get("state_abbr") or ""})

    # **The grand total is not a programme.** Dropped before anything else so
    # it cannot reach a node, an edge or a count. Recorded like the other two
    # skips rather than filtered silently — the slice must never be mistaken
    # for the whole, and a reader comparing this load to IPEDS's own published
    # total needs to know the total row is the thing that is missing.
    without_totals = [r for r in completions
                      if cip_code(r["cipcode_6digit"]) != cip_code(GRAND_TOTAL_CIP)]
    skipped_totals = len(completions) - len(without_totals)
    completions = without_totals

    skipped_zero = 0
    if only_awarded:
        keep = [r for r in completions if (r.get("awards_6digit") or 0) > 0]
        skipped_zero = len(completions) - len(keep)
        completions = keep
    if limit is not None:
        # `if limit:` read `--limit 0` as "no limit" and loaded the whole
        # slice. Zero is a legitimate request — "parse and write nothing" —
        # and answering it with 58,317 nodes is the opposite of what was
        # asked, on the flag whose purpose is to bound the write.
        completions = completions[:limit]

    programmes = sorted({cip_code(r["cipcode_6digit"]) for r in completions})
    for cip in programmes:
        writer.node("Programme", "cip_code", cip, {"cip_code": cip})

    # **The rate curve is part of the run, not a separate measurement.**
    # It was sampled by a second process polling the graph once a minute,
    # which meant the curve in the doc came from a DIFFERENT load than the
    # record beside it — two runs, quoted as one. The loader already knows
    # how many completions it has written and when it started; nothing has to
    # be asked of the engine to say so.
    curve: list[dict] = []
    last_mark = None
    next_mark = time.monotonic() + CURVE_EVERY

    seen: set[str] = set()
    for row in completions:
        key = completion_id(row)
        if key in seen:
            # The API returns rows that collapse onto one key — 169 of them
            # in this slice, printed by the load and not typed here from
            # memory. Skipping them rather than relying on the lookup keeps
            # the issued count honest.
            continue
        seen.add(key)
        # `major_number`, `race` and `sex` are properties as well as key
        # components. Keyed-only, the fix that split first-major from
        # second-major would be invisible in the graph: two Completion nodes
        # with equal `awards` and no readable difference between them, and no
        # question could ask "how many finished as a SECOND major".
        writer.node("Completion", "id", key, {
            "id": key, "year": YEAR,
            "cip_code": cip_code(row["cipcode_6digit"]),
            "award_level": row["award_level"],
            "major_number": row["majornum"],
            "race": row["race"], "sex": row["sex"],
            "awards": row.get("awards_6digit") or 0})
        writer.edge("AT", ("Completion", "id", key),
                    ("Institution", "unitid", row["unitid"]))
        writer.edge("IN", ("Completion", "id", key),
                    ("Programme", "cip_code", cip_code(row["cipcode_6digit"])))

        now = time.monotonic()
        if now >= next_mark:
            # Divided by the ELAPSED time, not by CURVE_EVERY. A sample
            # arrives when a row finishes, so the interval is "at least
            # CURVE_EVERY" and dividing by the nominal figure overstates the
            # rate by however long the last row took.
            since = now - (last_mark or started)
            written = len(seen)
            before = curve[-1]["completions_held"] if curve else 0
            curve.append({
                "seconds": round(now - started, 1),
                "completions_held": written,
                "completions_per_second": round((written - before) / since, 1)
                if since > 0 else None})
            last_mark, next_mark = now, now + CURVE_EVERY

    # **A final sample, so the curve reaches the total.** Without it the last
    # partial interval is never recorded: a 2,500-row run ended with the
    # curve at 2,449, and the reader could not see the rate the load actually
    # finished at — which is the end of the curve that matters, because it is
    # the one nearest the size a bigger slice would start from.
    finished = time.monotonic()
    # Not `if curve and …`: a load shorter than one sampling interval
    # recorded NO curve at all, so the run reporting the fewest figures was
    # the one a reader is most likely to be experimenting with.
    if seen and (not curve or curve[-1]["completions_held"] != len(seen)):
        since = finished - (last_mark or started)
        curve.append({
            "seconds": round(finished - started, 1),
            "completions_held": len(seen),
            "completions_per_second": round(
                (len(seen) - (curve[-1]["completions_held"] if curve else 0))
                / since, 1) if since > 0 else None})

    return {
        "seconds": round(time.monotonic() - started, 1),
        "statements_issued": writer.looked_up + writer.created,
        "nodes_and_edges_created": writer.created,
        "already_present": writer.already_there,
        "created_by": dict(writer.created_by),
        "institutions_in": len(institutions),
        "programmes_in": len(programmes),
        "completions_in": len(seen),
        "rows_skipped_zero_awards": skipped_zero,
        "rows_skipped_grand_total": skipped_totals,
        "duplicate_rows_skipped": (len(completions) - len(seen)),
        # Sampled once a minute across THIS run, so the curve and the totals
        # describe one load.
        "rate_curve": curve,
    }


def in_the_graph(engine: Engine) -> dict:
    """What the graph HOLDS — read back, never inferred from the input.

    A loader reporting what it issued has reported its own intentions. On
    this engine the two differ: a unique constraint does not reject a
    duplicate, so a double-issued CREATE leaves two nodes and no error.

    Every count interposes a `WITH`. An aggregate directly over a multi-node
    MATCH is only correct when the WHERE constrains the aggregated variable —
    `docs/engine-behaviours.md` measured 3,280 where 19,716 was due.
    """
    counts = {}
    # `WRITES`, not a second list of the same three labels. Two copies of
    # "what this loader writes" is one that can go stale — and the copy that
    # went stale would be the one the read-back uses, so a label written and
    # not counted would show as a clean load.
    for label in WRITES:
        rows = engine.run(
            f"MATCH (n:{label}) WITH n RETURN count(n)").get("records") or []
        counts[label] = rows[0][0] if rows and rows[0] else 0
    for kind in ("AT", "IN"):
        rows = engine.run(
            f"MATCH ()-[r:{kind}]->() RETURN count(r)").get("records") or []
        counts[kind] = rows[0][0] if rows and rows[0] else 0
    return counts


def report(loaded: dict, graph: dict, before: dict | None = None) -> list[str]:
    """What the graph held, what this run created, and what it holds now.

    **The gap is against BEFORE PLUS CREATED, not against what was issued.**
    Comparing a whole-graph label count with this run's issued count reports
    any pre-existing data — another year's completions, another state's — as
    a gap this run caused. On an empty engine the two readings agree, which is
    exactly why the wrong one survived: every run so far has been on a fresh
    container.

    `before` is optional so a dry run, which reads nothing back, still
    reports; it is treated as zero and the table says so.
    """
    lines = [
        f"  {loaded['statements_issued']:,} statements in "
        f"{loaded['seconds']}s "
        f"({round(loaded['statements_issued'] / max(loaded['seconds'], 0.1)):,}/sec)",
        f"  skipped {loaded['rows_skipped_zero_awards']:,} rows recording zero "
        f"awards, {loaded['duplicate_rows_skipped']:,} duplicate rows, "
        f"{loaded['rows_skipped_grand_total']:,} institution-total rows",
        "",
        f"  {'':<14} {'held before':>12} {'created':>9} {'in graph':>10}  gap",
    ]
    before = before or {}
    created = loaded.get("created_by") or {}
    for name in ("Institution", "Programme", "Completion", "AT", "IN"):
        was = before.get(name, 0)
        made = created.get(name, 0)
        holds = graph.get(name, 0)
        gap = holds - (was + made)
        lines.append(f"  {name:<14} {was:>12,} {made:>9,} {holds:>10,}  "
                     f"{'—' if gap == 0 else f'{gap:+,}'}")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m etl.load_education")
    parser.add_argument("--url", default="http://localhost:8200")
    # **THE SAME DEFAULT AS `etl/load_pwcs.py`.** Without this the loader took
    # `Engine`'s `graph="default"` while the district loads into `edtech`, so
    # somebody following the README got PWCS in one graph and the spine in
    # another — two disconnected halves, and the cross-tier join they exist
    # for cannot be written across them.
    parser.add_argument("--graph", default="edtech",
                        help="The graph to write into. Must match the one "
                             "`load_pwcs` used, or the two tiers cannot be "
                             "joined.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Count the statements without sending them.")
    parser.add_argument("--all-rows", action="store_true",
                        help="Load rows recording zero awards too. They are "
                             "69% of this slice and answer no question in "
                             "docs/questions.md.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Load only the first N completion rows.")
    parser.add_argument("--record", action="store_true",
                        help=f"Write the run to {shown(RECORD)}, "
                             f"stamped with the code that produced it.")
    args = parser.parse_args(argv)

    # **REFUSED BEFORE THE LOAD, not after it.** This sat after `load()`
    # returned, so a `--record --limit 100` spent forty minutes and then
    # declined to write. A flag combination knowable at parse time is one to
    # check at parse time.
    if args.record and (args.dry_run or args.limit is not None or args.all_rows):
        print("--record describes the full default slice; drop --dry-run, "
              "--limit and --all-rows", file=sys.stderr)
        return 4

    engine = Engine(args.url, graph=args.graph)
    # **Read BEFORE the load.** Without it the report has nothing to subtract
    # and a graph that already held anything shows this run as having lost or
    # gained nodes it never touched.
    before = {} if args.dry_run else in_the_graph(engine)
    try:
        loaded = load(engine, dry_run=args.dry_run,
                      only_awarded=not args.all_rows, limit=args.limit)
    except Missing as gone:
        print(f"{gone}", file=sys.stderr)
        return 2
    except Refused as refused:
        print(f"the engine refused a statement: {refused}", file=sys.stderr)
        return 3

    graph = {} if args.dry_run else in_the_graph(engine)
    for line in report(loaded, graph, before):
        print(line)

    if args.record:
        # **THE IDEMPOTENCE RE-RUN IS PART OF THE RECORD.** The page used to
        # claim "175,762 statements, zero created" and that figure was in no
        # record — a run done by hand, on a page whose first sentence says
        # every figure came from the record. A second pass is the only way
        # that claim can be true, and it is the claim the loader's whole
        # design rests on.
        print("  re-running to measure idempotence...")
        again = load(engine, only_awarded=not args.all_rows)
        after = in_the_graph(engine)
        write_record(RECORD, {
            "_": RECORD_NOTE,
            "second_run": {
                "seconds": again["seconds"],
                "statements_issued": again["statements_issued"],
                "nodes_and_edges_created": again["nodes_and_edges_created"],
                "already_present": again["already_present"],
                "in_graph_after": after,
            },
            "engine_version_reported": ENGINE_VERSION,
            "fips": FIPS, "year": YEAR,
            "issued": loaded,
            "in_graph": graph,
        })
        print(f"wrote {shown(RECORD)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

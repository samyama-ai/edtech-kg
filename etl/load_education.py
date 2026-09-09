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
    "Measured by `python -m etl.load_education --record`. `issued` is what "
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


def held(name: str) -> dict:
    path = CACHE / f"{name}-{FIPS}-{YEAR}.json"
    if not path.exists():
        raise Missing(
            f"{shown(path)} is not here. Run "
            f"`python -m etl.download_education` first — `data/` is "
            f"gitignored, so a fresh clone has none of it.")
    return json.loads(path.read_text(encoding="utf-8"))


def completion_id(row: dict) -> str:
    """The Completion key, spelled exactly as `schema/edtech_kg.cypher` does.

    Six parts. `majornum` is one of them: without it, 3,524 groups in this
    slice merge two real completions into one node and lose a count — which
    is what the first load found and what the schema now records.
    """
    parts = (row["unitid"], row["cipcode_6digit"], row["award_level"],
             row["majornum"], row["race"], row["sex"], YEAR)
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()


def quote(value) -> str:
    """A Cypher string literal. 1.1.0 has no escape sequence inside one.

    `etl/cypher_script.py` records why that matters: a quote character always
    opens or closes a literal and never appears within, so a value carrying
    one cannot be written at all. Refused rather than mangled — a silently
    truncated institution name is a wrong answer that looks like a right one.
    """
    text = str(value)
    if '"' in text or "\\" in text:
        raise Refused(400, f"cannot quote {text!r}: 1.1.0 has no escape "
                           f"sequence inside a string literal")
    return '"' + text + '"'


class Writer:
    """Lookup, then create only if absent — and count both.

    The two round trips are the point, and they are still cheaper than one
    `MERGE`: #169 measured `MERGE` ignoring the constraint's index and
    scanning, falling from 692/sec at 1,500 nodes to 35/sec at 37,141.

    This does not claim "does not degrade" — an earlier draft did, on a
    2,000-row slice, which is exactly the size at which the `MERGE` problem
    is also invisible. `docs/national-spine.md` carries the rate measured
    across the whole load instead.
    """

    def __init__(self, engine: Engine, dry_run: bool = False):
        self.engine = engine
        self.dry_run = dry_run
        self.looked_up = 0
        self.created = 0
        self.already_there = 0

    def node(self, label: str, key: str, value: str, properties: dict) -> None:
        self.looked_up += 1
        if not self.dry_run:
            found = self.engine.run(
                f"MATCH (n:{label}) WHERE n.{key} = {quote(value)} "
                f"WITH n RETURN n.{key}").get("records") or []
            if found:
                self.already_there += 1
                return
        self.created += 1
        if self.dry_run:
            return
        fields = ", ".join(f"{name}: {quote(v)}"
                           for name, v in properties.items())
        # Concatenated rather than interpolated. An f-string needs the
        # literal brace doubled to emit one, and a doubled brace around a
        # name is exactly the unfilled-template shape
        # `tests/test_repo_layout.py` refuses — this is a public repo and a
        # reader sees an unfilled template before they see anything else.
        # (The comment cannot show the shape either, for the same reason.)
        self.engine.run("CREATE (n:" + label + " {" + fields + "})")

    def edge(self, kind: str, tail: tuple[str, str, str],
             head: tuple[str, str, str]) -> None:
        """One edge between two existing nodes.

        **Both endpoints matched with their own WHERE.** A `MATCH` whose
        endpoints are BOTH already bound does not filter on 1.1.0 — it is
        silently ignored, which `docs/engine-behaviours.md` records — so the
        pattern is written with the endpoints introduced fresh.
        """
        self.looked_up += 1
        if self.dry_run:
            self.created += 1
            return
        tail_label, tail_key, tail_value = tail
        head_label, head_key, head_value = head

        # **LOOK FIRST — the node path did and this did not.** A second run
        # over the same slice created 2,000 duplicate AT and IN edges: the
        # nodes were idempotent and the edges were not. The loader's own
        # issued-against-held report is what caught it, which is the argument
        # for reading counts back from the graph rather than trusting the
        # count of what was sent.
        #
        # An edge MERGE would not do it either: #163 records edge `MERGE`
        # ignoring its property map on 1.1.0.
        existing = self.engine.run(
            f"MATCH (a:{tail_label})-[r:{kind}]->(b:{head_label}) "
            f"WHERE a.{tail_key} = {quote(tail_value)} "
            f"AND b.{head_key} = {quote(head_value)} "
            f"WITH r RETURN count(r)").get("records") or []
        if existing and existing[0] and existing[0][0]:
            self.already_there += 1
            return

        self.engine.run(
            f"MATCH (a:{tail_label}) WHERE a.{tail_key} = {quote(tail_value)} "
            f"WITH a "
            f"MATCH (b:{head_label}) WHERE b.{head_key} = {quote(head_value)} "
            f"WITH a, b "
            f"CREATE (a)-[:{kind}]->(b)")
        self.created += 1


def load(engine: Engine, dry_run: bool = False,
         only_awarded: bool = True, limit: int | None = None) -> dict:
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

    institutions = held("institutions")["rows"]
    for row in institutions:
        writer.node("Institution", "unitid", row["unitid"],
                    {"unitid": row["unitid"], "name": row.get("inst_name") or "",
                     "state": row.get("state_abbr") or ""})

    completions = held("completions")["rows"]
    skipped_zero = 0
    if only_awarded:
        keep = [r for r in completions if (r.get("awards_6digit") or 0) > 0]
        skipped_zero = len(completions) - len(keep)
        completions = keep
    if limit:
        completions = completions[:limit]

    programmes = sorted({str(r["cipcode_6digit"]) for r in completions})
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
            "cip_code": str(row["cipcode_6digit"]),
            "award_level": row["award_level"],
            "major_number": row["majornum"],
            "race": row["race"], "sex": row["sex"],
            "awards": row.get("awards_6digit") or 0})
        writer.edge("AT", ("Completion", "id", key),
                    ("Institution", "unitid", row["unitid"]))
        writer.edge("IN", ("Completion", "id", key),
                    ("Programme", "cip_code", str(row["cipcode_6digit"])))

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
        "institutions_in": len(institutions),
        "programmes_in": len(programmes),
        "completions_in": len(seen),
        "rows_skipped_zero_awards": skipped_zero,
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


def report(loaded: dict, graph: dict) -> list[str]:
    """Issued against held, per label — and the gap named, not assumed away."""
    lines = [
        f"  {loaded['statements_issued']:,} statements in "
        f"{loaded['seconds']}s "
        f"({round(loaded['statements_issued'] / max(loaded['seconds'], 0.1)):,}/sec)",
        f"  skipped {loaded['rows_skipped_zero_awards']:,} rows recording zero "
        f"awards, {loaded['duplicate_rows_skipped']:,} duplicate rows",
        "",
        f"  {'':<14} {'issued':>9} {'in graph':>10}  gap",
    ]
    for label, issued in (("Institution", loaded["institutions_in"]),
                          ("Programme", loaded["programmes_in"]),
                          ("Completion", loaded["completions_in"])):
        holds = graph.get(label, 0)
        gap = holds - issued
        lines.append(f"  {label:<14} {issued:>9,} {holds:>10,}  "
                     f"{'—' if gap == 0 else f'{gap:+,}'}")
    # One edge of each kind per completion, so the issued count is the same.
    edges_issued = loaded["completions_in"]
    for kind in ("AT", "IN"):
        holds = graph.get(kind, 0)
        gap = holds - edges_issued
        lines.append(f"  {kind:<14} {edges_issued:>9,} {holds:>10,}  "
                     f"{'—' if gap == 0 else f'{gap:+,}'}")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m etl.load_education")
    parser.add_argument("--url", default="http://localhost:8200")
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

    engine = Engine(args.url)
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
    for line in report(loaded, graph):
        print(line)

    if args.record:
        if args.dry_run or args.limit or args.all_rows:
            # A record of a partial load, filed where the card reads the whole
            # one, is a wrong figure that looks measured. Refused rather than
            # written with a caveat nobody reads.
            print("--record describes the full default slice; drop --dry-run, "
                  "--limit and --all-rows", file=sys.stderr)
            return 4
        write_record(RECORD, {
            "_": RECORD_NOTE,
            "engine_version_reported": ENGINE_VERSION,
            "fips": FIPS, "year": YEAR,
            "issued": loaded,
            "in_graph": graph,
        })
        print(f"wrote {shown(RECORD)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Export the loaded graph, and import it into an engine that holds nothing.

edtech-kg#25. A demo that begins with a load begins with ten minutes of
nothing. The sibling KG measured a 2.2 MB snapshot importing in 0.54 seconds
against a ~10 minute load, and that difference is what lets the graph be shown
in someone else's office, on someone else's laptop, without internet.

    python -m etl.snapshot export --url http://localhost:8200
    python -m etl.snapshot import --url http://localhost:8250 --file <path>
    python -m etl.snapshot verify --url http://localhost:8250

**THE COUNTS DO NOT COME FROM `/api/status`.** That is the obvious place to
read them and it is wrong: on a graph built by Cypher `CREATE`, `storage.edges`
reports **2,834** for a graph holding **1,417** edges, while the same graph
imported from a snapshot reports 1,417. Measured on 1.1.0, both engines side
by side, with every per-type count identical:

    REQUIRES 240 · IN_SUBJECT 723 · INCLUDES 316 · HAS_REQUIREMENT 138 = 1,417

So a verification that trusted `/api/status` would call a correct import a
failure, or a half-imported graph a success, depending on which side it read.
Every count here is a per-type `MATCH ()-[r:TYPE]->() RETURN count(r)`.

The snapshot is NOT committed. `data/` is gitignored and this ships as a
release asset — a graph artefact is not source, and the dataset card records
its size and import time so the figure has a run behind it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request

from etl.engine import Engine
from etl.provenance import write_record

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_FILE = ROOT / "data" / "edtech-kg.sgsnap"
RECORD = ROOT / "docs" / "sources" / "snapshot-measured.json"
RECORD_NOTE = (
    "Measured by `python -m etl.snapshot record`. Size, import time and the "
    "counts an import must reproduce. The counts are per-type Cypher, NOT "
    "`/api/status`: on a Cypher-loaded graph that endpoint reports twice the "
    "edges it holds, so a check against it would pass or fail depending on "
    "how the graph it is checking was built. `snapshot.bytes` is the export "
    "this run published; `snapshot.reproducible` compares three FURTHER "
    "exports of the same graph. They are different exports, and exports of "
    "one unchanged graph differ in size, so `bytes` is not expected to fall "
    "between `bytes_min` and `bytes_max` — it did not on an earlier run, and "
    "the two looked inconsistent.")

#: What the district's graph holds, by type. Named so `verify` compares a
#: shape rather than a single total — a total can be right while two types are
#: wrong in opposite directions.
NODE_LABELS = ("Course", "Subject", "Pathway", "Requirement")
EDGE_TYPES = ("REQUIRES", "IN_SUBJECT", "INCLUDES", "HAS_REQUIREMENT")


class Refused(RuntimeError):
    """The engine would not do what the snapshot needs."""


def post(url: str, path: str, body: bytes | None = None,
         content_type: str | None = None) -> tuple[int, bytes]:
    request = urllib.request.Request(f"{url.rstrip('/')}{path}", data=body or b"",
                                     method="POST")
    if content_type:
        request.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as refused:
        return refused.code, refused.read()
    except (urllib.error.URLError, TimeoutError, OSError) as gone:
        raise Refused(f"{path}: {gone}") from gone


def counts(engine: Engine) -> dict:
    """What the graph holds, by label and by edge type.

    Per-type, never `/api/status`. See the module docstring: that endpoint
    double-counts edges on a Cypher-loaded graph.
    """
    held = {}
    for label in NODE_LABELS:
        rows = engine.run(f"MATCH (n:{label}) WITH n RETURN count(n)").get("records")
        held[label] = int(rows[0][0]) if rows and rows[0] else 0
    for kind in EDGE_TYPES:
        rows = engine.run(f"MATCH ()-[r:{kind}]->() RETURN count(r)").get("records")
        held[kind] = int(rows[0][0]) if rows and rows[0] else 0
    return held


def export(url: str, into: pathlib.Path) -> dict:
    """Write a snapshot of `url`, and record what it was taken from."""
    before = counts(Engine(url))
    if not sum(before.values()):
        raise Refused(
            f"{url} holds nothing. Exporting it would publish an empty "
            f"snapshot as a demo — load the district first.")

    status, body = post(url, "/api/snapshot/export")
    if status != 200:
        raise Refused(f"export answered {status}: {body[:200]!r}")
    into.parent.mkdir(parents=True, exist_ok=True)
    # Written aside and moved into place: a snapshot half-written to the path
    # a demo reads from is worse than none.
    scratch = into.with_name(into.name + ".part")
    scratch.write_bytes(body)
    scratch.replace(into)
    # **Repo-relative.** `str(into)` put a committed document's author's home
    # directory into `snapshot-measured.json`.
    try:
        where = into.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        where = into.name          # written outside the repo; the name is all
    return {"file": where, "bytes": len(body), "taken_from": before}


def load(url: str, snapshot: pathlib.Path) -> dict:
    """Import into an engine that holds NOTHING, and time it."""
    engine = Engine(url)
    held = counts(engine)
    if sum(held.values()):
        raise Refused(
            f"{url} already holds {sum(held.values())} nodes and edges. "
            f"Importing would merge into somebody's graph — point this at a "
            f"fresh engine.")

    raw = snapshot.read_bytes()
    boundary = "----samyama-snapshot"
    body = (f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; '
            f'filename="{snapshot.name}"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n").encode()
    body += raw + f"\r\n--{boundary}--\r\n".encode()

    started = time.monotonic()
    status, answer = post(url, "/api/snapshot/import", body,
                          f"multipart/form-data; boundary={boundary}")
    seconds = round(time.monotonic() - started, 2)
    if status != 200:
        raise Refused(f"import answered {status}: {answer[:200]!r}")
    return {"seconds": seconds, "bytes": len(raw),
            "engine_said": json.loads(answer or b"{}"),
            "in_graph": counts(engine)}


def should_hold() -> dict | None:
    """The counts an import must reproduce, from the committed record.

    One reader for both `import` and `verify`, so neither can drift into
    checking the graph against itself.
    """
    if not RECORD.exists():
        print(f"{RECORD.relative_to(ROOT)} is missing — run "
              f"`python -m etl.snapshot record` first.", file=sys.stderr)
        return None
    return json.loads(RECORD.read_text(encoding="utf-8"))["counts"]


def verify(url: str, expected: dict) -> list[str]:
    """Every label and edge type, compared. Returns what disagrees."""
    held = counts(Engine(url))
    return [f"{name}: expected {expected[name]:,}, found {held.get(name, 0):,}"
            for name in expected if held.get(name, 0) != expected[name]]


def reproducibility(url: str, times: int = 3) -> dict:
    """Does exporting an unchanged graph twice give the same file?

    **It does not**, and that decides how the size may be quoted and how a
    download may be checked. Three exports of one unloaded-since graph differ
    in size and in sha256; the figures are in `snapshot-measured.json` under
    `snapshot.reproducible`, and are not repeated here — the three sizes this
    docstring used to quote had drifted from the record they came from, which
    is the same defect this module was written to remove from the card.

    So a published snapshot cannot be verified by re-exporting and comparing;
    its integrity has to be checked against the hash of the file that was
    actually published. And an exact byte count on a page is a figure that
    drifts on every export, which is why the dataset card rounds it.
    """
    seen = []
    # In memory: the export is compared as bytes, never written. An earlier
    # version built scratch paths, wrote nothing to them, then unlinked them
    # in a `finally`.
    for _ in range(times):
        status, body = post(url, "/api/snapshot/export")
        if status != 200:
            raise Refused(f"export answered {status}")
        seen.append((len(body), hashlib.sha256(body).hexdigest()))
    sizes = [n for n, _ in seen]
    return {
        "exports_compared": times,
        "bytes_min": min(sizes),
        "bytes_max": max(sizes),
        "bytes_spread": max(sizes) - min(sizes),
        "byte_identical": len({d for _, d in seen}) == 1,
    }


def report(measured: dict) -> None:
    snap = measured["snapshot"]
    print(f"  {snap['bytes']:,} bytes, imported in {measured['import']['seconds']}s")
    print(f"  {'':<18} {'nodes/edges':>12}")
    for name in NODE_LABELS + EDGE_TYPES:
        print(f"  {name:<18} {measured['import']['in_graph'][name]:>12,}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m etl.snapshot",
        description=__doc__.strip().splitlines()[0],
        epilog="The snapshot is NOT committed — `data/` is gitignored and this "
               "ships as a release asset.")
    parser.add_argument("action",
                        choices=("export", "import", "verify", "record"))
    parser.add_argument("--url", default="http://localhost:8200")
    parser.add_argument("--file", type=pathlib.Path, default=DEFAULT_FILE)
    parser.add_argument("--from-url", default="http://localhost:8200",
                        help="`record` only: the loaded graph to export FROM.")
    args = parser.parse_args(argv)

    try:
        if args.action == "export":
            found = export(args.url, args.file)
            print(f"  {found['bytes']:,} bytes -> {found['file']}")
            return 0

        if args.action == "import":
            found = load(args.url, args.file)
            print(f"  imported in {found['seconds']}s")
            # **NOT `found["in_graph"]`.** That is `counts(engine)` taken from
            # this same engine moments earlier, so it compared the graph to
            # itself: it could only fail on a race, and a half-import — the
            # failure this module exists to catch — passed. It also returned 4
            # without saying what disagreed. Both actions use the record now.
            expected = should_hold()
            if expected is None:
                return 2
            wrong = verify(args.url, expected)
            if wrong:
                print("the imported graph is not what the snapshot should "
                      "produce:", file=sys.stderr)
                for line in wrong:
                    print(f"  {line}", file=sys.stderr)
                return 4
            return 0

        if args.action == "verify":
            expected = should_hold()
            if expected is None:
                return 2
            wrong = verify(args.url, expected)
            if wrong:
                print("the graph is not what the snapshot should produce:",
                      file=sys.stderr)
                for line in wrong:
                    print(f"  {line}", file=sys.stderr)
                return 4
            print(f"  verified: {sum(expected.values()):,} nodes and edges")
            return 0

        # record: export from the loaded graph, import into `--url`, measure.
        taken = export(args.from_url, args.file)
        taken["reproducible"] = reproducibility(args.from_url)
        found = load(args.url, args.file)
        wrong = verify(args.url, taken["taken_from"])
        if wrong:
            # **The round trip did not reproduce the graph.** Recording that
            # would publish a snapshot the demo cannot trust.
            print("the import did not reproduce the source graph:",
                  file=sys.stderr)
            for line in wrong:
                print(f"  {line}", file=sys.stderr)
            return 4
        measured = {"_": RECORD_NOTE, "snapshot": taken, "import": found,
                    "counts": taken["taken_from"]}
        report(measured)
        write_record(RECORD, measured)
        print(f"\n  -> {RECORD.relative_to(ROOT)}")
        return 0
    except Refused as refused:
        print(f"{refused}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())

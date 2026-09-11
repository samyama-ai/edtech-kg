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

**Why that is the endpoint's fault and not the import's**, which matters
because the other reading is that the import silently drops half its edges:
`both_directions` records a REVERSE expansion on both engines, and both
answer 1,417 — an engine holding one adjacency entry per edge could not walk
`(c:Course)<-[r:INCLUDES]-(:Pathway)` from the Course end. The undirected
count is recorded too and settles nothing alone: it is exactly twice directed
for every type on both engines, which is as much a doubling rule as a
traversal. See `both_directions` and `edge_count_readings` in the record.

The snapshot is NOT committed. `data/` is gitignored and this ships as a
release asset — a graph artefact is not source, and the dataset card records
its size and import time so the figure has a run behind it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import secrets
import sys
import time
import urllib.error
import urllib.request

from etl.edge_count_readings import (DEFAULT_GRAPH, Refused, _count,
                                     both_directions, storage_reported)
from etl.engine import Engine, identifier
from etl.engine import Refused as EngineRefused
from etl.provenance import write_record
from etl.scratch_engine import Unusable, still_held

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_FILE = ROOT / "data" / "edtech-kg.sgsnap"
RECORD = ROOT / "docs" / "sources" / "snapshot-measured.json"
RECORD_NOTE = (
    "Measured by `python -m etl.snapshot record`. Size, import time and the "
    "counts an import must reproduce. The counts are per-type Cypher, NOT "
    "`/api/status`: on a Cypher-loaded graph that endpoint reports twice the "
    "edges it holds, so a check against it would pass or fail depending on "
    "how the graph it is checking was built. `edge_count_readings` carries "
    "the evidence for that, from both engines, written by `both_directions`: "
    "the REVERSE expansion is the reading that excludes a lossy import, "
    "because an engine holding one adjacency entry per edge could not answer "
    "it from the head. The undirected count is recorded but settles nothing "
    "on its own — it is exactly twice directed everywhere, which is as much "
    "a doubling rule as a traversal. `snapshot.bytes` is the export "
    "this run published; `snapshot.reproducible` compares three FURTHER "
    "exports of the same graph. They are different exports, and exports of "
    "one unchanged graph differ in size, so `bytes` is not expected to fall "
    "between `bytes_min` and `bytes_max` — it did not on an earlier run, and "
    "the two looked inconsistent. `property_counts` says how many nodes of "
    "each label carry the property they are worthless without, measured on "
    "the SOURCE during export and proved by the round trip — counting "
    "nodes says the shape survived, not that they carry anything.")

#: What the district's graph holds, by type. Named so `verify` compares a
#: shape rather than a single total — a total can be right while two types are
#: wrong in opposite directions.
NODE_LABELS = ("Course", "Subject", "Pathway", "Requirement")

#: The property each label is worthless without, and the one `load_pwcs`
#: already checks after its own load (`etl/load_pwcs.py:427-434`). Counting
#: nodes and edges says the SHAPE survived the round trip; it says nothing
#: about whether they carry anything, and a graph of nameless nodes verifies
#: clean while the walkthrough opens on blanks.
REQUIRED_PROPERTIES = (("Course", "name"), ("Subject", "name"),
                       ("Pathway", "name"), ("Requirement", "text"))
EDGE_TYPES = ("REQUIRES", "IN_SUBJECT", "INCLUDES", "HAS_REQUIREMENT")


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
        held[label] = _count(
            engine, f"MATCH (n:{identifier(label)}) WITH n RETURN count(n)")
    for kind in EDGE_TYPES:
        held[kind] = _count(
            engine, f"MATCH ()-[r:{identifier(kind)}]->() RETURN count(r)")
    return held


def export(url: str, into: pathlib.Path,
           graph: str = DEFAULT_GRAPH) -> dict:
    """Write a snapshot of `url`, and record what it was taken from."""
    source = Engine(url, graph=graph)
    before = counts(source)
    # **From the SOURCE, beside `taken_from`.** Measured on the imported
    # graph instead, this became self-fulfilling: an engine whose import
    # dropped values would have `Course.name: 0` written into the record as
    # the published expectation, and every later `demo/ready.sh` would then
    # verify the nameless graph as clean — the check certifying the state it
    # exists to detect.
    carried = properties(source)
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
    return {"file": where, "bytes": len(body), "properties": carried,
            # The digest of the file this run published — the one a download
            # is checked against. `reproducible` compares three FURTHER
            # exports, which differ from this one and from each other.
            "sha256": hashlib.sha256(body).hexdigest(),
            "taken_from": before}


def load(url: str, snapshot: pathlib.Path, graph: str = DEFAULT_GRAPH,
         expect_sha256: str | None = None) -> dict:
    """Import into an engine that holds NOTHING, and time it.

    **"Holds nothing" is asked of the INSTANCE, not of four labels.** It was
    `sum(counts(engine).values())`, and `counts` only knows the district's
    four labels and four edge types — so an engine holding the Virginia
    spine, or any of the twelve declared-and-unloaded labels on the dataset
    card, summed to zero and read as empty. The import is a MERGE and is not
    undoable.

    `still_held` is the same decision made earlier in `etl/scratch_engine.py`,
    where it is documented as having failed open twice in exactly this
    direction: instance-wide `/api/status`, and an unmeasurable count raises
    rather than reading as zero.
    """
    engine = Engine(url, graph=graph)
    try:
        occupied = still_held(url)
    except Unusable as unmeasured:
        raise Refused(str(unmeasured)) from unmeasured
    if occupied:
        raise Refused(
            f"{url} already holds {occupied:,} nodes instance-wide. "
            f"Importing would merge into somebody's graph — point this at a "
            f"fresh engine.")

    raw = snapshot.read_bytes()
    if expect_sha256 is not None:
        # **The card promises this check.** Before it existed, a binary
        # downloaded from a Releases page went straight into an engine on the
        # strength of a documented guarantee with nothing behind it — and the
        # import path is the trust boundary this module itself identifies.
        got = hashlib.sha256(raw).hexdigest()
        if got != expect_sha256:
            raise Refused(
                f"{snapshot.name} hashes to {got[:16]}... and the record says "
                f"{expect_sha256[:16]}.... Exports of one graph differ byte "
                f"for byte, so a re-export will not match — check this "
                f"against the file that was published.")

    boundary = f"----samyama-{secrets.token_hex(16)}"
    body = (f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; '
            f'filename="{pathlib.Path(snapshot.name).name}"\r\n'
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


def should_hold(whole: bool = False) -> dict | None:
    """The counts an import must reproduce, from the committed record.

    One reader for both `import` and `verify`, so neither can drift into
    checking the graph against itself. `whole` returns the entire record,
    for the caller that needs the published digest as well as the counts.
    """
    if not RECORD.exists():
        print(f"{RECORD.relative_to(ROOT)} is missing — run "
              f"`python -m etl.snapshot record` first.", file=sys.stderr)
        return None
    held = json.loads(RECORD.read_text(encoding="utf-8"))
    return held if whole else held["counts"]


def properties(engine: Engine) -> dict:
    """How many nodes of each label actually carry their key property.

    Asked as `IS NOT NULL` rather than as a total, so the answer is directly
    comparable with the label count beside it: equal means every node carries
    it, and anything less names how many do not.
    """
    return {f"{label}.{prop}": _count(
        engine, f"MATCH (n:{identifier(label)}) "
                f"WHERE n.{identifier(prop)} IS NOT NULL RETURN count(n)")
        for label, prop in REQUIRED_PROPERTIES}


def verify(url: str, expected: dict, graph: str = DEFAULT_GRAPH,
           expect_properties: dict | None = None) -> list[str]:
    """Every label and edge type, compared — and their key properties.

    **Cardinality is not content.** This compared counts per label and per
    edge type only, so a snapshot that reproduced every node and every edge
    and dropped every PROPERTY verified clean, and the demo then opened on
    nameless nodes. `demo/ready.sh` runs this as its gate, so it is the check
    standing between a bad import and a customer-facing walkthrough — and
    `etl/engine.py:208-220` records that properties are effectively
    unremovable on 1.1.0, so such a graph cannot be repaired in place.
    """
    engine = Engine(url, graph=graph)
    held = counts(engine)
    wrong = [f"{name}: expected {expected[name]:,}, found {held.get(name, 0):,}"
             for name in expected if held.get(name, 0) != expected[name]]
    if expect_properties:
        carried = properties(engine)
        wrong += [
            f"{name}: expected {expect_properties[name]:,} node(s) carrying "
            f"it, found {carried.get(name, 0):,} — the nodes arrived and the "
            f"values did not"
            for name in expect_properties
            if carried.get(name, 0) != expect_properties[name]]
    return wrong


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
        # The digests were computed and thrown away, so "three different
        # sha256" was a sentence with nothing behind it. n=3 supports "these
        # three exports differed", not "exports are non-deterministic in
        # general" — and that conclusion drives both the card's rounding and
        # the hash policy, so it is worth stating at its real strength.
        "sha256": [digest for _, digest in seen],
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
    parser.add_argument("--graph", default=DEFAULT_GRAPH,
                        help="The graph to read and write. Defaults to `edtech`, matching etl/load_pwcs.py and demo/demo.py.")
    parser.add_argument("--from-url", default="http://localhost:8200",
                        help="`record` only: the loaded graph to export FROM.")
    args = parser.parse_args(argv)

    try:
        if args.action == "export":
            found = export(args.url, args.file, graph=args.graph)
            print(f"  {found['bytes']:,} bytes -> {found['file']}")
            print(f"  sha256 {found['sha256']}")
            return 0

        if args.action == "import":
            recorded = should_hold(whole=True)
            if recorded is None:
                return 2
            expected_hash = (recorded.get("snapshot") or {}).get("sha256")
            found = load(args.url, args.file, graph=args.graph,
                         expect_sha256=expected_hash)
            print(f"  imported in {found['seconds']}s")
            # **NOT `found["in_graph"]`.** That is `counts(engine)` taken from
            # this same engine moments earlier, so it compared the graph to
            # itself: it could only fail on a race, and a half-import — the
            # failure this module exists to catch — passed. It also returned 4
            # without saying what disagreed. Both actions use the record now.
            wrong = verify(args.url, recorded["counts"], graph=args.graph,
                           expect_properties=recorded.get("property_counts"))
            if wrong:
                print("the imported graph is not what the snapshot should "
                      "produce:", file=sys.stderr)
                for line in wrong:
                    print(f"  {line}", file=sys.stderr)
                return 4
            return 0

        if args.action == "verify":
            recorded = should_hold(whole=True)
            if recorded is None:
                return 2
            expected = recorded["counts"]
            wrong = verify(args.url, expected, graph=args.graph,
                           expect_properties=recorded.get("property_counts"))
            if wrong:
                print("the graph is not what the snapshot should produce:",
                      file=sys.stderr)
                for line in wrong:
                    print(f"  {line}", file=sys.stderr)
                return 4
            print(f"  verified: {sum(expected.values()):,} nodes and edges")
            return 0

        # record: export from the loaded graph, import into `--url`, measure.
        #
        # **Exported aside and moved into place only after the round trip
        # verifies.** A failed `record` used to leave the bad snapshot at the
        # path `demo/ready.sh` picks up by default, so the next run imported
        # it and checked it against a stale record.
        candidate = args.file.with_name(args.file.name + ".candidate")
        taken = export(args.from_url, candidate, graph=args.graph)
        taken["reproducible"] = reproducibility(args.from_url)
        # No `expect_sha256`: this run just wrote those bytes, so checking
        # them against a digest of themselves would prove nothing.
        found = load(args.url, candidate, graph=args.graph)
        wrong = verify(args.url, taken["taken_from"], graph=args.graph,
                       expect_properties=taken["properties"])
        if wrong:
            # **The round trip did not reproduce the graph.** Recording that
            # would publish a snapshot the demo cannot trust.
            print("the import did not reproduce the source graph:",
                  file=sys.stderr)
            for line in wrong:
                print(f"  {line}", file=sys.stderr)
            candidate.unlink(missing_ok=True)
            return 4
        candidate.replace(args.file)
        taken["file"] = str(args.file.resolve().relative_to(ROOT).as_posix()) \
            if ROOT in args.file.resolve().parents else args.file.name
        # **The two measurements that tell the readings of 2,834 apart.**
        # Recorded from BOTH engines so a reader can check the conclusion
        # rather than take the note's word for it.
        endpoint = {
            "cypher_loaded": {"api_status_storage": storage_reported(args.from_url),
                              "per_type": both_directions(args.from_url, args.graph)},
            "imported": {"api_status_storage": storage_reported(args.url),
                         "per_type": both_directions(args.url, args.graph)},
        }
        measured = {"_": RECORD_NOTE, "snapshot": taken, "import": found,
                    "counts": taken["taken_from"],
                    # Which graph, and which engine was which — the card leans
                    # on a two-engine comparison, and `cypher_loaded` versus
                    # `imported` was attributable to nothing but a key name.
                    "graph": args.graph,
                    # What the nodes CARRY, not just how many arrived, and
                    # measured on the SOURCE during `export` — see the note
                    # there. The round trip above already proved the imported
                    # graph reproduces it.
                    "property_counts": taken["properties"],
                    "exported_from": args.from_url, "imported_into": args.url,
                    "edge_count_readings": endpoint}
        report(measured)
        write_record(RECORD, measured)
        print(f"\n  -> {RECORD.relative_to(ROOT)}")
        return 0
    except (Refused, EngineRefused) as refused:
        # **Both `Refused` classes.** This module defines one and
        # `etl/engine.py:64` defines a different class of the same name; only
        # the local one was caught, so an unreachable engine, a 4xx or a parse
        # error during `counts` gave a traceback and exit 1. Under `set -e` in
        # `demo/ready.sh` that is a stack trace in front of whoever is setting
        # up the demo.
        print(f"{refused}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())

"""The CIP-SOC crosswalk, loaded — programmes to the occupations they lead to.

edtech-kg#196. The join every career-side question in `docs/questions.md`
traverses: a degree programme on one side, occupations on the other.

**This loads a published CLAIM, not a fact.** NCES and BLS revise the
crosswalk, and two editions disagree about what a programme prepares you for.
So the edition rides on the edge (`source_edition`), the way
`schema/edtech_kg.cypher` specifies, and a later edition can be told from this
one rather than silently replacing it.

**Occupations are loaded whole; edges are not.** The crosswalk names 867
occupations over 1,949 CIP codes, and this graph holds only the programmes
Virginia actually awarded in 2022 — 663 of them. Writing an edge whose
Programme is absent would be a no-op that `Writer.edge` still counts as
created, so mappings without a loaded programme are skipped and COUNTED
rather than issued. The occupations themselves are the published vocabulary
and stand on their own.

The key comes from `etl/cip.py`, not from the spine loader: a loader
importing another loader to borrow a key is the wrong way round, and both
sides of this join have to normalise the same way or it fails quietly.

Reads through `etl/probe_cipsoc.py` rather than parsing the workbook again:
that module already measures this file, and a second reader is a second set of
figures to keep in agreement.

    python -m etl.load_cipsoc --url http://localhost:8200 --graph edtech
    python -m etl.load_cipsoc --record

Needs the spine loaded first — `etl/load_education.py` — or every mapping is
skipped for want of a programme.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import zipfile

from etl import probe_cipsoc
from etl.engine import ENGINE_VERSION, Engine, Refused
from etl.graph_writer import Writer, quote
from etl.cip import cip_code
from etl.load_education import ROOT
from etl.provenance import write_record

RECORD = ROOT / "docs" / "sources" / "cipsoc-load-measured.json"
RECORD_NOTE = (
    "Measured by `python -m etl.load_cipsoc --record`. The crosswalk is a "
    "published claim with a revision history, so `source_edition` rides on "
    "every PREPARES_FOR edge and this record names the edition it read. "
    "`mappings_without_a_programme` is not a failure: the crosswalk covers "
    "1,949 CIP codes and this graph holds only the programmes Virginia "
    "awarded, so the difference is scope rather than loss.")

#: What a node is worthless without, checked before the first write.
WRITTEN_FIELDS = ("soc_code", "title")


def edition(header: list[str]) -> str:
    """The crosswalk's edition, read off its own column headings.

    `CIP2020Code` and `SOC2018Code` name the two vocabularies, so the edition
    comes from the file rather than from its name — a downloaded copy can be
    renamed, and the headings cannot be without the reader failing loudly.
    """
    vocabularies = [text[:-4] for text in header
                    if text.endswith("Code") and len(text) > 4]
    if len(vocabularies) != 2:
        raise Refused(0, f"cannot read an edition from headings {header!r}")
    return "-".join(vocabularies)


def mappings(path=None) -> tuple[list[dict], str]:
    """Every programme-to-occupation mapping, and the edition that made it.

    `NO MATCH` rows are excluded here as they are in the probe: `99-9999` is
    the crosswalk's own sentinel for "this programme maps to no occupation",
    and loading it would create an occupation that is the absence of one.
    """
    book = zipfile.ZipFile(path or probe_cipsoc.LOCAL)
    table = probe_cipsoc.rows(book, probe_cipsoc.sheets(book)["CIP-SOC"])
    head = probe_cipsoc.find_header(table, "CIP")
    columns = {name: i for i, name in enumerate(table[head])}
    read = []
    for row in table[head + 1:]:
        def at(name):
            i = columns.get(name)
            return row[i].strip() if i is not None and i < len(row) else ""
        cip, soc = at("CIP2020Code"), at("SOC2018Code")
        if not cip or not soc or soc in probe_cipsoc.NOT_AN_OCCUPATION:
            continue
        read.append({"cip_code": cip_code(cip), "soc_code": soc,
                     "cip_title": at("CIP2020Title"),
                     "soc_title": at("SOC2018Title")})
    return read, edition(table[head])


def refuse_unwritable(occupations: list[dict]) -> None:
    """Raise if any value cannot be written, BEFORE the first write.

    There is no transaction here. Discovering an unwritable title at
    occupation 800 leaves 799 behind and a non-zero exit, which is the worst
    of both — the same argument `etl/load_education.py` makes, and the reason
    that one checks the larger table too.
    """
    for row in occupations:
        for field in WRITTEN_FIELDS:
            value = row.get(field)
            if value is not None:
                quote(value)          # raises Refused, naming the value


def in_the_graph(engine: Engine) -> dict:
    """What the graph holds, read back rather than inferred from the input."""
    held = {}
    for name, cypher in (
            ("Occupation", "MATCH (o:Occupation) WITH o RETURN count(o)"),
            ("PREPARES_FOR",
             "MATCH ()-[r:PREPARES_FOR]->() RETURN count(r)")):
        answered = engine.scalar(cypher)
        if answered is None:
            raise Refused(0, f"{engine.url} did not answer `{cypher}`")
        held[name] = int(answered)
    return held


def load(engine: Engine, dry_run: bool = False, limit: int | None = None,
         path=None) -> dict:
    """Occupations, then the edges to the programmes already loaded."""
    started = time.monotonic()
    read, which = mappings(path)
    if limit is not None:
        read = read[:limit]

    occupations = {}
    for row in read:
        occupations.setdefault(row["soc_code"],
                               {"soc_code": row["soc_code"],
                                "title": row["soc_title"]})
    refuse_unwritable(list(occupations.values()))

    # **Which programmes exist, asked once.** Issuing an edge whose Programme
    # is absent is a no-op that `Writer.edge` still counts as created, so the
    # gap would be invisible in the issued figure and visible only in the
    # graph. Asked up front, and the difference is reported.
    loaded = {str(row[0]) for row in
              (engine.run("MATCH (p:Programme) WITH p RETURN p.cip_code")
               .get("records") or []) if row and row[0] is not None}

    writer = Writer(engine, dry_run)
    for occupation in occupations.values():
        writer.node("Occupation", "soc_code", occupation["soc_code"],
                    occupation)

    joined = 0
    for row in read:
        if row["cip_code"] not in loaded:
            continue
        writer.edge("PREPARES_FOR",
                    ("Programme", "cip_code", row["cip_code"]),
                    ("Occupation", "soc_code", row["soc_code"]),
                    {"source_edition": which})
        joined += 1

    return {
        "source_edition": which,
        "seconds": round(time.monotonic() - started, 1),
        "statements_issued": writer.looked_up + writer.created,
        "nodes_and_edges_created": writer.created,
        "already_present": writer.already_there,
        "created_by": writer.created_by,
        "mappings_read": len(read),
        "occupations_in": len(occupations),
        "programmes_in_the_graph": len(loaded),
        "programmes_with_an_occupation": len(
            {r["cip_code"] for r in read if r["cip_code"] in loaded}),
        "edges_issued": joined,
        # Scope, not loss: the crosswalk covers every CIP code, and this graph
        # holds only the programmes Virginia awarded.
        "mappings_without_a_programme": len(read) - joined,
    }


def report(loaded: dict, held: dict) -> list[str]:
    """What was issued, beside what the graph actually holds."""
    lines = [
        f"  {loaded['mappings_read']:,} mappings from edition "
        f"{loaded['source_edition']} in {loaded['seconds']}s",
        f"  {loaded['occupations_in']:,} occupations, "
        f"{loaded['edges_issued']:,} edges issued",
        f"  {loaded['mappings_without_a_programme']:,} mappings name a "
        f"programme this graph does not hold — scope, not loss",
        "",
        f"  {'':<16}{'issued':>10}{'in graph':>12}{'gap':>8}",
    ]
    issued = {"Occupation": loaded["occupations_in"],
              "PREPARES_FOR": loaded["edges_issued"]}
    for name, count in issued.items():
        there = held.get(name, 0)
        gap = "—" if there == count else f"{there - count:+,}"
        lines.append(f"  {name:<16}{count:>10,}{there:>12,}{gap:>8}")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m etl.load_cipsoc",
        description=__doc__.strip().splitlines()[0])
    parser.add_argument("--url", default=os.environ.get(
        "SAMYAMA_URL", "http://localhost:8200"))
    parser.add_argument("--graph", default="edtech",
                        help="The graph to write into. Defaults to `edtech`, "
                             "matching etl/load_education.py and demo.demo.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Read and check, write nothing.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Load only the first N mappings.")
    parser.add_argument("--record", action="store_true",
                        help="Load twice and write docs/sources/, so "
                             "idempotence is measured rather than asserted.")
    args = parser.parse_args(argv)

    if args.record and args.dry_run:
        print("--record needs a real load; --dry-run writes nothing.",
              file=sys.stderr)
        return 2

    engine = Engine(args.url, graph=args.graph)
    try:
        loaded = load(engine, dry_run=args.dry_run, limit=args.limit)
        held = {} if args.dry_run else in_the_graph(engine)
        for line in report(loaded, held):
            print(line)
        if not args.record:
            return 0

        print("\n  re-running to measure idempotence...")
        again = load(engine, limit=args.limit)
        write_record(RECORD, {
            "_": RECORD_NOTE,
            "engine_version_reported": ENGINE_VERSION,
            "graph": args.graph,
            "issued": loaded,
            "second_run": again,
            "in_graph": in_the_graph(engine),
        })
        print(f"\nwrote {RECORD.relative_to(ROOT)}")
        return 0
    except Refused as refused:
        print(f"{refused}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())

"""What Florida actually published to the Credential Registry.

#55. Florida's Department of Education returns 403 to any automated request on
fldoe.org (#40, #50) and its statewide course directory carried no
prerequisites — yet it has a Registry community, `fdoe`, holding ten thousand
records. If any meaningful share were courses carrying resolvable
prerequisites, that would be the state-level source #40 concluded does not
exist, published somewhere nobody looked.

Two measurements, and the difference between them is the point:

**The type breakdown is a CENSUS.** The Registry reports `x-total` per type, so
fourteen HEAD requests count every record without reading one. The totals are
checked against the whole-community total and must close to zero
unattributed — an unexplained remainder means a type nobody asked about, and
reporting the parts as if they were the whole is exactly the failure this repo
keeps finding.

**The field profile is a SAMPLE**, drawn at a stride across the result set, and
it is reported as one. Which fields a credential carries cannot be read from a
header; it needs the records.

    python -m etl.probe_florida
    python -m etl.probe_florida --json
    python -m etl.probe_florida --record

No third-party dependency, as with the other probes.
"""

from __future__ import annotations

import argparse
import collections
import datetime
import json
import pathlib
import sys

from etl.registry_read import (REGISTRY, HttpStatus, MalformedSource, get,
                               parse, total)

COMMUNITY = "fdoe"
PER_PAGE = 50

#: Every resource type the Registry exposes as a search path. The list is long
#: on purpose: a type omitted here lands in `unattributed`, which is loud,
#: rather than being silently left out of a breakdown that still sums to
#: something plausible.
TYPES = ("course", "credential", "learning_opportunity_profile", "pathway",
         "assessment_profile", "organization", "collection",
         "competency_framework", "job", "occupation", "pathway_set",
         "transfer_value_profile", "support_service", "scheduled_offering")

#: The fields #55 turns on. `instructionalProgramType` is CIP and
#: `occupationType` is O*NET-SOC, so their coverage decides whether a Florida
#: credential reaches an occupation without any course data at all.
FIELDS = ("ceterms:instructionalProgramType", "ceterms:occupationType",
          "ceterms:requires", "ceterms:availableAt", "ceterms:subjectWebpage",
          "ceterms:identifier", "ceterms:estimatedCost")

ROOT = pathlib.Path(__file__).resolve().parent.parent
RECORD = ROOT / "docs" / "sources" / "florida-registry-measured.json"
RECORD_NOTE = ("Measured by `python -m etl.probe_florida`. The type breakdown "
               "is a census from x-total headers and reconciles to zero "
               "unattributed; the field profile is a sample and says so.")


def census() -> dict:
    """Every record in the community, counted by type, and reconciled.

    Raises rather than reporting a breakdown that does not add up. A partial
    census read as a whole one is the failure `probe_registry.registry_totals`
    already guards with its "unattributed" arithmetic; here the remainder must
    be zero, because these fourteen paths are meant to be exhaustive.
    """
    whole = total(f"/{COMMUNITY}/search")
    if not isinstance(whole, int):
        raise RuntimeError(
            f"the Registry did not report a total for {COMMUNITY}: {whole}")
    by_type = {}
    for kind in TYPES:
        counted = total(f"/{COMMUNITY}/{kind}/search")
        if not isinstance(counted, int):
            raise RuntimeError(f"{COMMUNITY}/{kind} answered {counted!r}; "
                               f"refusing to report a breakdown with a hole")
        by_type[kind] = counted
    return {"records": whole, "by_type": by_type,
            "unattributed": whole - sum(by_type.values())}


def spread(pages: int, wanted: int) -> list[int]:
    """Pages at a fixed stride, not the first N.

    Reading pages 1..N is a sample of whatever sorts first, which one
    publisher's bulk upload can dominate — and `fdoe` has exactly that shape:
    page 1 is one publisher and carries no `ceterms:requires` at all, while
    later pages are another and carry it on every record. The stride is
    deterministic, so the figure is reproducible.
    """
    if pages <= wanted:
        return list(range(1, pages + 1))
    stride = pages / wanted
    return sorted({max(1, min(pages, round(1 + i * stride)))
                   for i in range(wanted)})


def profile(population: int, sample_pages: int = 8) -> dict:
    """Which fields the credentials carry, over a sample drawn at a stride."""
    pages = -(-population // PER_PAGE)
    read = spread(pages, sample_pages)
    nodes = []
    for page in read:
        body = parse(get(f"{REGISTRY}/{COMMUNITY}/credential/search"
                         f"?per_page={PER_PAGE}&page={page}"),
                     f"page {page} of the {COMMUNITY} credential search")
        if not isinstance(body, list):
            raise MalformedSource(
                f"page {page} returned {type(body).__name__}, not a list")
        nodes += [n for envelope in body
                  for n in ((envelope.get("decoded_resource") or {})
                            .get("@graph") or [])
                  if isinstance(n, dict) and n.get("ceterms:ctid")]
    if not nodes:
        raise ValueError("no credential records returned — refusing to report "
                         "coverage over zero")
    kinds = collections.Counter(str(n.get("@type")) for n in nodes)
    return {
        "sampled": len(nodes),
        "pages_read": read,
        "of_pages": pages,
        "credential_types": dict(kinds.most_common()),
        "field_coverage": {field: sum(1 for n in nodes if n.get(field))
                           for field in FIELDS},
    }


def probe(quiet: bool = False) -> dict:
    counted = census()
    result = {**counted, "profile": profile(counted["by_type"]["credential"])}
    if not quiet:
        report(result)
    return result


def report(result: dict) -> None:
    print(f"{COMMUNITY}: {result['records']:,} records\n")
    for kind, count in sorted(result["by_type"].items(), key=lambda kv: -kv[1]):
        print(f"  {kind:<30} {count:>7,}")
    print(f"  {'unattributed':<30} {result['unattributed']:>7,}")
    got = result["profile"]
    print(f"\ncredential shape, sampled {got['sampled']} over "
          f"{len(got['pages_read'])} of {got['of_pages']} pages:")
    for kind, count in got["credential_types"].items():
        print(f"  {kind:<40} {count:>5}")
    print()
    for field, count in got["field_coverage"].items():
        share = count / got["sampled"]
        print(f"  {field:<40} {count:>5}  {share:>5.0%}")


def main(argv: list[str] | None = None) -> int:
    summary = (__doc__ or "").splitlines()
    parser = argparse.ArgumentParser(
        prog="python -m etl.probe_florida",
        description=summary[0] if summary else None)
    parser.add_argument("--json", action="store_true",
                        help="Print the result as JSON.")
    parser.add_argument("--record", action="store_true",
                        help=f"Write {RECORD.name} from this run.")
    args = parser.parse_args(argv)
    try:
        result = probe(quiet=args.json or args.record)
    except ValueError as refused:
        print(f"\nrefused: {refused}", file=sys.stderr)
        return 1
    except MalformedSource as bad:
        print(f"\nsource malformed: {bad}", file=sys.stderr)
        return 3
    except (HttpStatus, RuntimeError) as gone:
        print(f"\nsource unreachable: {gone}", file=sys.stderr)
        return 2

    if args.record:
        RECORD.parent.mkdir(parents=True, exist_ok=True)
        RECORD.write_text(json.dumps(
            {"_": RECORD_NOTE,
             "retrieved_at": datetime.date.today().isoformat(),
             **result}, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {RECORD.relative_to(ROOT)}")
    elif args.json:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

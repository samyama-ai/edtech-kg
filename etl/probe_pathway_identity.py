"""Which identifier can key a Pathway, measured across both publishers.

`Pathway` was declared keyed on `ctid` when the Credential Registry was the
only publisher in view, then moved to `url` by #82 when a district turned out
to publish pathways as pages and none of them carried a ctid. Both choices were
right for the publisher in front of them and neither is right for both, which
is #85.

That issue could be settled by argument. It should not be: the claim standing
behind it — that a Registry pathway "may have no stable public URL" — is a
*may*, and a key chosen on a may is a key chosen on a guess. This probe reads
all 98 published pathways and asks the two questions a key has to answer.

    Is it PRESENT on every record?     A key absent on some records gives those
                                       nodes a null key, which 1.1.0 accepts in
                                       silence because a constraint here
                                       declares the key and does not enforce
                                       it. That is the failure #82 avoided
                                       for the district.

    Is it DISTINCT across records?     A key repeated across two records
                                       merges two things into one node. This
                                       is the half the issue did not ask
                                       about, and it is where the answer
                                       actually turned.

Both questions are asked of both candidates, because "the other publisher's key
does not fit" is only half an argument until the fit of each is a number.

Registry data is read, not loaded — #56 decides whether it may be loaded
at all.
Reading published identifiers to choose a schema key does not wait on that, and
nothing here writes to a graph.

    python -m etl.probe_pathway_identity
    python -m etl.probe_pathway_identity --json
    python -m etl.probe_pathway_identity --record

No third-party dependency, as with the other probes.
"""

from __future__ import annotations

import collections
import json
import pathlib
import urllib.parse

import argparse
import datetime
import sys

from etl.registry_read import (REGISTRY, HttpStatus, MalformedSource, get,
                               parse, total)

#: The whole population fits in two pages, so this probe SAMPLES NOTHING. Every
#: figure below is a census, and the honesty caveat the other Registry probes
#: carry about sampling does not apply here — which is worth stating, because a
#: reader who knows `probe_registry` will assume it does.
PER_PAGE = 50

#: Where the record is written, and read back by
#: `tests/test_probe_pathway_identity.py`.
RECORD = (pathlib.Path(__file__).resolve().parent.parent
          / "docs" / "sources" / "pathway-identity-measured.json")

#: CTDL's identifier, and CTDL's "the page about this thing". These are the two
#: candidate keys, and they are the only two: a Registry pathway's `@id` is the
#: Registry's own graph address rather than the publisher's, so keying on it
#: would make the key a fact about where we read the data.
CTID = "ceterms:ctid"
WEBPAGE = "ceterms:subjectWebpage"

#: Written by the writer rather than left in the file for a refresh to preserve
#: by accident — the shape `engine-capability-measured.json` uses.
RECORD_NOTE = ("Measured by `python -m etl.probe_pathway_identity`. A census "
               "of every published pathway, not a sample.")


def one(value):
    """A CTDL value that may arrive bare, as a list, or as a language map.

    Returns the first usable string, or None. Assuming the bare form is what
    turned a stated prerequisite into a course with none in `probe_registry`;
    the same shape is handled the same way here rather than differently.
    """
    if isinstance(value, list):
        return one(value[0]) if value else None
    if isinstance(value, dict):
        return one(value.get("en-US") or value.get("en")
                   or next(iter(value.values()), None))
    return value if isinstance(value, str) and value.strip() else None


def pathways() -> list[dict]:
    """Every published pathway, as its `ceterms:Pathway` node.

    A Registry record wraps a JSON-LD document whose `@graph` holds the pathway
    together with its components, so the type filter is not decoration — taking
    the first node would silently read a `ceterms:PathwayComponent` instead.
    """
    population = total("/ce-registry/pathway/search")
    found: list[dict] = []
    page = 1
    while True:
        body = parse(get(f"{REGISTRY}/ce-registry/pathway/search"
                         f"?per_page={PER_PAGE}&page={page}"),
                     f"page {page} of the pathway search")
        if not isinstance(body, list):
            raise MalformedSource(
                f"page {page} of the pathway search was "
                f"{type(body).__name__}, not a list of records")
        if not body:
            break
        for record in body:
            graph = (record.get("decoded_resource") or {}).get("@graph") or []
            found += [n for n in graph
                      if n.get("@type") == "ceterms:Pathway"]
        page += 1
        if len(found) >= population if isinstance(population, int) else False:
            break
    return found


def fitness(nodes: list[dict], field: str) -> dict:
    """How well one candidate property would serve as the key.

    `collides` counts the records that would be LOST to a merge, not the number
    of repeated values — two records sharing a value lose one, three lose two.
    Reporting the repeated values instead would say "4" where seven records are
    at stake, and the reader would draw the wrong conclusion from a smaller
    number.
    """
    values = [one(node.get(field)) for node in nodes]
    present = [v for v in values if v is not None]
    repeated = {v for v in present if present.count(v) > 1}
    return {
        "records": len(nodes),
        "present": len(present),
        "absent": len(nodes) - len(present),
        "distinct": len(set(present)),
        "collides": len(present) - len(set(present)),
        # The two halves of a merge, and they are DIFFERENT NUMBERS: four
        # pages carrying 3, 2, 4 and 2 pathways is four shared values and
        # seven records lost. Both are quoted in the schema, so both are
        # recorded rather than one being re-derived from the other by a reader
        # who has no way to.
        "shared_values": len(repeated),
        # `len(nodes)` guards the vacuous case. With no records the three
        # counts are all 0 and every candidate reads as a perfect key — so a
        # Registry that went dark would confirm whichever key the schema
        # already used, which is the worst possible failure for a probe whose
        # only job is to unseat one.
        "usable_as_key": bool(nodes) and len(present) == len(nodes) == len(
            set(present)),
    }


def hosts(nodes: list[dict]) -> dict:
    """Who publishes the pages the Registry pathways point at.

    This answers the second acceptance criterion — whether the SAME pathway can
    arrive from both publishers and be duplicated. It can only happen where a
    Registry pathway's webpage is a page a district loader also reads, so the
    host list is the evidence, and today it is evidence of absence.
    """
    found = collections.Counter(
        urllib.parse.urlparse(url).netloc.lower()
        for url in (one(n.get(WEBPAGE)) for n in nodes) if url)
    return {"distinct": len(found), "top": dict(found.most_common(8))}


def probe(quiet: bool = False) -> dict:
    nodes = pathways()
    result = {
        "pathways": len(nodes),
        "candidates": {CTID: fitness(nodes, CTID),
                       WEBPAGE: fitness(nodes, WEBPAGE)},
        "webpage_hosts": hosts(nodes),
    }
    if not quiet:
        report(result)
    return result


def report(result: dict) -> None:
    print(f"Published pathways: {result['pathways']}\n")
    print(f"{'candidate':<24} {'present':>9} {'distinct':>9} "
          f"{'lost to merge':>14}  key?")
    for name, got in result["candidates"].items():
        print(f"{name:<24} {got['present']:>4}/{got['records']:<4} "
              f"{got['distinct']:>9} {got['collides']:>14}  "
              f"{'yes' if got['usable_as_key'] else 'NO'}")
    print(f"\nWebpages published across {result['webpage_hosts']['distinct']} "
          f"hosts:")
    for host, count in result["webpage_hosts"]["top"].items():
        print(f"  {count:>3}  {host}")


def main(argv: list[str] | None = None) -> int:
    """`probe_registry.run_cli` is deliberately NOT reused.

    It offers `--courses` and passes `sample=`, because both probes it serves
    sample a population too large to read. This one reads all 98, so accepting
    that flag would put a control on the interface that changes nothing — a
    lie in the help text, and the kind a reader only finds by trying it. The
    three exit categories are the ones that file defines, and they are the part
    worth keeping identical.
    """
    summary = (__doc__ or "").splitlines()
    parser = argparse.ArgumentParser(
        prog="python -m etl.probe_pathway_identity",
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
        print(f"wrote {RECORD.relative_to(RECORD.parent.parent.parent)}")
    elif args.json:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

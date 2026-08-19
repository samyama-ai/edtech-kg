"""Probe CTDL — the vocabulary, and the Registry that publishes against it.

Two separate things, deliberately kept apart:

  the vocabulary   `credreg.net/ctdl/schema/encoding/json` — CC BY 4.0, and the
                   thing we might adopt terms from
  the Registry     `credentialengineregistry.org` — data published by many
                   organisations under their own terms, which are NOT the
                   vocabulary's licence (#56)

    python -m etl.probe_ctdl                 # both tables
    python -m etl.probe_ctdl --json          # machine-readable
    python -m etl.probe_ctdl --courses 600   # sample N courses for prerequisites

The Registry half lives in `etl/probe_registry.py` and is imported here, so the
two sources are measured in one place each while this command still prints both
tables together.

The number this exists to produce is the last one: **how many published courses
carry a resolvable prerequisite.** CTDL defines `ceterms:prerequisite` as a
Course-to-Course reference; whether anyone uses it is a different question from
whether it exists, and #28 could only answer the first.

No third-party dependency, as with the other probes.
"""

from __future__ import annotations

from datetime import datetime, timezone

# The Registry is a different source with a different licence, so it has its own
# probe. Imported rather than duplicated — one place measures it. `get` carries
# the shared User-Agent, which is why this module defines none of its own.
from etl.probe_registry import (MalformedSource, course_prerequisites, get, parse,
                                print_prerequisites, print_registry, registry_totals,
                                run_cli)

VOCAB = "https://credreg.net/ctdl/schema/encoding/json"


def vocabulary() -> dict:
    """Count the published vocabulary by RDF type."""
    payload = get(VOCAB)
    if not payload.lstrip().startswith(b"{"):
        # MalformedSource, not ValueError: an HTML error page and a truncated
        # JSON body are the same class of failure and were exiting under two
        # different categories.
        raise MalformedSource(
            f"{VOCAB} did not return JSON — got {payload[:40]!r}. A 200 carrying "
            f"an error page would otherwise be counted as zero classes."
        )
    graph = parse(payload, VOCAB).get("@graph") or []
    if not graph:
        raise ValueError("the CTDL graph is empty — refusing to report that as a count")

    counts: dict[str, int] = {}
    for node in graph:
        counts[node.get("@type", "?")] = counts.get(node.get("@type", "?"), 0) + 1

    def prop(pid):
        n = next((x for x in graph if x.get("@id") == pid), None)
        if not n:
            return None
        def ids(v):
            if isinstance(v, list):
                return [x.get("@id") if isinstance(x, dict) else x for x in v]
            return [v.get("@id")] if isinstance(v, dict) else ([v] if v else [])
        return {
            # Named as the source names them. These are `…Includes` lists, which
            # are deliberately non-committal — not rdfs:domain / rdfs:range, and
            # carrying no entailment. Printing them as domain/range would claim
            # more than CTDL says.
            "domainIncludes": ids(n.get("schema:domainIncludes")),
            "rangeIncludes": ids(n.get("schema:rangeIncludes")),
        }

    return {
        "source": VOCAB,
        "terms": len(graph),
        "by_type": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
        "pathway_classes": sorted(
            n["@id"] for n in graph
            if n.get("@type") == "rdfs:Class"
            and any(w in n["@id"].lower() for w in ("pathway", "component", "condition"))
        ),
        "prerequisite": prop("ceterms:prerequisite"),
        "isPreparationFor": prop("ceterms:isPreparationFor"),
    }


def probe(sample: int = 600, quiet: bool = False) -> dict:
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    vocab, registry = vocabulary(), registry_totals()
    prereq = course_prerequisites(sample)

    if not quiet:
        print(f"\nCTDL vocabulary — {vocab['source']}\n")
        print(f"  terms {vocab['terms']:>8,}")
        for k, v in vocab["by_type"].items():
            print(f"    {k:24} {v:>6,}")
        print(f"    {'pathway-related classes':24} {len(vocab['pathway_classes']):>6}")

        print_registry(registry)
        print_prerequisites(prereq)
        print(f"\n  measured {stamp}")
        print("  reproduce with: python -m etl.probe_ctdl\n")

    return {"retrieved_at": stamp, "vocabulary": vocab,
            "registry": registry, "course_prerequisites": prereq}


def main(argv: list[str] | None = None) -> int:
    return run_cli(argv, __doc__, probe, "etl.probe_ctdl")


if __name__ == "__main__":
    raise SystemExit(main())

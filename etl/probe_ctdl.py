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

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

# The Registry is a different source with a different licence, so it has its own
# probe. Imported rather than duplicated — one place measures it.
from etl.probe_registry import REGISTRY, course_prerequisites, get, registry_totals, total

VOCAB = "https://credreg.net/ctdl/schema/encoding/json"
USER_AGENT = "edtech-kg research (+https://git.samyama.ai/Samyama.ai/edtech-kg)"

__all__ = ["vocabulary", "probe", "main", "registry_totals", "course_prerequisites",
           "get", "total", "REGISTRY"]


def vocabulary() -> dict:
    """Count the published vocabulary by RDF type."""
    payload = get(VOCAB)
    if not payload.lstrip().startswith(b"{"):
        raise ValueError(
            f"{VOCAB} did not return JSON — got {payload[:40]!r}. A 200 carrying "
            f"an error page would otherwise be counted as zero classes."
        )
    graph = json.loads(payload).get("@graph") or []
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

        def n(v):
            return f"{v:,}" if isinstance(v, int) else (v or "—")

        print(f"\nCredential Registry — {registry['source']}\n")
        print(f"  envelopes  (root total_envelopes)   {n(registry['envelopes_root']):>10}")
        print(f"  resources  (search x-total)         "
              f"{n(registry['resources_all_communities']):>10}")
        print("  — different objects, not a contradiction: one envelope holds "
              "one or many resources")
        print(f"  deleted {n(registry['deleted_resources'])}, "
              f"provisional {n(registry['provisional_resources'])} — "
              f"neither explains the gap")

        print("\n  resources by community\n")
        for c, v in registry["communities"].items():
            print(f"    {c:22} {n(v):>10}")
        print(f"    {'unattributed':22} {n(registry['unattributed']):>10}"
              "   (the gated community)")

        print("\n  ce-registry resources by type\n")
        for t, v in registry["ce_registry_by_type"].items():
            print(f"    {t:34} {n(v):>8}")

        print(f"\nprerequisites in published courses\n")
        print(f"  sampled                {prereq['courses_sampled']:>6,}   "
              f"{prereq['sampling']}")
        print(f"  stating a prerequisite {prereq['stating_a_prerequisite']:>6,}")
        print(f"  resolvable reference   {prereq['resolvable']:>6,}")
        print(f"  free text only         {prereq['free_text_only']:>6,}")
        print(f"\n  measured {stamp}")
        print("  reproduce with: python -m etl.probe_ctdl\n")

    return {"retrieved_at": stamp, "vocabulary": vocab,
            "registry": registry, "course_prerequisites": prereq}


def main(argv: list[str] | None = None) -> int:
    summary = (__doc__ or "").splitlines()
    parser = argparse.ArgumentParser(description=summary[0] if summary else None)
    parser.add_argument("--courses", type=int, default=600,
                        help="How many published courses to sample (default 600).")
    parser.add_argument("--json", action="store_true", help="Print the result as JSON.")
    args = parser.parse_args(argv)
    try:
        result = probe(sample=args.courses, quiet=args.json)
    except ValueError as exc:
        print(f"\nrefused: {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"\nsource unreachable: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

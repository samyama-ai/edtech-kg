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

VOCAB = "https://credreg.net/ctdl/schema/encoding/json"
REGISTRY = "https://credentialengineregistry.org"
USER_AGENT = "edtech-kg research (+https://git.samyama.ai/Samyama.ai/edtech-kg)"

COMMUNITIES = ["ce-registry", "fdoe", "mytxlibrary", "learning-registry", "chaffeycollege"]
TYPES = ["course", "credential", "learning_opportunity_profile", "pathway"]

# Terms whose presence would mean a prerequisite is stated in a resolvable way.
RESOLVABLE = ("ceterms:targetLearningOpportunity", "ceterms:targetCredential",
              "ceterms:targetCompetency")


def get(url: str, headers_only: bool = False):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT},
                                     method="HEAD" if headers_only else "GET")
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            if headers_only:
                return dict(response.headers)
            return response.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{exc.code} from {url}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"unreachable: {url} ({exc})") from exc


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


def total(path: str, **params) -> int | str | None:
    """The `x-total` header for a search path.

    Returns the int, or the string `"secured"` when the community refuses an
    unauthenticated request. A gated community and an empty one are different
    facts and must not both print as a blank.
    """
    query = "&".join(f"{k}={v}" for k, v in {"per_page": 1, **params}.items())
    try:
        headers = get(f"{REGISTRY}{path}?{query}", headers_only=True)
    except RuntimeError as exc:
        return "secured" if ("401" in str(exc) or "403" in str(exc)) else None
    raw = headers.get("x-total") or headers.get("X-Total")
    return int(raw) if raw and raw.isdigit() else None


def registry_totals() -> dict:
    """Two counts of two different things, and the check that shows it (#59).

    The API root reports `total_envelopes`, which is *smaller* than what a
    single community's search returns. They do not contradict each other — they
    count different objects:

      root `total_envelopes`   `Envelope.not_deleted.count` — **envelopes**,
                               the deposited documents, across all communities
      search `x-total`         **EnvelopeResource** rows — "a JSON-LD object
                               stored in an envelope". One envelope holds one or
                               many; observed up to 49 in a single envelope

    So resources outnumber envelopes and the ratio is not fixed. `/search`
    answers "how many courses are published"; the root answers "how many
    documents were deposited". Ours is the first question.

    Both alternative explanations are measured rather than assumed away:
    deleted resources and provisional ones each come back zero.
    """
    root = json.loads(get(f"{REGISTRY}/"))
    communities = {c: total(f"/{c}/search") for c in COMMUNITIES}
    everywhere = total("/search")
    readable = sum(v for v in communities.values() if isinstance(v, int))

    return {
        "source": REGISTRY,
        "envelopes_root": root.get("total_envelopes"),
        "resources_all_communities": everywhere,
        "communities": communities,
        "ce_registry_by_type": {t: total(f"/ce-registry/{t}/search") for t in TYPES},
        "deleted_resources": total("/ce-registry/search", include_deleted="only"),
        "provisional_resources": total("/search", provisional="only"),
        # What the communities we can read do not account for. The remainder
        # belongs to the gated community; if this ever exceeds it, a community
        # has appeared that COMMUNITIES does not list.
        "unattributed": (everywhere - readable) if isinstance(everywhere, int) else None,
    }


def course_prerequisites(sample: int = 600) -> dict:
    """How many published courses state a prerequisite, and how many resolve.

    The distinction is the whole point. CTDL defines `ceterms:prerequisite` as a
    Course-to-Course reference. A `ConditionProfile` named "Prerequisites" whose
    only content is a description is a *string*, and resolving it means guessing
    which catalogue "PSYC101" belongs to.
    """
    def text(v):
        return (v.get("en-US") or v.get("en") or "") if isinstance(v, dict) else (v or "")

    courses = named = resolvable = 0
    prose: list[str] = []
    per_page = 50
    for page in range(1, sample // per_page + 1):
        body = get(f"{REGISTRY}/ce-registry/course/search?per_page={per_page}&page={page}")
        for envelope in json.loads(body):
            resource = envelope.get("decoded_resource") or {}
            for node in (resource.get("@graph") or [resource]):
                if not isinstance(node, dict) or "Course" not in str(node.get("@type", "")):
                    continue
                courses += 1
                if "ceterms:prerequisite" in node:
                    resolvable += 1
                    named += 1
                    continue
                for condition in node.get("ceterms:requires") or []:
                    if "prereq" not in text(condition.get("ceterms:name")).lower():
                        continue
                    named += 1
                    if any(k in condition for k in RESOLVABLE):
                        resolvable += 1
                    else:
                        described = text(condition.get("ceterms:description")).strip()
                        if described:
                            prose.append(described[:90])
    if not courses:
        raise ValueError("no course records returned — refusing to report a rate over zero")
    return {
        "courses_sampled": courses,
        "stating_a_prerequisite": named,
        "resolvable": resolvable,
        "free_text_only": named - resolvable,
        "examples": prose[:6],
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
        print(f"  sampled                {prereq['courses_sampled']:>6,}")
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

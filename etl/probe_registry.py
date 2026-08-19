"""Probe the Credential Engine Registry — what is published, and how.

The Registry is where CTDL-described records actually live. #53 asked what it
holds; #59 asked why its own two totals disagree. Both are answered by running
this.

    python -m etl.probe_registry                 # the tables
    python -m etl.probe_registry --json          # machine-readable
    python -m etl.probe_registry --courses 600   # sample N courses

Kept separate from `probe_ctdl.py` on purpose. **The vocabulary and the Registry
are different sources with different licences** — CTDL is CC BY 4.0, while the
records here are published by many organisations under their own terms (#56).
Merging the two probes would blur exactly the distinction #56 exists to protect.

The number this exists to produce is the last table: **how many published
courses carry a resolvable prerequisite.** CTDL defines `ceterms:prerequisite`
as a Course-to-Course reference; whether anyone uses it is a different question
from whether it exists.

No third-party dependency, as with the other probes.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
import urllib.parse
from datetime import datetime, timezone

REGISTRY = "https://credentialengineregistry.org"
USER_AGENT = "edtech-kg research (+https://git.samyama.ai/Samyama.ai/edtech-kg)"

COMMUNITIES = ["ce-registry", "fdoe", "mytxlibrary", "learning-registry", "chaffeycollege"]
TYPES = ["course", "credential", "learning_opportunity_profile", "pathway"]

# Terms whose presence would mean a prerequisite is stated in a resolvable way.
RESOLVABLE = ("ceterms:targetLearningOpportunity", "ceterms:targetCredential",
              "ceterms:targetCompetency")

PER_PAGE = 50


class HttpStatus(RuntimeError):
    """A failed request that knows its own status code.

    The code used to be recovered by searching the exception text for "401",
    which a URL containing those digits would satisfy.
    """

    def __init__(self, code: int | None, url: str, detail: str = ""):
        super().__init__(f"{code or 'unreachable'} from {url}{detail}")
        self.code = code


class MalformedSource(Exception):
    """Reachable, but the body did not parse.

    `json.JSONDecodeError` subclasses `ValueError`, so a corrupt body used to
    exit under "refused" — the category reserved for figures we decline to
    report — rather than being flagged as a broken source.
    """


def get(url: str, headers_only: bool = False):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT},
                                     method="HEAD" if headers_only else "GET")
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            if headers_only:
                return response.headers
            return response.read()
    except urllib.error.HTTPError as exc:
        raise HttpStatus(exc.code, url) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise HttpStatus(None, url, f" ({exc})") from exc


def total(path: str, **params) -> int | str | None:
    """The `x-total` header for a search path.

    Returns the int, or the string `"secured"` when the community refuses an
    unauthenticated request. A gated community and an empty one are different
    facts and must not both print as a blank.
    """
    query = urllib.parse.urlencode({"per_page": 1, **params})
    try:
        headers = get(f"{REGISTRY}{path}?{query}", headers_only=True)
    except HttpStatus as exc:
        return "secured" if exc.code in (401, 403) else None
    # HTTPMessage looks up case-insensitively; dict() threw that away.
    raw = headers.get("x-total")
    return int(raw) if raw and str(raw).isdigit() else None


def parse(payload: bytes, what: str):
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise MalformedSource(f"{what} did not parse as JSON ({exc})") from exc


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
    root = parse(get(f"{REGISTRY}/"), "the API root")
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


def sample_pages(wanted: int, population: int | None) -> tuple[list[int], int, str]:
    """Which pages to read, and an honest description of how they were chosen.

    Reading pages 1..N consecutively is not a sample of the Registry — it is a
    sample of whatever sorts first, which one publisher's bulk upload can
    dominate. Instead the pages are spread at a fixed stride across the whole
    result set, which is deterministic (so the figure is reproducible) and not
    concentrated at the head.

    It is still not a random sample, and the returned description says so
    rather than letting the reader assume otherwise.
    """
    if wanted < 1:
        raise ValueError(f"--courses must be at least 1, got {wanted}")

    pages_wanted = max(1, wanted // PER_PAGE)
    # A request below one page reads one short page, not a full one. This is the
    # only place the size is decided; the fetch loop uses what it returns.
    size = min(PER_PAGE, wanted) if pages_wanted == 1 else PER_PAGE

    if not isinstance(population, int) or population <= 0:
        return (list(range(1, pages_wanted + 1)), size,
                f"first {pages_wanted} page(s) of {size} — population unknown, "
                f"so the pages could not be spread; biased toward whatever sorts first")

    total_pages = max(1, -(-population // PER_PAGE))
    if total_pages <= pages_wanted:
        return (list(range(1, total_pages + 1)), size,
                f"every page — {population:,} records is the whole population, not a sample")

    if pages_wanted == 1:
        return ([1], size, f"the first {size} of {population:,} records — a single page, "
                           f"so nothing is spread; biased toward whatever sorts first")

    stride = total_pages // pages_wanted
    pages = [1 + i * stride for i in range(pages_wanted)]
    # Stating the reach honestly: a fixed stride from page 1 stops short of the
    # end, so the tail is never seen. "Spread across all N pages" overstated it.
    return (pages, size,
            f"{pages_wanted} pages of {size} at a stride of {stride}, reaching pages "
            f"{pages[0]}-{pages[-1]} of {total_pages:,} ({population:,} records); "
            f"the last {total_pages - pages[-1]:,} pages are not sampled — "
            f"deterministic, not random")


def course_prerequisites(sample: int = 600) -> dict:
    """How many published courses state a prerequisite, and how many resolve.

    The distinction is the whole point. CTDL defines `ceterms:prerequisite` as a
    Course-to-Course reference. A `ConditionProfile` named "Prerequisites" whose
    only content is a description is a *string*, and resolving it means guessing
    which catalogue "PSYC101" belongs to.

    Publisher spread is reported alongside the rate. A verdict drawn from a
    sample that turns out to be three publishers is a fact about those three,
    and the reader should be able to see that without asking.
    """
    def text(v):
        """A CTDL language map, which is a dict, a bare string, or a list of
        either. A list-valued map used to read as empty, which silently turned a
        stated prerequisite into a course with none."""
        if isinstance(v, list):
            return " ".join(text(i) for i in v)
        if isinstance(v, dict):
            value = v.get("en-US") or v.get("en") or next(iter(v.values()), "")
            return text(value)
        return v or ""

    def as_list(v):
        """`ceterms:requires` is a list when a course has several conditions and
        a bare object when it has one. Assuming the list raised AttributeError
        on the single-condition form."""
        if v is None:
            return []
        return v if isinstance(v, list) else [v]

    population = total("/ce-registry/course/search")
    pages, size, how = sample_pages(sample, population)

    courses = named = resolvable = 0
    prose: list[str] = []
    publishers: set[str] = set()
    for page in pages:
        if courses >= sample:
            break                       # the cap ends the walk, not just the page
        body = get(f"{REGISTRY}/ce-registry/course/search"
                   f"?per_page={size}&page={page}")
        for envelope in parse(body, f"page {page} of the course search"):
            if courses >= sample:
                break
            resource = envelope.get("decoded_resource") or {}
            for node in (resource.get("@graph") or [resource]):
                # Checked per course, not per envelope: one @graph can carry
                # many Course nodes and used to push the count past the cap.
                if courses >= sample:
                    break
                if not isinstance(node, dict) or "Course" not in str(node.get("@type", "")):
                    continue
                courses += 1
                publishers.add(str(envelope.get("published_by")
                                   or envelope.get("owned_by") or "unknown"))
                if "ceterms:prerequisite" in node:
                    resolvable += 1
                    named += 1
                    continue
                for condition in as_list(node.get("ceterms:requires")):
                    if not isinstance(condition, dict):
                        continue
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
        "population": population,
        "sampling": how,
        "pages_read": pages,
        "distinct_publishers": len(publishers),
        "stating_a_prerequisite": named,
        "resolvable": resolvable,
        "free_text_only": named - resolvable,
        "examples": prose[:6],
    }


def probe(sample: int = 600, quiet: bool = False) -> dict:
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    registry = registry_totals()
    prereq = course_prerequisites(sample)

    def n(v):
        return f"{v:,}" if isinstance(v, int) else (v or "—")

    if not quiet:
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

        print("\nprerequisites in published courses\n")
        print(f"  sampled                {prereq['courses_sampled']:>6,}   "
              f"{prereq['sampling']}")
        print(f"  stating a prerequisite {prereq['stating_a_prerequisite']:>6,}")
        print(f"  resolvable reference   {prereq['resolvable']:>6,}")
        print(f"  free text only         {prereq['free_text_only']:>6,}")
        print(f"\n  measured {stamp}")
        print("  reproduce with: python -m etl.probe_registry\n")

    return {"retrieved_at": stamp, "registry": registry,
            "course_prerequisites": prereq}


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
    except MalformedSource as exc:
        print(f"\nsource malformed: {exc}", file=sys.stderr)
        return 3
    if args.json:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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
# A resolvable prerequisite points at something a learner completes. A
# competency target is a different claim — it says what you must be able to do,
# not which course you must have taken — so it is deliberately not here. The
# page argues about the Course -> Course edge and this list must match it.
RESOLVABLE = ("ceterms:targetLearningOpportunity", "ceterms:targetCredential")

PER_PAGE = 50
MAX_EXAMPLES = 6     # enough to check the "free text" claim, not to reproduce the sample
EXAMPLE_CHARS = 90   # a prerequisite string is short; this is a display bound


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
        # Three different facts, three different answers. "secured" is a claim
        # about the community; anything else is a claim about the request, and
        # print_registry must not label the remainder "the gated community"
        # when a community merely failed.
        if exc.code in (401, 403):
            return "secured"
        return f"error {exc.code}" if exc.code else "unreachable"
    # HTTPMessage looks up case-insensitively; dict() threw that away.
    raw = headers.get("x-total")
    if raw and str(raw).isdigit():
        return int(raw)
    # Answered, but not with a count. Degrading this to None reads as "unknown
    # population" and silently widens the sampling caveat instead of saying the
    # source is broken.
    return "no x-total header"


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
    secured = [c for c, v in communities.items() if v == "secured"]
    failed = [c for c, v in communities.items()
              if not isinstance(v, int) and v != "secured"]

    return {
        "source": REGISTRY,
        "envelopes_root": root.get("total_envelopes"),
        "resources_all_communities": everywhere,
        "communities": communities,
        "ce_registry_by_type": {t: total(f"/ce-registry/{t}/search") for t in TYPES},
        # Both ce-registry-scoped. They were printed side by side against a
        # global gap while one was global and one was not, so the comparison
        # did not say what it looked like it said.
        "deleted_resources": total("/ce-registry/search", include_deleted="only"),
        "provisional_resources": total("/ce-registry/search", provisional="only"),
        # What the readable communities do not account for. The remainder
        # belongs to the gated community; if it ever exceeds what that can hold,
        # a community exists which COMMUNITIES does not list.
        #
        # `unreadable_communities` names the ones that did not answer, so the
        # remainder is not quietly absorbing an error and reading as records.
        "secured_communities": secured,
        "failed_communities": failed,
        "unattributed": (everywhere - readable) if isinstance(everywhere, int) else None,
    }


def describe(read: list[int], size: int, population: int | None) -> str:
    """How the sample was actually taken.

    Takes the pages that were *read*, never the pages that were planned. The
    two differ whenever the per-course cap ends the walk early, and describing
    the plan let the documents quote a reach the run did not have.
    """
    if not read:
        return "nothing was read"
    if not isinstance(population, int) or population <= 0:
        return (f"{len(read)} page(s) of {size} — population unknown, so the pages "
                f"could not be spread; biased toward whatever sorts first")

    total_pages = max(1, -(-population // PER_PAGE))
    if len(read) >= total_pages:
        return f"every page — {population:,} records is the whole population, not a sample"
    if len(read) == 1:
        return (f"the first {size} of {population:,} records — a single page, so nothing "
                f"is spread; biased toward whatever sorts first")

    stride = read[1] - read[0]
    tail = total_pages - read[-1]
    return (f"{len(read)} pages of {size} at a stride of {stride}, reaching pages "
            f"{read[0]}-{read[-1]} of {total_pages:,} ({population:,} records); "
            f"the last {tail:,} pages are not sampled — deterministic, not random")


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
    # Ceiling, not floor: --courses 130 asked for three pages' worth and got
    # two, silently sampling 100. The per-course cap trims the overshoot.
    pages_wanted = max(1, -(-wanted // PER_PAGE))
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
        # Anything else — a number, a bool — becomes a string rather than being
        # handed to .lower() as-is.
        return v if isinstance(v, str) else ("" if v is None else str(v))

    def as_list(v):
        """`ceterms:requires` is a list when a course has several conditions and
        a bare object when it has one. Assuming the list raised AttributeError
        on the single-condition form."""
        if v is None:
            return []
        return v if isinstance(v, list) else [v]

    population = total("/ce-registry/course/search")
    planned, size, _ = sample_pages(sample, population)
    read: list[int] = []

    courses = named = resolvable = stated_but_empty = 0
    prose: list[str] = []
    publishers: set[str] = set()
    for page in planned:
        if courses >= sample:
            break                       # the cap ends the walk, not just the page
        read.append(page)
        body = get(f"{REGISTRY}/ce-registry/course/search"
                   f"?per_page={size}&page={page}")
        page_body = parse(body, f"page {page} of the course search")
        if not isinstance(page_body, list):
            raise MalformedSource(
                f"page {page} of the course search returned "
                f"{type(page_body).__name__}, not a list of envelopes")
        for envelope in page_body:
            if courses >= sample:
                break
            if not isinstance(envelope, dict):
                continue        # the list shape is checked; its elements are not
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
                # Per COURSE, not per condition. Without these flags a course
                # carrying "Prerequisites" and "Prerequisite (recommended)"
                # incremented the count twice, so the figure counted profiles
                # while the documents read it as a share of courses.
                states = resolves = empty = False

                typed = node.get("ceterms:prerequisite")
                if typed:
                    # Present but empty is not a reference. Counting the key
                    # alone would credit the Registry with resolvable edges it
                    # does not publish — the opposite of this probe's finding.
                    states = True
                    resolves = any(isinstance(v, (dict, str)) and v for v in as_list(typed))

                for condition in as_list(node.get("ceterms:requires")):
                    if not isinstance(condition, dict):
                        continue
                    if "prereq" not in text(condition.get("ceterms:name")).lower():
                        continue
                    # Truthy, not merely present — the same test the typed branch
                    # above applies. A present-but-empty targetCredential is not
                    # a reference, and counting it would inflate the one number
                    # this module exists to produce.
                    if any(condition.get(k) for k in RESOLVABLE):
                        states = resolves = True
                        continue
                    described = text(condition.get("ceterms:description")).strip()
                    # "Prerequisites: None" is a statement that there are none.
                    # An absent or empty description says nothing at all. Neither
                    # is free text naming a course, and counting either inflates
                    # the rate the documents quote.
                    if described and described.lower() not in ("none", "n/a", "na", "-"):
                        states = True
                        prose.append(described[:EXAMPLE_CHARS])
                    else:
                        empty = True

                named += states
                resolvable += resolves
                stated_but_empty += empty and not states
    if not courses:
        raise ValueError("no course records returned — refusing to report a rate over zero")
    # Described AFTER the walk, from the pages actually fetched. Describing the
    # plan let the documents quote a reach the run did not have whenever the cap
    # ended the walk early — the same failure the "does not claim the tail it
    # skips" fix addresses one level up.
    return {
        "courses_sampled": courses,
        "population": population,
        "sampling": describe(read, size, population),
        "pages_read": read,
        "distinct_publishers": len(publishers),
        "stating_a_prerequisite": named,
        "resolvable": resolvable,
        "free_text_only": named - resolvable,
        # A prerequisite block carrying nothing — no description, an empty one,
        # or the word "None". Reported rather than folded into either figure.
        "stated_but_empty": stated_but_empty,
        "examples": prose[:MAX_EXAMPLES],
    }


def print_registry(registry: dict) -> None:
    """The Registry tables.

    Lives here so `probe_ctdl` can print them without carrying a second copy —
    the two had drifted apart already, which is what a duplicated block does.
    """
    def n(v):
        return f"{v:,}" if isinstance(v, int) else (v or "—")

    print(f"\nCredential Registry — {registry['source']}\n")
    print(f"  envelopes  (root total_envelopes)   {n(registry['envelopes_root']):>10}")
    print(f"  resources  (search x-total)         "
          f"{n(registry['resources_all_communities']):>10}")
    print("  — different objects, not a contradiction: one envelope holds "
          "one or many resources")
    print(f"  ce-registry deleted {n(registry['deleted_resources'])}, "
          f"provisional {n(registry['provisional_resources'])} — "
          f"neither explains the gap")

    print("\n  resources by community\n")
    for community, value in registry["communities"].items():
        print(f"    {community:22} {n(value):>10}")
    secured = registry.get("secured_communities") or []
    failed = registry.get("failed_communities") or []
    if failed:
        note = (f"   — {len(failed)} community/ies did not answer "
                f"({', '.join(failed)}), so this is not attributable")
    elif len(secured) == 1:
        note = f"   (the gated community: {secured[0]})"
    else:
        note = f"   ({len(secured)} gated communities, so not attributable to one)"
    print(f"    {'unattributed':22} {n(registry['unattributed']):>10}{note}")

    print("\n  ce-registry resources by type\n")
    for kind, value in registry["ce_registry_by_type"].items():
        print(f"    {kind:34} {n(value):>8}")


def probe(sample: int = 600, quiet: bool = False) -> dict:
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    registry = registry_totals()
    prereq = course_prerequisites(sample)

    if not quiet:
        print_registry(registry)

        print("\nprerequisites in published courses\n")
        print(f"  sampled                {prereq['courses_sampled']:>6,}   "
              f"{prereq['sampling']}")
        print(f"  stating a prerequisite {prereq['stating_a_prerequisite']:>6,}")
        print(f"  resolvable reference   {prereq['resolvable']:>6,}")
        print(f"  free text only         {prereq['free_text_only']:>6,}")
        if prereq["stated_but_empty"]:
            print(f"  stated but empty       {prereq['stated_but_empty']:>6,}"
                  f"   — a prerequisite block carrying nothing")
        print(f"  across                 {prereq['distinct_publishers']:>6,} "
              f"distinct publishers")
        print(f"\n  measured {stamp}")
        print("  reproduce with: python -m etl.probe_registry\n")

    return {"retrieved_at": stamp, "registry": registry,
            "course_prerequisites": prereq}


def positive(value: str) -> int:
    """A CLI argument check. Bad input is argparse's job — exiting under
    "refused" would put it in the category this module reserves for figures it
    declines to report, which is a different thing entirely."""
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError(f"must be at least 1, got {number}")
    return number


def main(argv: list[str] | None = None) -> int:
    summary = (__doc__ or "").splitlines()
    parser = argparse.ArgumentParser(description=summary[0] if summary else None)
    parser.add_argument("--courses", type=positive, default=600,
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

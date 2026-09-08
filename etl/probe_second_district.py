"""Does a second district's prerequisites resolve the way PWCS's do?

    python -m etl.probe_second_district --record

edtech-kg#19. PWCS was measured at 982 course pages and 89% of named
prerequisites resolving. **That single number decides what kind of product
this is** — if a second district resolves comparably, prerequisites generalise
and this is national; if not, it is a per-district integration, which is a
different business.

The issue records an ASSUMPTION worth testing rather than repeating: PWCS runs
Clean Catalog, the vendor says it serves other districts, "so the structure may
repeat". The vendor's own K-12 page names its district clients, which is how
the four below were found — not by guessing at hostnames.

**Same method, same field, same sample size, seed recorded.** The comparison is
worthless otherwise: a different sampling rule on the second district would
measure the rule rather than the district.

What is measured, per district:

  * how many course pages the index publishes
  * how many of a seeded sample state a prerequisite at all
  * of those, how many state it as a LINK rather than as prose — this is the
    distinction the whole question turns on, because only a link resolves
  * of the links, how many point at a course page the same index publishes

Politeness: one request at a time, a delay between them, and a sample rather
than a sweep. Every district here allows course pages in robots.txt; the
disallow lists cover Drupal internals only.
"""

from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import random
import re
import sys
import time
import urllib.error
import urllib.request

from etl.course_page import (COURSE_PATH, HREF, classify,
                             same_host)
from etl.identity import USER_AGENT
from etl.provenance import write_record
from etl.pwcs_pages import PATHWAY_FIELD_PRESENT

ROOT = pathlib.Path(__file__).resolve().parents[1]
RECORD = ROOT / "docs" / "sources" / "second-district-measured.json"
RECORD_NOTE = (
    "Measured by `python -m etl.probe_second_district --record`. The same "
    "fields, the same classifier and the same seed on every district. The "
    "sample size is the same CEILING everywhere and is smaller where a "
    "district publishes fewer pages than the ceiling — see `sampled` and "
    "`read` per district, and divide by `read`, never by the ceiling. "
    "Enumeration differs by necessity: three districts publish no sitemap, "
    "which is recorded per district and is itself part of the finding.")

#: Clean Catalog's own K-12 client list, read from cleancatalog.com/k12/ on
#: 2026-09-08. Named there with a "View Site" link each, so these are the
#: vendor's clients rather than hosts that happened to answer.
DISTRICTS = {
    "PWCS (Prince William County, VA)": "https://catalog.pwcs.edu",
    "APS (Arlington, VA)": "https://catalog.apsva.us",
    "Clover Park (WA)": "https://catalog.cloverpark.k12.wa.us",
    "Kenosha (WI)": "https://catalogs.kusd.org",
    "Central Islip (NY)": "https://hs-catalogue.centralislip.k12.ny.us",
}




SEED = 19            #: The issue number, so the sample is reproducible and
                     #: nobody has to wonder whether it was chosen after the
                     #: fact.
SAMPLE = 60          #: Per district. Small enough to be polite, large enough
                     #: that a 0% and an 89% are not the same measurement.
DELAY = 0.4


class Unreachable(RuntimeError):
    """A district did not answer. Distinct from answering with no courses."""


class Refused(RuntimeError):
    """The host asked us to stop. Not a page that stated no prerequisite."""


def get(url: str) -> str:
    """One page, with the politeness delay INSIDE the request.

    The delay used to sit after each successful call, so it was skipped on
    exactly the paths where a host is struggling: a sitemap 404 fell straight
    into the crawl with no pause, and five failing index candidates fired five
    back-to-back requests. Here it is structurally unskippable.

    **An HTTP refusal is distinguished from a transport failure.** `URLError`
    is `HTTPError`'s parent, so catching it first swallowed a 429 — a district
    that began rate-limiting mid-sample got 59 more requests, and the
    throttled page landed in `unreachable`, quietly shrinking the denominator.
    """
    time.sleep(DELAY)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as refused:
        if refused.code == 429:
            wait = refused.headers.get("Retry-After")
            raise Refused(
                f"{url}: HTTP 429, Retry-After={wait!r}. Stopping rather than "
                f"finishing the sample — a throttled page counted as "
                f"unreachable would shrink the denominator silently.")
        raise Unreachable(f"{url}: HTTP {refused.code}") from refused
    except (urllib.error.URLError, TimeoutError, OSError) as gone:
        raise Unreachable(f"{url}: {gone}") from gone


def course_paths(base: str) -> tuple[list[str], dict]:
    """Every `/subject/course` path the catalogue's own index links to.

    Walked from the index rather than guessed: the districts do not agree on
    where the index lives — PWCS puts it at `/courses`, Arlington splits it
    across `/high-school-courses` and `/middle-school-courses` — so each
    candidate is tried and the results are pooled.

    A path is a course if it has exactly two segments. That is the vendor's
    shape, and it is what `etl/pwcs_source.py` already relies on; using a
    different rule here would measure the rule.
    """
    # **The sitemap decides the population; the crawl is measured beside it.**
    # PWCS's population comes from its sitemap and its index crawl finds a
    # fraction of the same catalogue — both counts are recorded rather than
    # one being described in prose. Using the crawl everywhere would have made
    # every district look small in the same wrong way: comparable and useless.
    #
    # Three of the five publish no sitemap at all, which is part of the
    # answer — the enumeration PWCS's own figure rests on does not generalise.
    #
    # HAS A SITEMAP and HAS COURSES IN IT are different facts, and the page
    # makes a claim about the first. Kenosha publishes a sitemap holding only
    # pathway pages, so it falls through to the crawl while still having one —
    # collapsing the two would have made the page say "four publish no
    # sitemap" when three do not and a fourth publishes one with no courses.
    has_sitemap, in_sitemap = False, 0
    try:
        sitemap = get(f"{base}/sitemap.xml")
        locs = re.findall(r"<loc>([^<]+)</loc>", sitemap)
        # A 200 IS NOT A SITEMAP. Setting the flag on the status alone made a
        # soft-404 — a themed "not found" page answering 200 — indistinguish-
        # able from Kenosha's real sitemap that happens to list no courses,
        # and the page states that distinction as fact. A document is a
        # sitemap when it parses as one.
        has_sitemap = bool(locs) and "<urlset" in sitemap
        # PREFIX strip, not replace-everywhere. `str.replace` would also cut
        # the host out of the middle of a path — harmless on these five and
        # not a thing to leave in a URL parser.
        paths = {u[len(base):] for u in locs if u.startswith(base)}
        courses = sorted(p for p in paths if COURSE_PATH.match(p))
        in_sitemap = len(courses)
    except Unreachable:
        pass

    # **The index crawl is run even when the sitemap worked**, because the
    # page quotes the gap between them — "an index crawl of PWCS finds 73 of
    # its 817" — and that figure lived in a code comment, which is the one
    # place this repo says a figure may not live.
    crawled = crawl(base)
    if in_sitemap:
        return sorted(courses), {"how": "sitemap", "has_sitemap": True,
                                 "courses_in_sitemap": in_sitemap,
                                 "courses_in_index_crawl": len(crawled)}

    return sorted(crawled), {"how": "index crawl", "has_sitemap": has_sitemap,
                             "courses_in_sitemap": in_sitemap,
                             "courses_in_index_crawl": len(crawled)}


#: Index pages are paginated and the pager is followed. Reading only the
#: first page found 73 of PWCS's 817 courses — and the sample was then drawn
#: from whatever the first page happened to link to, which is a biased subset
#: rather than a small one. The cap is a safety net, not an expectation.
MAX_PAGES = 40


def crawl(base: str) -> set[str]:
    """Course paths the catalogue's own index pages link to, following the pager.

    The districts do not agree on where the index lives, so each candidate is
    tried and the results pooled. Drupal paginates with `?page=n` and stops
    yielding new paths at the end, which is what terminates this — not the
    cap.
    """
    found: set[str] = set()
    for index in ("/courses", "/high-school-courses", "/middle-school-courses",
                  "/high-school-course-catalog", ""):
        # **Per candidate**, not against everything seen so far. Subtracting
        # the global set meant an index whose first page happened to link only
        # paths another index had already yielded was abandoned entirely —
        # every later page of it included. Reproduced: two real courses lost.
        # The pager's own repetition is what should stop it, and that is a
        # fact about this index rather than about the ones before it.
        seen_here: set[str] = set()
        for page in range(MAX_PAGES):
            url = f"{base}{index}" + (f"?page={page}" if page else "")
            try:
                markup = get(url)
            except Unreachable:
                break
            here = {path for path in
                    (same_host(href, base) for href in HREF.findall(markup))
                    if path}
            if not here - seen_here:
                # This index has stopped yielding paths IT has not already
                # yielded: the pager has run out, or the page does not
                # paginate. Both mean move to the next candidate.
                break
            seen_here |= here
        found |= seen_here
    return found












def district(name: str, base: str, sample: int = SAMPLE) -> dict:
    """One district, measured the same way as every other."""
    paths, how = course_paths(base)
    if not paths:
        # THE SAME KEYS as every other district. A short entry is a KeyError
        # waiting for the first consumer that iterates the record, and it
        # reads as a missing measurement rather than a measured zero.
        return {"base": base, **how, "candidate_course_paths": 0,
                "sampled": 0, "read": 0, "unreachable": 0,
                "sampled_but_not_a_course": 0, "kinds": {},
                "state_a_prerequisite_in_either_field": 0,
                "percent_stating_in_either_field": None,
                "with_a_typed_prerequisite": 0,
                "percent_of_pages_with_a_typed_prerequisite": None,
                "links": 0, "links_resolving_to_a_published_course": 0,
                "percent_of_links_that_resolve": None,
                "with_a_nonempty_prose_field": 0, "prose_examples": [],
                "note": "the catalogue publishes no two-segment course paths "
                        "— pathway pages only — so there is nothing to attach "
                        "a prerequisite to and no sample to draw"}

    published = set(paths)
    # Seeded and sorted first, so the sample does not depend on the order the
    # index happened to emit links in.
    chosen = random.Random(SEED).sample(paths, min(sample, len(paths)))

    kinds: dict[str, int] = {}
    links = resolved = 0
    examples: list[dict] = []
    for path in chosen:
        try:
            markup = get(f"{base}{path}")
        except Unreachable:
            kinds["unreachable"] = kinds.get("unreachable", 0) + 1
            # Sleep on the FAILURE path too. Skipping it meant a host that
            # started refusing got hammered at full speed — the opposite of
            # what politeness is for.
            continue
        # **A pathway page is not a course**, and the repo already says so.
        # `etl/pwcs_pages.classify` decides by the MARKUP — a page rendering
        # the pathway course-table field is a pathway at any depth — and
        # `docs/schema.md` quotes every PWCS rate against the 791 courses,
        # not the 960 pages. Counting two-segment paths alone put pathway
        # pages, which carry no prerequisite field, into the denominator and
        # deflated the very percentage the conclusion rests on.
        if PATHWAY_FIELD_PRESENT.search(markup):
            kinds["not a course"] = kinds.get("not a course", 0) + 1
            continue

        found = classify(markup, published, base)
        kinds[found["kind"]] = kinds.get(found["kind"], 0) + 1
        if found["kind"] == "typed":
            links += len(found["links"])
            resolved += len(found["resolved"])
        # EIGHT, not four. The page argues from these about what the prose
        # field contains, and four is thin evidence for a claim that carries
        # a conclusion.
        if found["kind"] == "prose" and len(examples) < 8:
            examples.append({"path": path, "text": found["text"]})

    # Pages fetched, answered, AND found to be courses. A pathway page is
    # not a course that states no prerequisite.
    read = (len(chosen) - kinds.get("unreachable", 0)
            - kinds.get("not a course", 0))
    typed = kinds.get("typed", 0)
    return {
        "base": base,
        **how,
        "candidate_course_paths": len(paths),
        "sampled": len(chosen),
        # PAGES ACTUALLY READ. A page that did not answer is not a page that
        # stated nothing, and counting it in the denominator would report a
        # network failure as a district's choice.
        "read": read,
        "unreachable": kinds.get("unreachable", 0),
        "sampled_but_not_a_course": kinds.get("not a course", 0),
        "kinds": kinds,
        "with_a_typed_prerequisite": typed,
        # **The headline, and its denominator is pages READ.**
        #
        # The first version divided by "courses stating a prerequisite",
        # counting any non-empty prose field as a statement — and the prose
        # field is not a prerequisite field. Measured, it carries "This course
        # is not eligible for high school credit.", "No lab class", and GMU
        # credit notes. That inflated the denominator differently per
        # district, so the comparison partly measured how chatty each
        # district's notes are.
        "percent_of_pages_with_a_typed_prerequisite": (
            round(100 * typed / read, 1) if read else None),
        # Kept, and named for what it divides by. Only comparable within
        # itself — it says whether the links a district DOES publish land.
        "links": links,
        "links_resolving_to_a_published_course": resolved,
        # None on 0/0, not 0.0. A district publishing no links has not had
        # its links fail — printed as 0.0% it reads as "none of them resolve",
        # which is the opposite of what the page argues about resolution.
        "percent_of_links_that_resolve": (
            round(100 * resolved / links, 1) if links else None),
        "with_a_nonempty_prose_field": kinds.get("prose", 0),
        # **Stated in either field.** An earlier version of this probe
        # excluded prose from any prerequisite count on the grounds that the
        # field carried general notes — and the examples that supported that
        # were artifacts of an unbounded pattern reaching into a neighbouring
        # field. With the bound in place every prose example recorded is a
        # real prerequisite, so the exclusion was wrong and the count is
        # restored beside the typed one.
        #
        # It is a count of FIELDS, not a reading of them: a page whose prose
        # field is non-empty has stated something in the place a prerequisite
        # goes. `prose_examples` is what lets a reader check that.
        "state_a_prerequisite_in_either_field":
            kinds.get("typed", 0) + kinds.get("prose", 0),
        "percent_stating_in_either_field": (
            round(100 * (kinds.get("typed", 0) + kinds.get("prose", 0)) / read, 1)
            if read else None),
        "prose_examples": examples,
    }


def measure(sample: int = SAMPLE) -> dict:
    return {
        "_": RECORD_NOTE,
        "retrieved_at": datetime.datetime.now(datetime.timezone.utc)
                                .strftime("%Y-%m-%d"),
        "seed": SEED,
        "sample_per_district": sample,
        "vendor_client_list": "https://www.cleancatalog.com/k12/",
        "districts": {name: district(name, base, sample)
                      for name, base in DISTRICTS.items()},
    }


def report(measured: dict) -> None:
    print(f"  seed {measured['seed']}, {measured['sample_per_district']} "
          f"courses per district\n")
    header = (f"  {'district':<34} {'pages':>6} {'read':>5} {'typed':>6} "
              f"{'share':>7} {'links ok':>9}")
    print(header)
    print("  " + "-" * (len(header) - 2))
    for name, found in measured["districts"].items():
        if not found.get("candidate_course_paths"):
            print(f"  {name:<34} {'—':>6}  {found.get('note','')[:40]}")
            continue
        share = found["percent_of_pages_with_a_typed_prerequisite"]
        print(f"  {name:<34} {found['candidate_course_paths']:>6} "
              f"{found['read']:>5} "
              f"{found['with_a_typed_prerequisite']:>6} "
              f"{(f'{share}%' if share is not None else '—'):>7} "
              f"{found['links_resolving_to_a_published_course']:>4}/"
              f"{found['links']:<4}")


def went_empty(measured: dict) -> set[str]:
    """Districts the committed record found pages for and this run did not.

    **A ratchet, not an emptiness check.** The first guard refused only a
    wholly empty measurement, so a run where four of five districts timed out
    — the likely real failure — overwrote the record with a smaller one and
    exited 0. The record is evidence; it may gain districts and may only lose
    one by someone deciding to.

    On a first run there is nothing committed and nothing to lose. A
    measurement with no districts at all is always refused.
    """
    found = measured.get("districts") or {}
    if not any(d.get("candidate_course_paths") for d in found.values()):
        return {"(any district at all)"}
    if not RECORD.exists():
        return set()
    committed = (json.loads(RECORD.read_text(encoding="utf-8"))
                 .get("districts") or {})
    return {name for name, was in committed.items()
            if was.get("candidate_course_paths")
            and not found.get(name, {}).get("candidate_course_paths")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m etl.probe_second_district")
    parser.add_argument("--sample", type=int, default=SAMPLE)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--record", action="store_true")
    args = parser.parse_args(argv)

    if args.json and args.record:
        # BEFORE `measure()`. Refusing afterwards meant the full five-district
        # crawl ran first — a few hundred requests to somebody else's servers
        # — and then the run was thrown away over a flag combination knowable
        # at parse time. On a politeness-bounded probe that is the expensive
        # kind of wrong.
        print("--json and --record ask for different things; pick one.",
              file=sys.stderr)
        return 2

    try:
        measured = measure(args.sample)
    except Unreachable as gone:
        print(f"unreachable: {gone}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(measured, indent=2, sort_keys=True))
        return 0
    report(measured)
    if args.record:
        lost = went_empty(measured)
        if lost:
            print(f"refusing to --record: {sorted(lost)} had course pages in "
                  f"the committed record and have none now. A run where some "
                  f"districts time out must not replace the record with a "
                  f"smaller one — the all-or-nothing guard this replaces let "
                  f"exactly that through.", file=sys.stderr)
            return 3
        write_record(RECORD, measured)
        # `relative_to` raises when RECORD has been repointed outside the
        # repo, which a test does. The path is for a human either way.
        try:
            shown = RECORD.relative_to(ROOT)
        except ValueError:
            shown = RECORD
        print(f"\n  -> {shown}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

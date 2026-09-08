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

from etl.identity import USER_AGENT
from etl.provenance import write_record

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

#: **TWO different prerequisite fields**, and the difference between them is
#: the whole question.
#:
#: `field-prerequisite-courses` is an ENTITY REFERENCE — the CMS links it to
#: other course pages, and `etl/probe_pwcs.py` reads exactly this to get PWCS's
#: 89%. `field-pr` is a free-text paragraph. A district can state its
#: prerequisites completely and usefully in the second and still publish no
#: edge anybody can traverse.
#:
#: The first version of this probe matched `field--name-field-pr\b`, whose word
#: boundary excludes `field-prerequisite-courses` — so it read the free-text
#: field on every district and reported PWCS at 0% linked. The control is the
#: only reason that was caught: the repo's own figure for PWCS is 89%, and a
#: method that cannot reproduce the known number measures nothing.
TYPED_FIELD = re.compile(
    # `\Z` as well: the lookahead required either another typed field or a
    # footer to follow, so a page whose prerequisite field is the LAST thing
    # in the document matched nothing and was counted as stating none.
    r'field--name-field-prerequisite-courses'
    r'.*?(?=field--name-field(?!-prerequisite)|</footer|\Z)', re.S)
PROSE_FIELD = re.compile(
    r'field--name-field-pr\b.*?<div class="field__item">(.*?)</div>', re.S)
HREF = re.compile(r'href="(/[^"#?]*)"')
COURSE_PATH = re.compile(r"^/[a-z0-9][a-z0-9-]*/[a-z0-9][a-z0-9-]*$")

SEED = 19            #: The issue number, so the sample is reproducible and
                     #: nobody has to wonder whether it was chosen after the
                     #: fact.
SAMPLE = 60          #: Per district. Small enough to be polite, large enough
                     #: that a 0% and an 89% are not the same measurement.
DELAY = 0.4


class Unreachable(RuntimeError):
    """A district did not answer. Distinct from answering with no courses."""


def get(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return response.read().decode("utf-8", "replace")
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
        has_sitemap = True
        time.sleep(DELAY)
        locs = re.findall(r"<loc>([^<]+)</loc>", sitemap)
        paths = {u.replace(base, "") for u in locs if u.startswith(base)}
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


def crawl(base: str) -> set[str]:
    """Course paths the catalogue's own index pages link to.

    The districts do not agree on where the index lives, so each candidate is
    tried and the results pooled. It finds far fewer than a sitemap does —
    73 against 817 on PWCS — which is why the sitemap is preferred and why
    both counts are recorded.
    """
    found: set[str] = set()
    for index in ("/courses", "/high-school-courses", "/middle-school-courses",
                  "/high-school-course-catalog", ""):
        try:
            markup = get(f"{base}{index}")
        except Unreachable:
            continue
        time.sleep(DELAY)
        found.update(path for path in HREF.findall(markup)
                     if COURSE_PATH.match(path))
    return found


def classify(markup: str, published: set[str]) -> dict:
    """What one course page says about prerequisites, and in which field.

    Typed first: a page carrying both is answering the question in the form
    that resolves, and counting it as prose would understate the district.
    """
    typed = TYPED_FIELD.search(markup)
    if typed:
        links = [href for href in HREF.findall(typed.group(0))
                 if COURSE_PATH.match(href)]
        if links:
            return {"kind": "typed", "links": links,
                    "resolved": [href for href in links if href in published]}

    prose = PROSE_FIELD.search(markup)
    if prose:
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", prose.group(1))).strip()
        if text and text.lower() not in {"none", "n/a", "na", "-"}:
            return {"kind": "prose", "text": text[:120]}
        return {"kind": "says none", "text": text}
    return {"kind": "no field"}


def district(name: str, base: str, sample: int = SAMPLE) -> dict:
    """One district, measured the same way as every other."""
    paths, how = course_paths(base)
    if not paths:
        return {"base": base, "published": 0, **how,
                "note": "the index published no two-segment course paths; the "
                        "catalogue is laid out differently and this method "
                        "does not apply to it"}

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
            time.sleep(DELAY)
            continue
        time.sleep(DELAY)
        found = classify(markup, published)
        kinds[found["kind"]] = kinds.get(found["kind"], 0) + 1
        if found["kind"] == "typed":
            links += len(found["links"])
            resolved += len(found["resolved"])
        if found["kind"] == "prose" and len(examples) < 4:
            examples.append({"path": path, "text": found["text"]})

    read = len(chosen) - kinds.get("unreachable", 0)
    typed = kinds.get("typed", 0)
    return {
        "base": base,
        **how,
        "published": len(paths),
        "sampled": len(chosen),
        # PAGES ACTUALLY READ. A page that did not answer is not a page that
        # stated nothing, and counting it in the denominator would report a
        # network failure as a district's choice.
        "read": read,
        "unreachable": kinds.get("unreachable", 0),
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
            round(100 * typed / read, 1) if read else 0.0),
        # Kept, and named for what it divides by. Only comparable within
        # itself — it says whether the links a district DOES publish land.
        "links": links,
        "links_resolving_to_a_published_course": resolved,
        "percent_of_links_that_resolve": (
            round(100 * resolved / links, 1) if links else 0.0),
        # Reported, NOT counted as prerequisites. The field is used for
        # general notes by at least three of the five.
        "with_a_nonempty_prose_field": kinds.get("prose", 0),
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
        if not found.get("published"):
            print(f"  {name:<34} {'—':>6}  {found.get('note','')[:40]}")
            continue
        print(f"  {name:<34} {found['published']:>6} "
              f"{found['read']:>5} "
              f"{found['with_a_typed_prerequisite']:>6} "
              f"{found['percent_of_pages_with_a_typed_prerequisite']:>6}% "
              f"{found['links_resolving_to_a_published_course']:>4}/"
              f"{found['links']:<4}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m etl.probe_second_district")
    parser.add_argument("--sample", type=int, default=SAMPLE)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--record", action="store_true")
    args = parser.parse_args(argv)

    try:
        measured = measure(args.sample)
    except Unreachable as gone:
        print(f"unreachable: {gone}", file=sys.stderr)
        return 2

    if args.json and args.record:
        # REFUSED rather than one silently winning. They are opposite
        # intentions — print without touching the tree, and write to the tree.
        print("--json and --record ask for different things; pick one.",
              file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(measured, indent=2, sort_keys=True))
        return 0
    report(measured)
    if args.record:
        if not any(d.get("published") for d in measured["districts"].values()):
            print("refusing to --record: no district published a course index, "
                  "so this measured nothing.", file=sys.stderr)
            return 3
        write_record(RECORD, measured)
        print(f"\n  -> {RECORD.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

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
RECORD_NOTE = ("Measured by `python -m etl.probe_second_district --record`. "
               "Same field, same sample size and the same seed on every "
               "district — the comparison measures the districts, not the "
               "method.")

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
    r'field--name-field-prerequisite-courses'
    r'.*?(?=field--name-field(?!-prerequisite)|</footer)', re.S)
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
    # **The sitemap first.** PWCS's 982 comes from its sitemap, and an index
    # crawl of the same catalogue finds 73 — the index is partial. Using the
    # index everywhere would have made every district look small in the same
    # wrong way, which is comparable and useless.
    #
    # Three of the five districts publish no sitemap at all, which is itself
    # part of the answer: the enumeration PWCS's figure rests on does not
    # generalise either.
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
        if courses:
            return courses, {"how": "sitemap", "has_sitemap": True,
                             "courses_in_sitemap": in_sitemap}
    except Unreachable:
        pass

    found: set[str] = set()
    for index in ("/courses", "/high-school-courses", "/middle-school-courses",
                  "/high-school-course-catalog", ""):
        try:
            markup = get(f"{base}{index}")
        except Unreachable:
            continue
        time.sleep(DELAY)
        found.update(p for p in HREF.findall(markup) if COURSE_PATH.match(p))
    return sorted(found), {"how": "index crawl", "has_sitemap": has_sitemap,
                           "courses_in_sitemap": in_sitemap}


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
                    "resolved": [l for l in links if l in published]}

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
            continue
        time.sleep(DELAY)
        found = classify(markup, published)
        kinds[found["kind"]] = kinds.get(found["kind"], 0) + 1
        if found["kind"] == "typed":
            links += len(found["links"])
            resolved += len(found["resolved"])
        if found.get("text") and len(examples) < 4:
            examples.append({"path": path, "kind": found["kind"],
                             "text": found["text"]})

    stating = kinds.get("typed", 0) + kinds.get("prose", 0)
    return {
        "base": base,
        **how,
        "published": len(paths),
        "sampled": len(chosen),
        "kinds": kinds,
        "state_a_prerequisite": stating,
        "state_it_in_the_typed_field": kinds.get("typed", 0),
        "links": links,
        "links_resolving_to_a_published_course": resolved,
        # The comparable figure, and it is only comparable BECAUSE the
        # denominator is the same everywhere: of the prerequisites a district
        # states, what share is a link that lands on a course it publishes.
        "percent_stated_as_resolving_link": (
            round(100 * resolved / links, 1) if links else 0.0),
        # The figure that answers #19: of the prerequisites a district states
        # at all, what share is in the field that produces an edge.
        "percent_stated_in_the_typed_field": (
            round(100 * kinds.get("typed", 0) / stating, 1) if stating else 0.0),
        "examples": examples,
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
    header = (f"  {'district':<34} {'pages':>6} {'state':>6} {'link':>5} "
              f"{'resolve':>8}")
    print(header)
    print("  " + "-" * (len(header) - 2))
    for name, found in measured["districts"].items():
        if not found.get("published"):
            print(f"  {name:<34} {'—':>6}  {found.get('note','')[:40]}")
            continue
        print(f"  {name:<34} {found['published']:>6} "
              f"{found['state_a_prerequisite']:>6} "
              f"{found['state_it_in_the_typed_field']:>5} "
              f"{found['percent_stated_as_resolving_link']:>7}%")


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

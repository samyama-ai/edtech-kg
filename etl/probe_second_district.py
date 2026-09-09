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
import hashlib
import json
import pathlib
import sys

from etl.catalogue_pages import (CALIBRATION_DISTRICT, Refused,
                                 Unreachable, course_paths, get)
from etl.course_page import classify
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


#: **The sample is not seeded any more**, and the record says so rather than
#: leaving a stale `seed` to be read as method. `sample_of` takes the paths
#: with the lowest SHA-1, which is stable when the catalogue gains or loses a
#: page — a seeded draw is not, and that cost a whole re-measurement here.
SAMPLING = "the 60 paths with the lowest sha1(path), stable across catalogue edits"
SAMPLE = 60          #: Per district. Small enough to be polite, large enough
                     #: that a 0% and an 89% are not the same measurement —
                     #: the other half of this sentence went to
                     #: `catalogue_pages.DELAY` in the 500-line split.


def sample_of(paths: list[str], size: int) -> list[str]:
    """The `size` paths with the lowest hash — NOT a seeded random sample.

    **A seeded sample is reproducible against one population, and these
    populations move.** Arlington's catalogue went from 698 candidate paths to
    697 between two runs, and `random.Random(19).sample` then redrew almost
    the whole sample: measured on a synthetic population of the same size,
    adding ONE path keeps **4 of 60** pages. Hash-ordering keeps 60 of 60.

    That mattered here. Re-running the probe after the page reader was
    rewritten showed Arlington's typed count going 3 -> 0, which reads as a
    regression in the new reader. It is not: classifying the SAME BYTES with
    both readers changes nothing on any of 961 cached PWCS pages or on 60
    Arlington pages. The whole difference was the sample being redrawn — and
    the seed made that look deliberate.

    `sampling` in the record says which method produced the figures beside
    it, so a later reader is not left inferring one.
    """
    return sorted(paths,
                  key=lambda path: hashlib.sha1(path.encode()).hexdigest()
                  )[:min(size, len(paths))]


def district(name: str, base: str, sample: int = SAMPLE,
             calibrate: bool = False) -> dict:
    """One district, measured the same way as every other."""
    paths, how = course_paths(base, calibrate=calibrate)
    if not paths:
        # THE SAME KEYS as every other district. A short entry is a KeyError
        # waiting for the first consumer that iterates the record, and it
        # reads as a missing measurement rather than a measured zero.
        return {"base": base, **how, "candidate_course_paths": 0,
                "sampled": 0, "read": 0, "unreachable": 0,
                "sampled_but_not_a_course": 0, "kinds": {},
                "unreachable_by_status": {},
                "state_a_prerequisite_in_either_field": 0,
                "percent_stating_in_either_field": None,
                "with_a_typed_prerequisite": 0,
                "percent_of_pages_with_a_typed_prerequisite": None,
                "links": 0, "links_resolving_to_a_published_course": 0,
                "percent_of_links_that_resolve": None,
                "with_a_nonempty_prose_field": 0, "prose_examples": [],
                "note": "no two-segment course path was FOUND — by this "
                        "method, from this catalogue's sitemap and five index "
                        "candidates. A district publishing courses at another "
                        "depth would produce the same entry, so this is not "
                        "found rather than does not exist. The record "
                        "outlives the page; it must not say more."}

    published = set(paths)
    chosen = sample_of(paths, sample)

    kinds: dict[str, int] = {}
    by_status: dict[str, int] = {}
    links = resolved = 0
    examples: list[dict] = []
    for path in chosen:
        try:
            markup = get(f"{base}{path}")
        except Unreachable as gone:
            kinds["unreachable"] = kinds.get("unreachable", 0) + 1
            # WHY it was unreachable. A district returning 503 for half its
            # sample was indistinguishable in the record from one whose
            # hostname did not resolve — a softer version of the denominator
            # problem the 429 fix addressed, and a 403 is a refusal rather
            # than a failure at all.
            reason = str(gone).rsplit(": ", 1)[-1]
            key = reason if reason.startswith("HTTP ") else "transport"
            by_status[key] = by_status.get(key, 0) + 1
            # No sleep here: `get` pauses BEFORE every request, including
            # the one after this failure, so the failure path is already
            # paced. The comment that used to sit here described a sleep this
            # branch stopped doing when the fetch moved into
            # `catalogue_pages`.
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
        "unreachable_by_status": by_status,
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
        "sampling": SAMPLING,
        "sample_per_district": sample,
        "vendor_client_list": "https://www.cleancatalog.com/k12/",
        # Only the calibration district crawls as well as reading its
        # sitemap — see `course_paths`.
        "districts": {name: district(name, base, sample,
                                     calibrate=name == CALIBRATION_DISTRICT)
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
    lost = {name for name, was in committed.items()
            if was.get("candidate_course_paths")
            and not found.get(name, {}).get("candidate_course_paths")}
    # AND whether anything was READ. A run where every page times out with the
    # paths intact left `read: 0` everywhere and still exited 0 — and that is
    # the case that most resembles "the district started refusing". A
    # collapse in either number is the same event.
    lost |= {name for name, was in committed.items()
             if was.get("read") and not found.get(name, {}).get("read")}
    return lost


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
    except Refused as asked:
        # Its own exit code and its own message. It escaped as a traceback
        # before — the one path where the operator most needs to read what
        # the host said.
        print(f"the host asked us to stop: {asked}", file=sys.stderr)
        return 5
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

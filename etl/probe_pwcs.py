"""Probe one district's course catalogue — do its prerequisites resolve?

This is the fork in the road for the whole build. `docs/questions.md` says it
outright: everything in section A depends on knowing which course requires
which, and *"answering that question comes before the ontology"*. If a real
district publishes prerequisites that resolve to real courses, prerequisite
chains are the demo. If not, the demo is programme → occupation → earnings.

    python -m etl.probe_pwcs                # the full sweep, 960 catalogue pages
    python -m etl.probe_pwcs --limit 50     # a quick run, and it says it is one
                                            # (dangling counts are a ceiling then)
    python -m etl.probe_pwcs --json         # machine-readable, with timestamp

Prince William County Schools publishes `catalog.pwcs.edu` on Clean Catalog, a
Drupal product. Its sitemap lists every course page, which is why the population
is known exactly rather than crawled blind.

**Pages are cached under `data/pwcs/`** (gitignored). The first run fetches; the
rest read from disk. That keeps a re-run of the figures free rather than costing
a school district ~960 requests every time somebody checks a number.

**The measurement that matters is not "does it state a prerequisite".** It is
whether the stated prerequisite *resolves* — names a course this catalogue also
publishes. That is the distinction the Credential Registry failed (#53): 150
courses in 600 stated one, and none resolved. A course code with no catalogue to
resolve it against is a string, not an edge.

No third-party dependency, as with the other probes.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from etl.identity import USER_AGENT
from etl.pwcs_pages import classify, level

SITEMAP = "https://catalog.pwcs.edu/sitemap.xml"
CACHE = Path("data/pwcs")
DELAY = 0.3          # seconds between live fetches; this is a school district
RED_FLAG = "!! "     # prefixes a count that means the parser, not the source, is wrong

# Pages under these paths are catalogue furniture, not courses.
NOT_A_COURSE = ("/high-school-course-catalog/", "/middle-school-course-catalog/",
                "/sitemap", "/search")

# The catalogue publishes prerequisites as *entity references* — links to other
# course pages — not as prose. This block is the edge, already typed by the
# publisher. Reading it out of flattened page text instead would run it into the
# footer and turn the school's street address into a course name.
# `\Z` matters: without an end-of-string alternative the block is only found
# when a terminator follows it, so a page whose markup ends differently reports
# zero prerequisites instead of failing. A silent zero is the worst outcome here
# — it reads as "this district publishes none".
PREREQ_BLOCK = re.compile(
    r'field--name-field-prerequisite-courses'
    r'.*?(?=<div class="field field--|</article>|<footer|\Z)', re.S)
HREF = re.compile(r'<a href="([^"]+)"[^>]*>(.*?)</a>', re.S)

# A separate free-text field, labelled "Requirements" in the page — things like
# "Enrolled in Agriculture Specialty Program". Not a course reference, and
# counting it as one would overstate what can be loaded as an edge.
# Bounded the same way PREREQ_BLOCK is. Unbounded, a page carrying the wrapper
# but rendering its value differently would match the *next* field__item
# anywhere later in the document and attribute unrelated text to this course.
REQUIREMENTS = re.compile(
    r'field--name-field-recommended'
    r'(?:(?!<div class="field field--).)*?'
    r'field__item"><p>(.*?)</p>', re.S)

# A page that renders the prerequisite field but yields no links is a parse
# failure, not a course without prerequisites — the field would not be rendered
# at all if there were none. Counting it as "no prerequisite" would lower the
# rate with no trace, which is the class of error this probe exists to correct.
PREREQ_FIELD_PRESENT = re.compile(r'field--name-field-prerequisite-courses')

# A named field's contents — edtech-kg#137.
#
# Anchored PAST the opening tag, or the capture starts inside the class
# attribute and the extracted text begins
# `field--type-text-long field--label-hidden field__item">`.
#
# Stopped at the next SIBLING FIELD WRAPPER, not at the next
# `field--name-field-`. The looser stop ran past the end of the description
# into the markup of whatever came next, and `text_of` does not strip a tag it
# was handed mid-attribute — so 87 of 791 descriptions arrived carrying
# `<div class="field...` as text. The engine caught it rather than the parser:
# `lit()` refuses a string holding both quote characters, and those were the
# only descriptions that held a double quote at all.
FIELD = (r'field--name-field-{}\b[^>]*>'
         r'(.*?)(?=<div class="field\b|<span class="field\b|</article>|$)')
FIELD_ITEM = re.compile(r'field__item[^>]*>(.*?)</div>', re.S)


def field_text(markup: str, name: str) -> str | None:
    """One field's text, unescaped and whitespace-collapsed."""
    found = re.search(FIELD.format(name), markup, re.S)
    if not found:
        return None
    return " ".join(text_of(found.group(1)).split()) or None


def field_items(markup: str, name: str) -> list[str]:
    """A field published as a LIST of items — `Grades` renders one div each.

    Trailing commas stripped: the catalogue writes them as `9,` `10,` `12`, so
    the separator is inside the value on every item but the last.
    """
    found = re.search(FIELD.format(name), markup, re.S)
    if not found:
        return []
    return [item for item in
            (" ".join(text_of(raw).split()).strip(", ")
             for raw in FIELD_ITEM.findall(found.group(1)))
            if item]


class MalformedSource(Exception):
    """Reachable, but not the page we asked for."""


def text_of(markup: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", markup))


def cached_path(url: str):
    """Where this page is cached.

    Its own function so a caller can ask "is the cache complete" without
    re-deriving the key. Two derivations of one path is the same defect class
    as two normalisations of one URL: they agree until one changes.
    """
    return CACHE / (urllib.parse.quote(url, safe="") + ".html")


def fetch(url: str, use_cache: bool = True) -> str:
    key = cached_path(url)
    if use_cache and key.exists():
        return key.read_text(encoding="utf-8", errors="replace")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            body = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{exc.code} from {url}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"unreachable: {url} ({exc})") from exc
    if use_cache:
        key.parent.mkdir(parents=True, exist_ok=True)
        # Written to a sibling and renamed. A direct write interrupted midway
        # leaves a truncated page that every later run reads from cache as
        # though it were the real one — a silent wrong answer with no retry.
        # Encoding is stated on the write because the read states it.
        partial = key.with_suffix(".partial")
        partial.write_text(body, encoding="utf-8")
        partial.replace(key)
    time.sleep(DELAY)
    return body


def catalogue_urls(use_cache: bool = True) -> list[str]:
    """Every catalogue page in the sitemap, furniture removed.

    Named for what it returns. It was `course_urls`, and it never returned
    only courses — 127 of the 960 are subject indexes and 42 are CTE pathways.
    The probe took the name at its word and quoted every rate against 960,
    which is edtech-kg#74. A name that has to be remembered as untrue is the
    same defect as a wrong number, one step earlier.
    """
    sitemap = fetch(SITEMAP, use_cache)
    if "<loc>" not in sitemap:
        raise MalformedSource(
            f"{SITEMAP} returned no <loc> entries — got {sitemap[:60]!r}. "
            f"An error page here would otherwise report zero courses."
        )
    urls = re.findall(r"<loc>([^<]+)</loc>", sitemap)
    courses = [u for u in urls if not any(p in u for p in NOT_A_COURSE)]
    if not courses:
        raise ValueError("the sitemap lists no course pages — refusing to report that")
    return sorted(set(courses))


def parse_course(markup: str, url: str) -> dict | None:
    """Title, linked prerequisites and free-text requirements.

    Returns None if this is not a course page, so catalogue furniture and 404s
    are skipped rather than counted as courses with no prerequisite.
    """
    heading = re.search(r"<h1[^>]*>(.*?)</h1>", markup, re.S)
    if not heading:
        return None
    title = " ".join(text_of(heading.group(1)).split())
    if not title or title.lower().startswith("page not found"):
        return None

    block = PREREQ_BLOCK.search(markup)
    links = HREF.findall(block.group()) if block else []
    requirement = REQUIREMENTS.search(markup)
    return {
        "url": url,
        "title": title,
        "prerequisite_links": [
            {"href": href, "name": " ".join(text_of(name).split())}
            for href, name in links
        ],
        # Field rendered, nothing extracted — reported, never read as absence.
        "field_present_no_links": bool(PREREQ_FIELD_PRESENT.search(markup)) and not links,
        "requirements_text": (" ".join(text_of(requirement.group(1)).split())
                              if requirement else None),
        # edtech-kg#137. The catalogue publishes both and no loader read them,
        # so `Q9` and `Q14` reached for properties that were never written and
        # returned null on a loaded district. `None` and `[]` for absent, which
        # is a real state here: measured, every course page carries a
        # description and only 478 of them carry grades.
        "description": field_text(markup, "description"),
        "grade_levels": field_items(markup, "grades"),
    }


CATALOGUE_HOST = urllib.parse.urlparse(SITEMAP).netloc


def path_of(url: str) -> str | None:
    """The catalogue-relative path, or None for an off-site link.

    Hrefs in the prerequisite field are relative in practice, but an absolute
    off-site URL whose path happened to exist in the catalogue would otherwise
    resolve — and the claim being made here is 100%, which should be airtight.
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.netloc and parsed.netloc != CATALOGUE_HOST:
        return None
    return parsed.path.rstrip("/")


def resolve(records: list[dict], catalogue: list[str] | None = None) -> dict:
    """Do the linked prerequisites point at courses this catalogue publishes?

    Resolution is by **URL against the sitemap**, not by name matching. Both
    ends of the edge come from the same publisher, so a link either lands on a
    published course page or provably does not. That is the property the
    Credential Registry lacks (#53), where "PSYC101" is a string with no
    catalogue to resolve it against.

    `catalogue` is every course URL in the sitemap, so a partial run still
    resolves against the whole catalogue rather than the pages it happened to
    read — which would report almost everything as broken and look like a
    finding.
    """
    # Strictly the sitemap, so the invariant matches what the docstring and the
    # document both claim. Unioning the read records in made resolution partly
    # self-referential, and it is what let a slash-sensitivity bug hide.
    published = {path_of(u) for u in (catalogue or [])} - {None}
    stating = fully = partly = broken = with_requirements = unparsed_field = 0
    edges: list[tuple[str, str]] = []
    dangling: list[str] = []

    for record in records:
        if record.get("requirements_text"):
            with_requirements += 1
        if record.get("field_present_no_links"):
            unparsed_field += 1
        links = record.get("prerequisite_links") or []
        if not links:
            continue
        stating += 1
        hit = [l for l in links if path_of(l["href"]) in published]
        miss = [l for l in links if path_of(l["href"]) not in published]
        if not miss:
            fully += 1
        elif hit:
            partly += 1
        else:
            broken += 1
        dangling += [l["href"] for l in miss]
        edges += [(record["title"], l["name"]) for l in hit]

    return {
        "courses": len(records),
        "stating_a_prerequisite": stating,
        "every_link_resolves": fully,
        "some_links_resolve": partly,
        "no_link_resolves": broken,
        "resolvable_edges": len(edges),
        "dangling_links": len(dangling),
        "with_free_text_requirements": with_requirements,
        "prerequisite_field_unparsed": unparsed_field,
        "dangling_examples": sorted(set(dangling))[:8],
        "edge_examples": edges[:8],
    }


def probe(limit: int | None = None, use_cache: bool = True, quiet: bool = False) -> dict:
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    urls = catalogue_urls(use_cache)
    population = len(urls)
    read = urls[:limit] if limit else urls

    # Classified as they are read. A page's kind decides whether it belongs in
    # the denominator, so it has to be decided from the page — `classify` reads
    # the markup, and the four pages whose markup contradicts their depth are
    # the reason depth alone is not enough (#87).
    kinds: Counter[str] = Counter()
    # Every page we managed to classify, and separately every page the
    # classifier called a course. The second is not the same as
    # the parsed set: a page can be a course and still fail to parse, and it
    # is published either way.
    classified_any: set[str] = set()
    classified_course: list[str] = []
    records, skipped, unread = [], 0, []
    for url in read:
        # One slow page must not lose the whole sweep. Retried once, then
        # recorded as unread — reported, never silently dropped, because a page
        # we could not read is not a course without a prerequisite.
        try:
            markup = fetch(url, use_cache)
        except RuntimeError:
            time.sleep(DELAY)          # do not hit a struggling server twice at once
            try:
                markup = fetch(url, use_cache)
            except RuntimeError as exc:
                unread.append({"url": url, "why": str(exc)})
                continue
        kind = classify(url, markup) or "unclassified"
        kinds[kind] += 1
        classified_any.add(url)
        if kind == "course":
            classified_course.append(url)
        parsed = parse_course(markup, url)
        # A subject index and a pathway page both parse as courses — they have
        # a title and no prerequisite field — so `parse_course` returning a
        # record is not evidence that the page is one. Only the classifier's
        # answer puts a page in the denominator.
        if kind != "course":
            continue
        if parsed:
            records.append(parsed)
        else:
            skipped += 1
    if not records:
        raise ValueError("no course pages parsed — refusing to report a rate over zero")

    # Resolved against COURSE paths, not against every published page. A
    # prerequisite pointing at a subject index would have counted as resolved
    # and then written no edge, and the count and the graph would have
    # disagreed with nothing to say why.
    #
    # But "we could not open it" is not "it is not published". Three ways a
    # course page can be missing from the parsed set while still existing:
    # never attempted (`--limit`), attempted and unreadable, or read and
    # unparsed. All three belong in the eligible set.
    #
    # **Depth is the FALLBACK, not the rule.** Using it for every page absent
    # from the parsed set re-admitted the four pages whose markup says pathway
    # at course depth — undoing #87 in the one place that fix is about. So a
    # page the classifier reached is trusted: its kind decides. Depth is used
    # only for pages we never classified at all, where markup is exactly what
    # is missing.
    #
    # On a full, clean run `never_classified` is empty and the eligible set is
    # the classified courses, unchanged.
    never_classified = [u for u in urls
                        if u not in classified_any and level(u) == "course"]
    catalogue = classified_course + never_classified
    result = resolve(records, catalogue=catalogue)
    coverage = ("every catalogue page in the sitemap" if not limit
                else f"the first {len(read)} of {population} sitemap pages — "
                     f"a partial run, not the catalogue")
    # Said whenever the eligible set had to be widened, not only under
    # `--limit`. A full run can still leave pages unclassified — a fetch that
    # failed twice, or a page that parsed to nothing — and the caveat belongs
    # wherever that happened, not wherever we chose to stop early.
    if never_classified:
        coverage += (f". Prerequisite resolution is measured against the "
                     f"{len(classified_course)} classified courses plus "
                     f"{len(never_classified)} pages at course depth that "
                     f"were never opened, so dangling counts are a ceiling "
                     f"rather than a finding")
    result |= {"population": population, "pages_read": len(read),
               "subjects": kinds["subject"], "pathways": kinds["pathway"],
               "unclassified": kinds["unclassified"],
               # A course the classifier accepted and the parser could not
               # read — a missing `<h1>`. It was called `not_a_course_page`,
               # which is what it counted before the classifier decided that
               # question, and the opposite of what it counts now.
               "courses_that_did_not_parse": skipped,
               "unread": len(unread), "unread_examples": unread[:5], "coverage": coverage,
               # The number reported must BE the set resolution ran
               # against, so it is derived from `catalogue` and not rebuilt
               # from a wider or narrower list. Reporting 960 while resolution
               # used 791 made the 100% look checked against more than it was.
               "published_paths": len({path_of(u) for u in catalogue}
                                      - {None})}

    if not quiet:
        print("\nPWCS course catalogue — catalog.pwcs.edu\n")
        print(f"  coverage               {coverage}")
        print(f"  sitemap pages          {result['population']:>6,}")
        # AGAINST PAGES ATTEMPTED, not against the sitemap. `population` is
        # every page the sitemap lists; the breakdown below counts only pages
        # this run reached for, so under `--limit` the lines summed to the
        # limit and sat under a heading claiming they accounted for all 960.
        # Every attempt lands in exactly one line below — a page that could
        # not be read is one of them, so the group closes on the heading.
        print(f"  of the {result['pages_read']:,} attempted:")
        print(f"    subject indexes      {result['subjects']:>6,}")
        print(f"    COURSES              {len(classified_course):>6,}")
        print(f"      of those, parsed   {result['courses']:>6,}"
              f"   <- every rate below is quoted against this")
        if skipped:
            print(f"      unreadable         {skipped:>6,}"
                  f"   — classified a course, no title to parse")
        print(f"    CTE pathways         {result['pathways']:>6,}")
        if result["unclassified"]:
            print(f"    unclassified         {result['unclassified']:>6,}"
                  f"   — neither depth nor markup named these")
        if result["unread"]:
            print(f"    could not be read    {result['unread']:>6,}"
                  f"   — excluded, not counted as having no prerequisite")
        print(f"  linking a prerequisite {result['stating_a_prerequisite']:>6,}"
              f"   ({pct(result['stating_a_prerequisite'], result['courses'])})")
        print(f"    every link resolves  {result['every_link_resolves']:>6,}"
              f"   ({pct(result['every_link_resolves'], result['stating_a_prerequisite'])} of those)")
        print(f"    some links resolve   {result['some_links_resolve']:>6,}")
        print(f"    no link resolves     {result['no_link_resolves']:>6,}")
        print(f"  resolvable edges       {result['resolvable_edges']:>6,}")
        print(f"  resolved against       {result['published_paths']:>6,}"
              f"   published COURSE paths — subject indexes and pathway")
        print("                                  pages are excluded, as they are from the count above")
        print(f"  dangling links         {result['dangling_links']:>6,}")
        print(f"  free-text requirements alongside: "
              f"{result['with_free_text_requirements']:,} courses")
        if result["prerequisite_field_unparsed"]:
            print(f"  {RED_FLAG}prerequisite field rendered but no links read: "
                  f"{result['prerequisite_field_unparsed']:,} — markup drift, "
                  f"not courses without prerequisites")
        print(f"\n  measured {stamp}")
        print("  reproduce with: python -m etl.probe_pwcs\n")

    return {"retrieved_at": stamp, "source": SITEMAP, **result}


def pct(part: int, whole: int) -> str:
    """One decimal place.

    It rounded to whole percent, and the two candidate denominators for the
    prerequisite rate — 960 pages against 791 courses — print as 24% and 29%.
    The documents quote this figure, so the digit that distinguishes 29.0 from
    28.8 is the digit that says which denominator was used.
    """
    return f"{100 * part / whole:.1f}%" if whole else "—"


def main(argv: list[str] | None = None) -> int:
    summary = (__doc__ or "").splitlines()
    parser = argparse.ArgumentParser(description=summary[0] if summary else None)
    parser.add_argument("--limit", type=int, default=None,
                        help="Read only the first N pages. The output says it was partial.")
    parser.add_argument("--no-cache", action="store_true",
                        help="Fetch live even when a cached copy exists.")
    parser.add_argument("--json", action="store_true", help="Print the result as JSON.")
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 1:
        print("\nrefused: --limit must be at least 1", file=sys.stderr)
        return 1
    try:
        result = probe(limit=args.limit, use_cache=not args.no_cache, quiet=args.json)
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

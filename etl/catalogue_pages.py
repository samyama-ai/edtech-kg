"""Finding a catalogue's course pages — the sitemap, then its paginated index.

Split from `etl/probe_second_district.py` when it passed the 500-line review
limit. Split by SUBJECT: that module SAMPLES pages and classifies them; this
one decides which pages exist. The hazards differ — enumeration risks
visiting the wrong pages or missing most of them, and both have happened
here. Reading only the first index page found 73 of PWCS's 817 courses, and
the sample was then drawn from that biased subset.

`etl/course_page.py` is the third piece: reading ONE page.
"""

from __future__ import annotations

import re
import time
import urllib.error
import urllib.request

from etl.course_page import COURSE_PATH, same_host
from etl.course_reader import hrefs
from etl.identity import USER_AGENT

#: Seconds between requests to one host. The politeness budget, and the reason
#: the sample is 60 pages per district rather than all of them.
#:
#: This line arrived as an orphan comment fragment — "that a 0% and an 89% are
#: not the same measurement" — whose other half stayed behind in
#: `probe_second_district.SAMPLE` when the 500-line split cut between them. A
#: comment split across two modules explains nothing in either.
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

#: The one district where BOTH enumeration methods work, so the crawl can be
#: checked against a census. The page's calibration rests on it, and no other
#: district needs the comparison.
CALIBRATION_DISTRICT = "PWCS (Prince William County, VA)"


def course_paths(base: str, calibrate: bool = False) -> tuple[list[str], dict]:
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

    # **The index crawl runs alongside a working sitemap only where the page
    # quotes the comparison.** It is the calibration that lets the other four
    # districts' crawl figures be read as counts, and it needs one district
    # where both methods work — PWCS. Running it everywhere cost up to ~200
    # extra requests per district for a number nothing uses, which on a
    # politeness-bounded probe reading school-district servers is the
    # expensive kind of thoroughness.
    crawled = crawl(base) if (calibrate or not in_sitemap) else set()
    if in_sitemap:
        # `has_sitemap` from the PARSED check, not hard-coded. This branch
        # asserted True while the variable beside it was computed, so the two
        # could disagree and the record would carry the assertion.
        return sorted(courses), {"how": "sitemap", "has_sitemap": has_sitemap,
                                 "courses_in_sitemap": in_sitemap,
                                 # None, not 0 — "not measured here" and
                                 # "the crawl found nothing" are different
                                 # facts and only one of them is a finding.
                                 "courses_in_index_crawl": (
                                     len(crawled) if calibrate else None)}

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
                    (same_host(href, base) for href in hrefs(markup))
                    if path}
            if not here - seen_here:
                # This index has stopped yielding paths IT has not already
                # yielded: the pager has run out, or the page does not
                # paginate. Both mean move to the next candidate.
                break
            seen_here |= here
        found |= seen_here
    return found

"""What ONE course page says about prerequisites, and in which field.

Split from `etl/probe_second_district.py` when it passed the 500-line review
limit. Split by SUBJECT: that module walks catalogues and samples them; this
reads a single page. The hazards are different — walking risks visiting the
wrong pages, reading risks measuring the wrong field, and this file is about
the second.

**This file used to scan HTML with regular expressions, and it took four
review rounds to stop.** Each round fixed one bound and the next round found
the same failure through a different door: a `class` attribute the scanner
could not locate, a comment whose `-->` became prose, an attribute value
holding `<div>`, an unclosed quote pairing with the next tag's quote. Those
are not four bugs. They are one: **the code was deciding what was markup and
what was text, and that is a parser's job.**

So the scan is `html.parser.HTMLParser` — standard library, no dependency.
Comments, script bodies and attribute values arrive as their own events and
can no longer be mistaken for anything else. `masked()`, `NOT_MARKUP`,
`_in_class_attribute`, `field_ends_at`, `field_openings` and the offset-
sharing dance between them are gone.

It is not a shorter file — 353 lines became 380. The parser needs things the
regex version never knew it needed: which elements HTML does not close, which
elements' contents are not text, and what to do with a region whose closing
tag never arrives. That last one is the point. The regex version answered the
malformed case by guessing, and the guess was a neighbouring field's link
reported as a prerequisite that resolves.

The two hazards this file exists for have both been realised. The first
version matched the free-text field on every district and reported PWCS at 0%
linked; the second let an unbounded pattern reach forward into a neighbouring
field and record its text as a prerequisite. Every bound below is there
because one of those happened.

No network.
"""

from __future__ import annotations

import html
import re

from etl.course_page_fields import FIELD_OPENS       # noqa: F401  (re-exported)
from etl.course_reader import Field, read_fields, plain, hrefs   # noqa: F401

#: A CANDIDATE course path — two segments. **Candidate, not course**: the
#: repo's own classifier decides, by markup rather than depth. PWCS publishes
#: 960 pages of which `docs/schema.md` counts 791 courses, 127 subject indexes
#: and 42 pathways, and quotes every rate against the 791. Two segments
#: selects more than that, so each sampled page is classified after it is
#: fetched and a pathway leaves the denominator.
COURSE_PATH = re.compile(r"^/[a-z0-9][a-z0-9-]*/[a-z0-9][a-z0-9-]*$")


def same_host(href: str, base: str) -> str | None:
    """`href` as a path on `base`, or None if it points somewhere else.

    Absolute and root-relative both resolve; anything off-host is not a course
    in this catalogue and is not a resolution failure either.
    """
    # **The query string and fragment come off HERE**, not in the pattern
    # that finds the href. The regex version captured `[^"#?]+` between the
    # quotes, which matched NOTHING for `href="/maths/algebra-1?from=x"` — so
    # a prerequisite carrying a query string was invisible, and `links` is the
    # denominator of the "every link resolves" claim. The parser hands over
    # the href as written; normalising it is this function's job, and it is
    # the only place that knows what a course path looks like.
    href = href.split("#", 1)[0].split("?", 1)[0]
    if href.startswith(base):
        href = href[len(base):] or "/"
    if not href.startswith("/"):
        return None
    return href if COURSE_PATH.match(href) else None


def classify(markup: str, published: set[str], base: str = "") -> dict:
    """What one course page says about prerequisites, and in which field.

    Typed first: a page carrying both is answering the question in the form
    that resolves, and counting it as prose would understate the district.

    **An unbounded field is refused, not read.** One unclosed `<div>` used to
    carry the region into its neighbour and return the NEXT field's link as a
    prerequisite that resolves — manufacturing the exact finding this probe
    publishes. `"unbounded field"` is a fifth answer, and a district emitting
    them says so in the record rather than inflating a rate.
    """
    fields = read_fields(markup)

    typed = fields.get("prerequisite-courses")
    if typed is not None:
        if not typed.bounded:
            return {"kind": "unbounded field", "field": "prerequisite-courses"}
        # DEDUPLICATED. One course linked twice in the same field counted
        # twice in both the links and the resolved numerators, inflating a
        # rate whose whole claim is that the links land.
        links = sorted({path for path in
                        (same_host(href, base) for href in typed.links)
                        if path})
        if links:
            return {"kind": "typed", "links": links,
                    "resolved": [href for href in links if href in published]}
        # **A typed field holding no course link is its own answer.** It fell
        # through to the prose branch, so a district that emits the field and
        # fills it with navigation or off-host links was reported as not using
        # it at all. That is a different fact from "no field" and from
        # "prose", and only this branch can tell them apart.
        # **No `if text:` guard.** With one, a typed field holding only
        # `&nbsp;` — or nothing — fell through to the prose branch and out as
        # `no field`, so "the district emits this field and left it empty"
        # and "the district does not use this field" were the same answer.
        # They are different facts about a district, which is the argument
        # this branch's own name makes.
        return {"kind": "typed but no course link",
                "text": typed.readable()[:120]}

    prose = fields.get("pr")
    if prose is not None:
        if not prose.bounded:
            return {"kind": "unbounded field", "field": "pr"}
        text = prose.readable()
        if states_a_prerequisite(text):
            return {"kind": "prose", "text": text[:120]}
        return {"kind": "says none", "text": text}
    return {"kind": "no field"}


#: A field whose whole content is a denial. Anchored at both ends, so
#: "None; after successful completion of 23132" — which names courses — is
#: NOT caught, and a bare "None." is.
SAYS_NONE = re.compile(
    r"^(prerequisites?\s*[:\-]?\s*)?(none|n/?a|nil|not applicable|-|–|—)"
    r"\s*[.;:]?$", re.I)

#: An explicit denial written as a sentence. "NO PRIOR FILM EXPERIENCE
#: REQUIRED." is not a prerequisite, and counting it as one is the same
#: mistake as counting "None" — one clause longer.
DENIES_ONE = re.compile(
    r"\bno\s+(prior|previous|prerequisite)\b[^.]*\b(required|necessary|needed)\b",
    re.I)


def states_a_prerequisite(text: str) -> bool:
    """Does this prose field state a prerequisite, or deny one?

    **The sentinel was exact-match on four strings**, so a trailing full stop
    flipped the answer: `None.` counted as a stated prerequisite. That is in
    the committed record — three of eight sampled Arlington examples were
    non-statements, and one was an explicit denial — and it is the district
    the headline comparison depends on.

    `docs/sources/course-prerequisites.md` records this same mistake as a past
    correction: *"counted 'Prerequisite: None' as a stated prerequisite"*. The
    repo learned it once; this is the second time.

    Entities are decoded and trailing punctuation stripped before the
    comparison, because `&nbsp;` survived `plain()` as six literal characters
    and could never look empty.
    """
    text = html.unescape(text or "").replace("\xa0", " ").strip()
    if not text:
        return False
    if SAYS_NONE.match(text):
        return False
    return not DENIES_ONE.search(text)

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
from html.parser import HTMLParser

#: **TWO different prerequisite fields**, and the difference between them is
#: the whole question.
#:
#: `field-prerequisite-courses` is an ENTITY REFERENCE — the CMS links it to
#: other course pages, and `etl/probe_pwcs.py` reads exactly this. `field-pr`
#: is a free-text paragraph. A district can state its prerequisites completely
#: and usefully in the second and still publish no edge anybody can traverse.
#:
#: The first version matched `field--name-field-pr\b`, whose word boundary
#: excludes `field-prerequisite-courses` — so it read the free-text field on
#: every district and reported PWCS at 0% linked. The control is the only
#: reason that was caught.
FIELD_OPENS = "field--name-field-"


#: How deep a field's own markup can plausibly nest before the count is wrong
#: rather than deep. A Drupal entity-reference teaser nests a handful of divs;
#: thirty is generous and still finite, which is what matters.
MAX_NESTING = 30

#: Elements that close the page region a field lives in. A field that reached
#: past one of these was never bounded at all.
REGION_ENDS = {"article", "main", "footer", "body"}

#: Elements HTML never closes, so they must not move the depth count. The
#: regex version counted only `<div>`; a parser sees every element, which is
#: more correct and means this list has to exist.
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr"}

#: Elements whose CONTENT is not page text. `HTMLParser` still reports their
#: character data, so a `<script>` holding `field--name-field-pr` would read
#: as prose without this.
NOT_TEXT = {"script", "style", "template", "noscript"}

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


class Hrefs(HTMLParser):
    """Every `href` on a page, in document order.

    An index page is not a field, so it does not need `FieldReader` — but it
    does need the same parser rather than the `HREF` regex that used to serve
    both. That regex read `href="([^"#?]*)[^"]*"`: double quotes only, and a
    capture that matched NOTHING when a query string was present. An index
    whose pager links carry `?page=` yielded no paths at all, which reads as
    "this catalogue has no courses".
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.found: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        for name, value in attrs:
            if name.lower() == "href" and value:
                self.found.append(value)


def hrefs(markup: str) -> list[str]:
    reader = Hrefs()
    reader.feed(markup)
    reader.close()
    return reader.found


class Field:
    """One field's collected text and links, and whether it was BOUNDED.

    `bounded` is the part that matters. A field whose own closing tag never
    arrives — one unclosed `<div>` does it, and district CMS output has them —
    used to run on into its neighbour and return the NEXT field's link as a
    prerequisite that resolves. That is the exact shape of the finding this
    probe publishes, manufactured by the reader.

    So an unbounded region is not guessed at. It is reported as unbounded and
    `classify` refuses to read it, which is this repo's usual answer to a
    measurement it cannot stand behind.
    """

    def __init__(self, name: str, depth: int):
        self.name = name
        self.depth = depth
        self.text: list[str] = []
        self.links: list[str] = []
        self.bounded = False

    def readable(self) -> str:
        return re.sub(r"\s+", " ", "".join(self.text)).strip()


class FieldReader(HTMLParser):
    """Every `field--name-field-X` region on the page, in one pass.

    **One pass, not two scans sharing offsets.** The regex version scanned the
    masked markup for structure and the original for field names, because
    masking hid the class attribute it needed to read — then compared
    positions between the two. Attributes are just data here, so there is
    nothing to mask and nothing to line up.
    """

    def __init__(self):
        # `convert_charrefs=True` is the default and is wanted: `&nbsp;`
        # arrives as a character rather than as six of them, which is what
        # `states_a_prerequisite` had to undo by hand.
        super().__init__(convert_charrefs=True)
        self.fields: dict[str, Field] = {}
        self.open: Field | None = None
        self.depth = 0
        self.silent = 0          # inside a script/style/template
        self.stopped = False     # past </article>, </main> or <footer>

    # -- structure ---------------------------------------------------------

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if self.stopped:
            return
        if tag == "footer":
            self._close_open(bounded=False)
            self.stopped = True
            return
        if tag in NOT_TEXT:
            self.silent += 1
        if tag in VOID:
            return

        field = self._field_name(attrs)
        if field is not None:
            # A field opening at or above the open field's own depth is a
            # SIBLING and ends it. Deeper is a sub-field — routine in an
            # entity-reference teaser, where each referenced node brings its
            # own fields — and must not, or a two-course prerequisite list
            # returns one link.
            if self.open is not None and self.depth <= self.open.depth:
                self._close_open(bounded=True)
            if self.open is None and field not in self.fields:
                self.open = Field(field, self.depth)
                self.fields[field] = self.open
        self.depth += 1

        if self.open is not None and self.depth - self.open.depth > MAX_NESTING:
            # Runaway rather than deep. The depth is a count over markup that
            # may not close what it opens; this is the ceiling that keeps a
            # wrong count finite.
            self._close_open(bounded=False)

    def handle_startendtag(self, tag, attrs):
        if not self.stopped and tag.lower() not in VOID:
            self.handle_starttag(tag, attrs)
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if self.stopped:
            return
        if tag in NOT_TEXT:
            # `silent` comes off, but the DEPTH still does — `<script>`
            # incremented it on the way in, and returning here left the count
            # one too high for the rest of the page. A field open at the time
            # then never closed and was reported unbounded. Symmetry between
            # the two handlers is the whole of the depth model's correctness.
            self.silent = max(0, self.silent - 1)
        if tag in VOID:
            return
        if tag in REGION_ENDS:
            self._close_open(bounded=False)
            self.stopped = True
            return
        self.depth = max(0, self.depth - 1)
        if self.open is not None and self.depth <= self.open.depth:
            self._close_open(bounded=True)

    def _close_open(self, bounded: bool):
        if self.open is not None:
            self.open.bounded = bounded
            self.open = None

    def close(self):
        # Anything still open at the end of the document never closed.
        self._close_open(bounded=False)
        super().close()

    # -- content -----------------------------------------------------------

    def handle_data(self, data):
        if self.open is not None and not self.silent:
            self.open.text.append(data)

    # `handle_comment` is NOT overridden, and that is the point: a comment is
    # its own event, so `<!-- <div> -->` can no longer leave a stray `-->` in
    # the text or move the depth count. Three of the four round-4 blockers
    # were this one fact, arriving separately.

    @staticmethod
    def _field_name(attrs) -> str | None:
        for name, value in attrs:
            if name.lower() != "class" or not value:
                continue
            for token in value.split():
                if token.startswith(FIELD_OPENS):
                    return token[len(FIELD_OPENS):]
        return None

    def link_of(self, tag, attrs):
        for name, value in attrs:
            if name.lower() == "href":
                return value
        return None


class LinkReader(FieldReader):
    """`FieldReader`, also collecting `href` values inside a field.

    Separate only so `handle_starttag` stays readable; the parse is still one
    pass. The href arrives already decoded and already unquoted — `href='…'`,
    `HREF=` and `Href=` are the same event, which the regex version treated as
    three different ones and got two of them wrong.
    """

    def handle_starttag(self, tag, attrs):
        super().handle_starttag(tag, attrs)
        if self.open is not None and not self.silent and tag.lower() == "a":
            href = self.link_of(tag, attrs)
            if href:
                self.open.links.append(href)


def read_fields(markup: str) -> dict[str, Field]:
    """Every field on the page. Malformed markup yields fields, not an error.

    `HTMLParser` raises nothing on broken markup by default, which is what is
    wanted: a district's CMS output is not a conformance test, and a page that
    cannot be parsed still has to be classified as something.
    """
    reader = LinkReader()
    reader.feed(markup)
    reader.close()
    return reader.fields


def plain(markup: str) -> str:
    """Markup as readable text, via the parser.

    The regex version stripped comments and tags on the raw string, so
    `<div title="-->">Real text</div>` returned `'">Real text'` — and a prose
    field whose whole content was `None.` behind a `data-tip="-->"` came back
    as `'">None.'`, whose `">` prefix defeated `SAYS_NONE`'s `^` anchor and
    turned a denial into a stated prerequisite.
    """
    reader = FieldReader()
    reader.open = Field("", -1)          # capture everything
    reader.feed(markup)
    return reader.open.readable()


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
        text = typed.readable()
        if text:
            return {"kind": "typed but no course link", "text": text[:120]}

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

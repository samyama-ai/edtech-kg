"""What ONE course page says about prerequisites, and in which field.

Split from `etl/probe_second_district.py` when it passed the 500-line review
limit. Split by SUBJECT: that module walks catalogues and samples them; this
reads a single page. The hazards are different — walking risks visiting the
wrong pages, reading risks measuring the wrong field, and this file is about
the second.

Both hazards have been realised here. The first version matched the free-text
field on every district and reported PWCS at 0% linked; the second let an
unbounded pattern reach forward into a neighbouring field and record its text
as a prerequisite. Every bound in this file is there because one of those
happened.

No network.
"""

from __future__ import annotations

import html
import re

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


#: Where a field's own markup ENDS. Both patterns previously ran `.*?` under
#: `re.S` to the next field or the end of the document, which is two bugs:
#:
#:   * a `field-pr` wrapper with no `field__item` of its own reached forward
#:     to the first one ANYWHERE later, so text from a different field was
#:     recorded as prose — and three such examples were the entire evidence
#:     for this page's central claim about what `field-pr` contains;
#:   * a typed field that is the LAST field on the page ran to `\Z`, so
#:     trailing navigation counted as prerequisite links. Navigation links to
#:     published courses always resolve, which is precisely the claim being
#:     made.
#:
#: So a field stops at the next field, or at the end of the article, whichever
#: comes first — never at the end of the document.

#: How deep a field's own markup can plausibly nest before the count is
#: wrong rather than deep. A Drupal entity-reference teaser nests a handful of
#: divs; thirty is generous and still finite, which is what matters — an
#: unclosed tag makes the depth monotonic and only a ceiling stops it.
MAX_NESTING = 30

#: Every token `field_ends_at` has to see to keep its depth count honest.
DIV_OR_BOUNDARY = re.compile(r"<div\b|</div>|</article|</main|<footer", re.I)


#: district linking its prerequisites as `https://catalog.example.edu/x/y`
#: was silently counted as having none — the finding this probe exists to
#: measure, produced by not looking. `same_host` strips the prefix.
HREF = re.compile(r'href="([^"#?]+)"')


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
    if href.startswith(base):
        href = href[len(base):] or "/"
    if not href.startswith("/"):
        return None
    return href if COURSE_PATH.match(href) else None


def classify(markup: str, published: set[str], base: str = "") -> dict:
    """What one course page says about prerequisites, and in which field.

    Typed first: a page carrying both is answering the question in the form
    that resolves, and counting it as prose would understate the district.
    """
    typed = field_block(markup, "prerequisite-courses")
    if typed is not None:
        # DEDUPLICATED. One course linked twice in the same field counted
        # twice in both the links and the resolved numerators, inflating a
        # rate whose whole claim is that the links land.
        links = sorted({path for path in
                        (same_host(href, base) for href in HREF.findall(typed))
                        if path})
        if links:
            return {"kind": "typed", "links": links,
                    "resolved": [href for href in links if href in published]}
        # **A typed field holding no course link is its own answer.** It fell
        # through to the prose branch, so a district that emits the field and
        # fills it with navigation or off-host links was reported as not using
        # it at all. That is a different fact from "no field" and from
        # "prose", and only this branch can tell them apart.
        text = plain(typed)
        if text:
            return {"kind": "typed but no course link", "text": text[:120]}

    prose = field_block(markup, "pr")
    if prose is not None:
        text = plain(prose)
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


def plain(markup: str) -> str:
    """Markup as readable text, with the tags and comments gone.

    Comments are removed FIRST. `<[^>]+>` stops at the first `>`, so
    `<!-- <div> -->` left a stray `-->` in the text — which then read as
    prose content and, in a prose field, as a stated prerequisite.
    """
    without = re.sub(r"<!--.*?-->|<script\b.*?</script>|<style\b.*?</style>",
                     " ", markup, flags=re.S | re.I)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", without)).strip()


def field_block(markup: str, name: str) -> str | None:
    """One named field's own markup, bounded, or None if the page has no such
    field.

    **Bounded at the next field or the end of the article**, never at the end
    of the document. And it starts AFTER the opening tag, so the recorded text
    no longer begins with the class attribute it was matched on.

    The name is matched as a whole field name — `pr` must not match
    `prerequisite-courses`. Both patterns previously relied on a `\b` for
    that, which works but is easy to misread; the class list is split and
    compared instead, which is not.
    """
    for at, field in field_openings(markup):
        if field != name:
            continue
        # The tag's own `>`, found on the MASKED markup — a `>` inside a
        # quoted attribute value is not the end of the tag, and starting
        # there put the attribute's tail into the block. Reproduced: a
        # `data-x="<div>"` yielded a prose field reading `"> See counsellor.`
        hidden = masked(markup)
        closes = hidden.find(">", at)
        if closes == -1:
            continue
        after = closes + 1
        stop = field_ends_at(markup, after)
        # BACK UP TO THE TAG the boundary sits inside. `field--name-field-X`
        # is a class attribute, so cutting at it leaves a dangling `<div
        # class="` in the block — which `plain()` then renders as text,
        # because an unclosed tag has nothing to strip.
        opened = markup.rfind("<", after, stop)
        if opened != -1 and markup.find(">", opened, stop) == -1:
            stop = opened
        return markup[after:stop]
    return None


def field_ends_at(markup: str, after: int) -> int:
    """Where the field opened before `after` closes.

    **Depth-aware.** Stopping at the first `field--name-field-` meant a
    SUB-field rendered inside a `field__item` — routine in a Drupal
    entity-reference teaser, where each referenced node brings its own fields
    — ended the block early. Constructed, a prerequisite list of two courses
    with a `field-course-number` inside the first item returned one link. That
    under-counts links, which is the denominator of the "every link resolves"
    claim, and can turn a multi-prerequisite course into a single-prerequisite
    one.

    So a boundary only terminates the block at depth zero — that is, once the
    `<div>`s opened inside the field have closed again. `</article>`,
    `</main>` and `<footer>` still stop it unconditionally: those close the
    page region, and a field that reached past them was never bounded at all.
    """
    # TWO scans over one string, because the two things being looked for
    # live in different places. Div structure is counted on the MASKED text,
    # so a `<div` in a comment, a script body or an attribute value does not
    # move the depth. Sibling fields are read from `field_openings`, which
    # searches the ORIGINAL — a field name lives in a class attribute, and
    # masking hides exactly that.
    #
    # The first version masked both and so could not see a sibling field at
    # all: with an unclosed `<div>` the depth never returned to zero and the
    # block swallowed every field after it.
    hidden = masked(markup)
    events = [(m.start(), "div" if m.group(0).lower().startswith("<div")
               else "close" if m.group(0).lower().startswith("</div")
               else "region")
              for m in DIV_OR_BOUNDARY.finditer(hidden, after)]
    events += [(at, "field") for at, _ in field_openings(markup) if at >= after]
    events.sort()

    depth = 0
    for at, kind in events:
        if kind == "div":
            depth += 1
        elif kind == "close":
            depth -= 1
            if depth < 0:
                # The field's own closing tag.
                return at
        elif kind == "region":
            # `</article>`, `</main>` or `<footer>` — these close the page
            # region and a field that reached past them was never bounded.
            return at
        # A sibling field terminates the block once the divs opened inside
        # ours have closed. It ALSO terminates it when the depth has run away
        # — markup with an unclosed `<div>` never returns to zero, and
        # without this the block would swallow every field after it. The
        # depth count is a heuristic over a language regexes cannot parse;
        # this is the backstop for when the heuristic is wrong.
        elif depth <= 0 or depth > MAX_NESTING:
            return at
    return len(markup)


#: Regions whose contents are not markup: HTML comments, script and style
#: bodies, and quoted attribute values.
NOT_MARKUP = re.compile(
    r"<!--.*?-->|<script\b.*?</script>|<style\b.*?</style>|\"[^\"]*\"|'[^']*'",
    re.S | re.I)


def masked(markup: str) -> str:
    """`markup` with everything that is not structure replaced by spaces.

    **The depth counter is a token scan and knew nothing about context.** Any
    `<div` inside a comment, a script body or an attribute value incremented
    the depth and never came back — and once the count is off by one, the
    field's own `</div>` reads as a child's and the block runs into its
    neighbour. That is the original bug through a different door: reproduced
    with a `<div>` in an HTML comment, the typed field returned a link from a
    sibling `field-related-courses`, and an attribute-borne `<div>` in a prose
    field regenerated the exact string this page retracts as an artifact.

    Same LENGTH, so every offset the caller computes still points at the same
    character of the original.
    """
    return NOT_MARKUP.sub(lambda m: " " * len(m.group(0)), markup)


def field_openings(markup: str):
    """(position, field name) for every `field--name-field-X` in the page."""
    # Masked too: `field--name-field-pr` inside a `<script>` blob is text,
    # not a field, and selecting it would bound the block from a position no
    # element opens at.
    #
    # The class attribute is quoted, so masking hides it as well — the search
    # runs on the ORIGINAL and each hit is checked against the mask, which is
    # the same length and so shares its offsets.
    hidden = masked(markup)
    for found in re.finditer(FIELD_OPENS + r"([a-z0-9-]+)", markup):
        inside_a_comment_or_script = hidden[found.start()] == " " and \
            markup[found.start()] != " " and not _in_class_attribute(markup, found.start())
        if inside_a_comment_or_script:
            continue
        yield found.start(), found.group(1)


def _in_class_attribute(markup: str, at: int) -> bool:
    """Is this position inside a `class="…"` value on an open tag?

    Masking hides every quoted attribute, and a field name legitimately lives
    in one. This tells the legitimate case from a `<script>` blob.
    """
    opened = markup.rfind("<", max(0, at - 400), at)
    if opened == -1:
        return False
    closed = markup.find(">", opened)
    return closed == -1 or closed > at

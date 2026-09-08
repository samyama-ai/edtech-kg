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

#: Every token `field_ends_at` has to see to keep its depth count honest.
DIV_OR_BOUNDARY = re.compile(
    r"<div\b|</div>|</article|</main|<footer|" + FIELD_OPENS, re.I)


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
        if text and text.lower() not in {"none", "n/a", "na", "-"}:
            return {"kind": "prose", "text": text[:120]}
        return {"kind": "says none", "text": text}
    return {"kind": "no field"}


def plain(markup: str) -> str:
    """Markup as readable text, with the tags gone."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", markup)).strip()


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
        after = markup.index(">", at) + 1
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
    depth = 0
    for token in DIV_OR_BOUNDARY.finditer(markup, after):
        text = token.group(0).lower()
        if text.startswith("<div"):
            depth += 1
            continue
        if text.startswith("</div"):
            depth -= 1
            if depth < 0:
                # The field's own closing tag.
                return token.start()
            continue
        if text.startswith(("</article", "</main", "<footer")):
            return token.start()
        # A sibling field, but only once ours has closed its children.
        if depth <= 0:
            return token.start()
    return len(markup)


def field_openings(markup: str):
    """(position, field name) for every `field--name-field-X` in the page."""
    for found in re.finditer(FIELD_OPENS + r"([a-z0-9-]+)", markup):
        yield found.start(), found.group(1)

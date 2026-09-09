"""Reading a district's course page — the STRUCTURE, not the meaning.

Split from `etl/course_page.py` at the 500-line review limit, and split by
SUBJECT rather than by length: that module asks what a page SAYS about
prerequisites, this one finds the region it says it in. The hazards are
different, which is the test for whether a split is real. A wrong reading
misreports one page; a wrong BOUND reports a neighbouring field's content as
this page's, which is how a district's prerequisite rate gets manufactured.

**This file used to scan HTML with regular expressions, and it took four
review rounds to stop.** Each round fixed one bound and the next round found
the same failure through a different door: a `class` attribute the scanner
could not locate, a comment whose `-->` became prose, an attribute value
holding `<div>`, an unclosed quote pairing with the next tag's quote. Those
are not four bugs. They are one — the code was deciding what was markup and
what was text, and that is a parser's job.

**Then round five found the same thing one level up.** The parser was in
place, but the bound was a DEPTH COUNTER over start tags, which is a model of
the document rather than the document. HTML lets `<p>`, `<li>`, `<td>`,
`<tr>`, `<dd>` and `<option>` omit their closing tag, and Drupal field output
is full of `<p>`. So the count never came back, the next sibling field looked
deeper, and its link was returned as a prerequisite that resolves — on
ordinary markup, not on malformed input.

There is a real open-element stack now, with HTML's implied-end-tag rules for
the handful of elements that matter. **A field ends when its own element is
popped**, so there is no depth arithmetic left to get wrong, and a sibling
cannot be mistaken for a sub-field.

Where the markup genuinely does not close what it opens, the region is
reported UNBOUNDED and `classify` refuses to read it. Refusing a measurement
this repo cannot stand behind is its usual answer; it had simply never been
applied to markup.

No network.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

from etl.course_page_fields import FIELD_OPENS

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

    def __init__(self, name: str):
        self.name = name
        self.text: list[str] = []
        self.links: list[str] = []
        self.bounded = False

    def readable(self) -> str:
        return re.sub(r"\s+", " ", "".join(self.text)).strip()


class FieldReader(HTMLParser):
    """Every `field--name-field-X` region on the page, in one pass.

    **A real open-element stack, not a depth counter.** Counting start tags
    is a model of the document rather than the document, and HTML lets `<p>`,
    `<li>`, `<td>`, `<tr>`, `<dd>` and `<option>` omit their closing tag.
    Drupal field output is full of `<p>`.

    So the count never came back, the next sibling field looked DEEPER and was
    taken for a sub-field, and its content landed in the open field. With an
    outer wrapper closing afterwards the region was even marked bounded, so
    `classify` read it rather than refusing. Reproduced before this rewrite:

        <div class="page">
          <div class="field--name-field-prerequisite-courses">
            <div class="field__item"><p>See below<a href="/m/a">A1</a></div>
          </div>
          <div class="field--name-field-related"><a href="/m/b">not one</a></div>
        </div>

        -> links ['/m/a', '/m/b'], BOTH resolved

    The neighbour's link, returned as a prerequisite that resolves. That is
    the published number — the resolution claim this page rests on —
    manufactured by the reader out of ordinary markup.

    With a stack there is no depth arithmetic at all: **a field ends when its
    own element is popped.** A sibling field cannot be mistaken for a
    sub-field, because a sibling's element opens only after the previous
    field's element has closed.
    """

    #: Elements HTML permits to be closed implicitly. When one of these is
    #: still open as its parent closes, the markup is FINE and the parser
    #: must not conclude anything from it.
    OPTIONAL_END = {"p", "li", "td", "th", "tr", "dd", "dt", "option",
                    "optgroup", "thead", "tbody", "tfoot", "caption",
                    "colgroup", "rt", "rp"}

    #: A `<p>` is closed by any of these opening. The full HTML rule is
    #: longer; these are the ones that appear in course-catalogue markup.
    CLOSES_A_PARAGRAPH = {"p", "div", "ul", "ol", "dl", "table", "section",
                          "article", "aside", "header", "footer", "h1", "h2",
                          "h3", "h4", "h5", "h6", "blockquote", "pre", "form",
                          "hr", "main", "nav", "figure", "fieldset"}

    def __init__(self):
        # `convert_charrefs=True` is the default and is wanted: `&nbsp;`
        # arrives as a character rather than as six of them, which is what
        # `states_a_prerequisite` had to undo by hand.
        super().__init__(convert_charrefs=True)
        self.fields: dict[str, Field] = {}
        self.open: Field | None = None
        #: (element name, the Field this element opened, or None)
        self.stack: list[tuple[str, Field | None]] = []
        self.silent = 0          # inside a script/style/template/noscript
        self.stopped = False     # past </article>, </main> or <footer>

    # -- structure ---------------------------------------------------------

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if self.stopped:
            return

        if tag in NOT_TEXT:
            # **The field is NOT registered while silent, and that is the
            # fix.** `HTMLParser` treats only script and style as CDATA, so
            # `<template>` and `<noscript>` bodies are parsed as real markup:
            # a field name in one registered an EMPTY field, and the guard
            # below then blocked the genuine field later on the page. A real
            # typed field became "no field", and a `<noscript>` copy turned
            # "Algebra 1 required." into "says none" — a silent undercount of
            # exactly the metric this probe reports.
            self.silent += 1
            self.stack.append((tag, None))
            return

        if tag in VOID:
            return

        if tag == "footer" and not self.silent:
            # A `<footer>` inside a `<template>` used to stop the whole page
            # and discard everything real after it.
            self._stop()
            return

        self._imply_ends_before(tag)

        # **Only when nothing is open.** A field nested inside an open one is
        # a SUB-field — routine in a Drupal entity-reference teaser, where
        # each referenced node brings its own fields — and its content
        # belongs to the field containing it. Registering it would take the
        # region over and return one link where a two-course prerequisite
        # list has two, under-counting the denominator of the resolution
        # claim.
        name = None if self.silent else self._field_name(attrs)
        field = None
        if name is not None and self.open is None and name not in self.fields:
            field = Field(name)
            self.fields[name] = field
            self.open = field
        self.stack.append((tag, field))

        if len(self.stack) > MAX_NESTING:
            # Runaway rather than deep. Even with a stack, markup that opens
            # without closing grows it without bound.
            self._unbind_everything()

    def handle_startendtag(self, tag, attrs):
        """`<div/>` — XHTML self-closing on an element HTML does not treat
        that way. Opened and closed, so it cannot leave the stack unbalanced."""
        if self.stopped or tag.lower() in VOID:
            return
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if self.stopped:
            return
        if tag in VOID:
            return
        if tag in REGION_ENDS and not self.silent:
            self._stop()
            return

        depth = self._innermost(tag)
        if depth is None:
            # A stray end tag closing nothing. Ignored rather than treated as
            # malformity: it is common in CMS output and says nothing about
            # whether a field is bounded.
            return

        # Everything above it was left open. That is FINE for the elements
        # HTML lets you leave open, and malformity for anything else — and
        # malformity is where a region stops being one this reader can stand
        # behind.
        implied = [name for name, _ in self.stack[depth + 1:]]
        malformed = [name for name in implied if name not in self.OPTIONAL_END]

        for name, field in reversed(self.stack[depth:]):
            if field is not None:
                field.bounded = not malformed
                if self.open is field:
                    self.open = None
            if name in NOT_TEXT:
                self.silent = max(0, self.silent - 1)
        del self.stack[depth:]

        if malformed and self.open is not None:
            self.open.bounded = False
            self.open = None

    def _imply_ends_before(self, tag):
        """Close what this tag implicitly closes, per HTML's own rules.

        `<li>` closes an open `<li>`; a block element closes an open `<p>`.
        Without this the stack never unwinds on ordinary markup — which is
        the whole of finding 1.
        """
        while self.stack:
            innermost, field = self.stack[-1]
            implied = (
                (innermost == tag and innermost in self.OPTIONAL_END)
                or (innermost == "p" and tag in self.CLOSES_A_PARAGRAPH)
                or (innermost in ("td", "th") and tag in ("td", "th", "tr"))
                or (innermost == "tr" and tag == "tr")
                or (innermost in ("dd", "dt") and tag in ("dd", "dt"))
            )
            if not implied:
                return
            if field is not None:
                field.bounded = True
                if self.open is field:
                    self.open = None
            self.stack.pop()

    def _innermost(self, tag):
        for at in range(len(self.stack) - 1, -1, -1):
            if self.stack[at][0] == tag:
                return at
        return None

    def _stop(self):
        """`</article>`, `</main>` or `<footer>` — the page region ends.

        A field still open here never closed, so it is unbounded. Everything
        after is navigation.
        """
        self._unbind_everything()
        self.stopped = True

    def _unbind_everything(self):
        for _, field in self.stack:
            if field is not None:
                field.bounded = False
        if self.open is not None:
            self.open.bounded = False
        self.open = None

    def close(self):
        # Anything still open at the end of the document never closed.
        self._unbind_everything()
        super().close()

    # -- content -----------------------------------------------------------

    def handle_data(self, data):
        if self.open is not None and not self.silent:
            self.open.text.append(data)

    # `handle_comment` is NOT overridden, and that is the point: a comment is
    # its own event, so `<!-- <div> -->` can no longer leave a stray `-->` in
    # the text or move the structure. Three of the round-4 blockers were this
    # one fact, arriving separately.

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
    # **The field is held here, not read back off the reader.** `plain()`
    # used to return `reader.open.readable()`, and any region-ending tag —
    # `</article>`, `</body>`, a `<footer>` — sets `open` to None, so
    # `plain('<div>hi</div></article>')` raised AttributeError. It is a public
    # helper in an ETL module and a whole page is the obvious thing to pass it.
    everything = Field("")
    reader = FieldReader()
    reader.open = everything
    reader.feed(markup)
    reader.close()
    return everything.readable()



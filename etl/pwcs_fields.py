"""Reading one named field out of the catalogue's markup.

Split from `etl/probe_pwcs.py` at the 500-line review limit — six reviews in
this repo have reported a file as too large and reviewed nothing inside it.
Split by SUBJECT: that module fetches the catalogue, classifies its pages and
reports what it found; this is the small thing underneath, which is "given a
page and a field name, what does the field say".

The catalogue is Drupal, so every field is a div whose class names it:

    <div class="field field--name-field-description field__item">…</div>
    <div class="field field--name-field-grades">
      <div class="field__items">
        <div class="field__item">10,</div>

Two things about that shape have already been wrong once each, and both are
tested rather than remembered — see `tests/test_probe_pwcs.py`.
"""

from __future__ import annotations

import functools
import html
import re


def text_of(markup: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", markup))


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
#
# `<footer` TOO, which `PREREQ_BLOCK` in `etl/probe_pwcs.py` already carries
# for the same reason its own comment gives — reading a field out of flattened
# page text "would run it into the footer and turn the school's street address
# into a course name". A description that is the LAST field on a page with no
# `</article>` fell through to the end of the document and took the address and
# the nav with it. Measured before the fix; the earlier tests all placed a
# sibling field after the description and never reached the case.
#
# A `field__label` is STRIPPED, not stopped at. `field\b` does not match it —
# `_` is a word character, so there is no boundary — and on the standard Drupal
# labelled shape the label sits inside the wrapper, so the description came out
# as "Description Real text". Ending the capture there instead returns nothing,
# which is worse; `field_items` already defends against label placement and
# this is the same variation on the other reader.
# `{name}` by KEYWORD, not `{}`. This is a `.format` template, so a future
# `{n,m}` quantifier anywhere in it raises `KeyError` — naming the field makes
# that visible rather than surprising. Compiled once per field name below,
# because it is applied to 791 pages twice each.
FIELD = (r'field--name-field-{name}\b[^>]*>'
         r'(.*?)(?=<div class="field\b|<span class="field\b|'
         r'</article>|<footer|\Z)')

#: The field's own label, which is chrome and not content. REMOVED from the
#: capture rather than used to end it: on the labelled shape the label sits
#: immediately inside the wrapper, so stopping there captures nothing at all.
FIELD_LABEL = re.compile(r'<(div|span) class="field__label[^>]*>.*?</\1>', re.S)
# `field__item` and NOT `field__items`. `[^>]*` absorbed the `s"` of the
# container class, so the wrapper matched first and its capture ran to the
# first `</div>` inside it. On this template that is the first real item, so
# the answer came out right by coincidence of ordering — move the label inside
# `field__items`, which Drupal templates do, and `Grades` is emitted as a grade
# level. Verified before the fix.
FIELD_ITEM = re.compile(r'field__item(?![\w-])[^>]*>(.*?)</div>', re.S)


@functools.lru_cache(maxsize=None)
def field_pattern(name: str) -> re.Pattern:
    """One compiled matcher per field name, like every other regex here.

    `name` is escaped. Every caller passes a literal, so this is not
    exploitable — but it is interpolated into a pattern built by `.format`,
    and the two together are how a field name with a `.` or a `-` in it
    quietly starts matching something else.
    """
    return re.compile(FIELD.format(name=re.escape(name)), re.S)


def field_text(markup: str, name: str) -> str | None:
    """One field's text, unescaped and whitespace-collapsed."""
    found = field_pattern(name).search(markup)
    if not found:
        return None
    return " ".join(text_of(FIELD_LABEL.sub(" ", found.group(1))).split()) or None


def field_items(markup: str, name: str) -> list[str]:
    """A field published as a LIST of items — `Grades` renders one div each.

    Trailing commas stripped: the catalogue writes them as `9,` `10,` `12`, so
    the separator is inside the value on every item but the last.
    """
    found = field_pattern(name).search(markup)
    if not found:
        return []
    return [item for item in
            (" ".join(text_of(raw).split()).strip(", ")
             for raw in FIELD_ITEM.findall(found.group(1)))
            if item]

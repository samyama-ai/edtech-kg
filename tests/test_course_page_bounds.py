"""Where a field ENDS — the bound, not the answer.

Split from `tests/test_course_page.py` at the 500-line review limit, and split
by SUBJECT: that file asks what a page says about prerequisites, this one asks
where the reader stopped looking. The hazards are different. A wrong answer
misreports one page; a wrong bound reports a NEIGHBOUR'S content as this
page's, which is how a district's prerequisite rate gets manufactured.

Every case here was a review finding. Four of them are the round-4 blockers on
edtech-kg#179, which are one defect — the reader was deciding what was markup
and what was text — reported four times because it surfaced four ways. They
are kept separate because a future reader that gets three right and one wrong
should fail three times rather than once.
"""

from __future__ import annotations

from etl import course_page


def test_a_comment_inside_the_typed_field_is_not_its_content():
    """Repro: a comment inside the typed field hid the real link and recorded
    `<!--` as the text. `<[^>]+>` stops at the first `>`, so a comment
    containing markup was half-stripped.

    `HTMLParser` reports a comment as its own event, so there is nothing to
    strip and nothing to get wrong.
    """
    markup = ('<div class="field--name-field-prerequisite-courses">'
              '<!-- <a href="/m/old">retired</a> -->'
              '<a href="/m/a">Algebra</a></div>')
    found = course_page.classify(markup, {"/m/a"})
    assert found["kind"] == "typed", found
    assert found["links"] == ["/m/a"], "the comment's own link was counted"


def test_a_commented_out_field_does_not_capture_the_next_fields_content():
    """Repro: a commented-out `field-pr` recorded the NEXT field's content as
    a prerequisite — `{'kind': 'prose', 'text': '1 credit, weighted.'}`."""
    markup = ('<!-- <div class="field--name-field-pr">old</div> -->'
              '<div class="field--name-field-credits">'
              '<div class="field__item">1 credit, weighted.</div></div>')
    assert course_page.classify(markup, set())["kind"] == "no field"


def test_a_field_name_in_a_data_attribute_is_not_a_field():
    """Repro: `_in_class_attribute('<div data-x="field--name-field-pr">', 20)`
    returned True — it never looked for a `class` attribute at all, only for a
    surrounding tag. The parser is given attributes by name."""
    assert course_page.classify(
        '<div data-x="field--name-field-pr">text</div>', set()) == {
            "kind": "no field"}


def test_a_field_name_in_a_script_template_is_not_a_field():
    """Repro: a `<script type="text/template">` pulled text from the prose
    field. `<script>` bodies are character data the parser hands over
    labelled, so `NOT_TEXT` can drop them."""
    markup = ('<script type="text/template">'
              '<div class="field--name-field-pr">Not a real field</div>'
              '</script>')
    assert course_page.classify(markup, set())["kind"] == "no field"


def test_an_attribute_holding_a_comment_close_does_not_reach_the_text():
    """**Blocker 3, and the one that moves the headline metric.** `plain()`
    stripped comments and tags on the raw string, so
    `<div title="-->">Real text</div>` returned `'">Real text'`.

    End to end: a prose field whose whole content is `None.` behind a
    `data-tip="-->"` classified as a STATED PREREQUISITE, because the `">`
    prefix defeats `SAYS_NONE`'s `^` anchor. A denial counted as a
    prerequisite — which is exactly what round 3 was written to fix, arriving
    through the other door.
    """
    assert course_page.plain('<div title="-->">Real text</div>') == "Real text"
    markup = ('<div class="field--name-field-pr">'
              '<div data-tip="-->">None.</div></div>')
    assert course_page.classify(markup, set())["kind"] == "says none"


def test_an_unclosed_quote_does_not_pair_with_the_next_tags_quote():
    """**Blocker 4.** `"[^"]*"` backtracked across a missing close quote and
    paired with the next tag's quote, so `<div class="field__item>` inside a
    typed field yielded the SIBLING's link as a prerequisite. Unescaped quotes
    in CMS-authored `title`/`alt` are common on district catalogues.

    The region is now reported unbounded rather than resolved from a
    neighbour — the page is genuinely malformed and any link taken from it is
    a guess.
    """
    markup = ('<div class="field--name-field-prerequisite-courses">'
              '<span class="field__item></span></div>'
              '<div class="field--name-field-related">'
              '<a href="/m/b">not a prerequisite</a></div>')
    found = course_page.classify(markup, {"/m/b"})
    assert found["kind"] == "unbounded field", found
    assert "links" not in found, "a link was taken from a malformed region"


def test_one_unclosed_div_does_not_carry_the_field_into_its_neighbour():
    """**Blocker 2, unchanged across four rounds.** One unclosed `<div>` left
    the depth never returning to zero, so the next field's link came back as a
    prerequisite AND as resolving — manufacturing the exact finding this probe
    publishes.

    Mutating `elif depth <= 0` to `depth < 0` used to leave the whole suite
    green, which is what "the sibling bound is not covered" means.
    """
    markup = ('<div class="field--name-field-prerequisite-courses">'
              '<div class="field__item">'                      # never closed
              '</div>'
              '<div class="field--name-field-related">'
              '<a href="/m/b">not a prerequisite</a></div>')
    found = course_page.classify(markup, {"/m/b"})
    assert found["kind"] == "unbounded field", found
    assert found.get("field") == "prerequisite-courses"


def test_a_sub_field_inside_a_teaser_does_not_end_the_block():
    """The bound must not swing the other way. A Drupal entity-reference
    teaser brings each referenced node's own fields, and stopping at the first
    of them turned a two-course prerequisite list into a one-course one —
    under-counting the denominator of the "every link resolves" claim.
    """
    markup = ('<div class="field--name-field-prerequisite-courses">'
              '<div class="field__item"><a href="/m/a">A</a>'
              '<div class="field--name-field-course-number">1234</div></div>'
              '<div class="field__item"><a href="/m/b">B</a></div></div>')
    found = course_page.classify(markup, {"/m/a", "/m/b"})
    assert found["kind"] == "typed", found
    assert found["links"] == ["/m/a", "/m/b"], found


def test_every_href_spelling_is_the_same_event():
    """`href='…'` single-quoted, `HREF=` and `Href=` all used to yield "typed
    but no course link" — the same misclassification the round-4 fix targeted,
    through a different quoting style. The parser lower-cases attribute names
    and unquotes values, so there is one spelling to handle."""
    for attribute in ('href="/m/a"', "href='/m/a'", "HREF='/m/a'",
                      'Href="/m/a"', "href=/m/a"):
        markup = (f'<div class="field--name-field-prerequisite-courses">'
                  f'<a {attribute}>A</a></div>')
        found = course_page.classify(markup, {"/m/a"})
        assert found["kind"] == "typed", (attribute, found)
        assert found["links"] == ["/m/a"], attribute


def test_a_query_string_or_fragment_leaves_the_path_intact():
    """`[^"#?]+` between the quotes matched NOTHING for
    `href="/m/a?from=x"`, so a prerequisite carrying a query string was
    invisible — and `links` is the denominator of the resolution claim.

    Stripped in `same_host` now, which is the only place that knows what a
    course path is.
    """
    for href in ("/m/a?from=x", "/m/a#top", "/m/a?a=b#c"):
        markup = (f'<div class="field--name-field-prerequisite-courses">'
                  f'<a href="{href}">A</a></div>')
        assert course_page.classify(markup, {"/m/a"})["links"] == ["/m/a"], href


def test_entities_arrive_decoded():
    """`&nbsp;` survived `plain()` as six literal characters, so a field
    holding only a non-breaking space could never look empty and
    `states_a_prerequisite` had to undo it by hand. `convert_charrefs` does
    it at the parse."""
    empty = '<div class="field--name-field-pr">&nbsp;&nbsp;</div>'
    assert course_page.classify(empty, set())["kind"] == "says none"
    # And a decoded entity that IS content stays content — the point is that
    # the text is decoded, not that decoding makes fields empty.
    named = '<div class="field--name-field-pr">Algebra&nbsp;I &amp; II</div>'
    assert course_page.classify(named, set()) == {
        "kind": "prose", "text": "Algebra I & II"}

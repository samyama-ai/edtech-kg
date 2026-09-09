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

from etl import course_page, course_reader


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


# --------------------------------------------------------------------------
# Round five. All three findings have one root cause: a DEPTH COUNTER over
# start tags is a model of the document rather than the document. The reader
# keeps a real open-element stack now, and a field ends when its own element
# is popped — there is no depth arithmetic left to get wrong.


def test_an_unclosed_p_does_not_put_a_neighbours_link_in_this_field():
    """**The one that fires on ORDINARY markup, not on malformed input.**

    HTML lets `<p>` omit its closing tag and Drupal field output is full of
    them. Counting start tags, the depth never came back: the next sibling
    field looked DEEPER, was taken for a sub-field, and its content landed in
    the open field. With an outer wrapper closing afterwards the region was
    even marked bounded, so `classify` read it rather than refusing.

    Reproduced before the fix — `links: ['/m/a', '/m/b']`, both resolved. The
    neighbour's link, reported as a prerequisite that resolves: the published
    resolution figure, manufactured by the reader.
    """
    markup = ('<div class="page">'
              '<div class="field--name-field-prerequisite-courses">'
              '<div class="field__item"><p>See below'
              '<a href="/m/a">A1</a></div></div>'
              '<div class="field--name-field-related">'
              '<a href="/m/b">not a prerequisite</a></div></div>')
    found = course_page.classify(markup, {"/m/a", "/m/b"})
    assert found["kind"] == "typed", found
    assert found["links"] == ["/m/a"], found
    assert found["resolved"] == ["/m/a"], found


def test_an_unclosed_li_does_not_swallow_the_next_field():
    """`<ul><li>none here</ul>` was worse than the `<p>` case: the typed
    field reported ONLY the neighbour's link."""
    markup = ('<div class="field--name-field-prerequisite-courses">'
              '<div class="field__item"><ul><li>none here</ul>'
              '<a href="/m/a">A1</a></div></div>'
              '<div class="field--name-field-related">'
              '<a href="/m/b">not a prerequisite</a></div>')
    found = course_page.classify(markup, {"/m/a", "/m/b"})
    assert found["links"] == ["/m/a"], found


def test_the_prose_field_after_an_unclosed_p_is_still_its_own_field():
    """The other half of the same defect: the swallowed field disappeared
    entirely, so a district's prose count fell silently."""
    markup = ('<div class="field--name-field-prerequisite-courses">'
              '<div class="field__item"><p>x<a href="/m/a">A1</a></div></div>'
              '<div class="field--name-field-pr"><p>Teacher recommendation</div>')
    assert "pr" in course_page.read_fields(markup)
    assert course_page.read_fields(markup)["pr"].readable() == \
        "Teacher recommendation"


def test_a_field_name_in_a_template_does_not_shadow_the_real_one():
    """**`HTMLParser` treats only `script` and `style` as CDATA.** So
    `<template>` and `<noscript>` bodies are parsed as real markup: the field
    name fired, an EMPTY field was registered, and the guard then blocked the
    genuine field later on the page. A real typed field became "no field".
    """
    markup = ('<template><div class="field--name-field-prerequisite-courses">'
              'placeholder</div></template>'
              '<div class="field--name-field-prerequisite-courses">'
              '<a href="/m/a">A1</a></div>')
    found = course_page.classify(markup, {"/m/a"})
    assert found["kind"] == "typed", found
    assert found["links"] == ["/m/a"]


def test_a_field_in_a_noscript_does_not_turn_a_statement_into_a_denial():
    """The `<noscript>` variant of the same bug turned
    "Algebra 1 required." into `says none` — a silent undercount of exactly
    the metric this page's headline turns on."""
    markup = ('<noscript><div class="field--name-field-pr">nothing</div>'
              '</noscript>'
              '<div class="field--name-field-pr">Algebra 1 required.</div>')
    found = course_page.classify(markup, set())
    assert found == {"kind": "prose", "text": "Algebra 1 required."}, found


def test_a_footer_inside_a_template_does_not_stop_the_page():
    """`stopped` latched, so everything real after it was discarded."""
    markup = ('<template><footer>navigation</footer></template>'
              '<div class="field--name-field-pr">Algebra 1 required.</div>')
    assert course_page.classify(markup, set())["kind"] == "prose"


def test_a_field_still_open_at_the_article_end_is_unbounded():
    """**The policy the whole rewrite is built around, and it was untested.**

    Mutating `bounded=False` to `True` at `</article>` and at `<footer>`
    survived the entire 1,590-test suite. A typed field left open at
    `</article>` must classify as `unbounded field`, not as a reading of
    whatever it swallowed on the way there.
    """
    markup = ('<article><div class="field--name-field-prerequisite-courses">'
              '<a href="/m/a">A1</a></article>'
              '<nav><a href="/m/b">navigation</a></nav>')
    found = course_page.classify(markup, {"/m/a", "/m/b"})
    assert found["kind"] == "unbounded field", found
    assert "links" not in found, "a link was read out of an unbounded region"


def test_a_field_still_open_at_a_footer_is_unbounded():
    """`<footer>` is the other region end, and it had the same hole."""
    markup = ('<div class="field--name-field-prerequisite-courses">'
              '<a href="/m/a">A1</a>'
              '<footer><a href="/m/b">navigation</a></footer>')
    found = course_page.classify(markup, {"/m/a", "/m/b"})
    assert found["kind"] == "unbounded field", found


def test_a_field_still_open_at_the_end_of_the_document_is_unbounded():
    """A field whose element never closes at all. Navigation links to
    published courses always resolve, which is precisely the claim being
    made."""
    markup = ('<div class="field--name-field-prerequisite-courses">'
              '<a href="/m/a">A1</a>')
    assert course_page.classify(markup, {"/m/a"})["kind"] == "unbounded field"


def test_runaway_nesting_is_bounded():
    """`MAX_NESTING` 30 to 3000 also survived the suite. Markup that opens
    without closing grows the stack without bound, and the ceiling is what
    keeps a wrong structure finite."""
    markup = ('<div class="field--name-field-prerequisite-courses">'
              + "<div>" * (course_reader.MAX_NESTING + 5)
              + '<a href="/m/a">A1</a>')
    assert course_page.classify(markup, {"/m/a"})["kind"] == "unbounded field"


def test_plain_survives_a_region_ending_tag():
    """`plain()` read `reader.open` back after the parse, and any region end
    sets it to None — so `plain('<div>hi</div></article>')` raised
    AttributeError. It is a public helper in an ETL module and a whole page is
    the obvious thing to pass it."""
    assert course_page.plain("<div>hi</div></article>") == "hi"
    assert course_page.plain("before<footer>f</footer>") == "before"
    assert course_page.plain("<body>x</body>") == "x"


def test_a_self_closing_div_does_not_unbalance_the_stack():
    """`<div/>` is XHTML self-closing on an element HTML does not treat that
    way. Left on the stack it never closes, and the field never bounds."""
    markup = ('<div class="field--name-field-prerequisite-courses">'
              '<div/><a href="/m/a">A1</a></div>')
    found = course_page.classify(markup, {"/m/a"})
    assert found["kind"] == "typed", found
    assert found["links"] == ["/m/a"]


def test_a_typed_field_left_empty_is_not_the_same_as_no_field():
    """"The district emits this field and left it empty" and "the district
    does not use this field" are different facts about a district — which is
    the argument the `typed but no course link` branch's own name makes.

    A typed field holding only `&nbsp;` fell through to the prose branch and
    came out as `no field`, so a district that emits the field on every page
    and fills it on none looked identical to one that has never heard of it.
    """
    for empty in ('<div class="field--name-field-prerequisite-courses">'
                  '&nbsp;</div>',
                  '<div class="field--name-field-prerequisite-courses">'
                  '</div>'):
        found = course_page.classify(empty, set())
        assert found["kind"] == "typed but no course link", found
    assert course_page.classify('<div class="other">x</div>', set()) == {
        "kind": "no field"}


def test_a_long_list_of_unclosed_items_is_not_runaway_nesting():
    """**This is what the implied-end-tag rule is for**, and without it the
    rule is inert — removing `_imply_ends_before` survived every other test
    here.

    A list of forty `<li>` with no closing tags is ordinary catalogue markup,
    not malformity. Nested rather than implied-closed, it passes
    `MAX_NESTING` and the field is reported unbounded — a real prerequisite
    list, refused for being a list.
    """
    markup = ('<div class="field--name-field-prerequisite-courses"><ul>'
              + "".join(f"<li>item {i}" for i in range(40))
              + '<li><a href="/m/a">A1</a></ul></div>')
    found = course_page.classify(markup, {"/m/a"})
    assert found["kind"] == "typed", found
    assert found["links"] == ["/m/a"]


def test_the_nesting_ceiling_is_a_fixed_number_of_elements():
    """Written with a literal 60, not `MAX_NESTING + 5`.

    Derived from the constant, the test scaled with it: raising
    `MAX_NESTING` from 30 to 3000 left the whole suite green, so the ceiling
    was covered by a test that could not fail on the thing it named.
    """
    markup = ('<div class="field--name-field-prerequisite-courses">'
              + "<section>" * 60 + '<a href="/m/a">A1</a>')
    assert course_page.classify(markup, {"/m/a"})["kind"] == "unbounded field"
    assert course_reader.MAX_NESTING < 60, (
        "the ceiling is above the depth this test builds, so it no longer "
        "exercises it")

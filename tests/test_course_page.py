"""Reading ONE course page — which field, bounded where.

Split from `tests/test_probe_second_district.py` when it passed the 500-line
review limit, matching the split of the module under test. Split by SUBJECT:
that file walks catalogues and samples them; this reads a single page.

**Every bound asserted here exists because it was once absent.** The first
version matched the free-text field on every district and reported PWCS at 0%
linked; the second let an unbounded pattern reach into a neighbouring field
and record its text as a prerequisite; the third stopped at a NESTED field and
dropped half a prerequisite list. Each test below names the one it guards.

No network.
"""

from __future__ import annotations

from etl import course_page


def page(*, typed=None, prose=None) -> str:
    """A course page carrying either field, both, or neither.

    `None` means the field is ABSENT; `""` means present and empty. Those are
    different answers and the probe treats them differently, so the helper has
    to express both — the first version used `""` for absent and could not
    build the empty-field case at all.
    """
    markup = "<div>"
    if typed is not None:
        markup += (f'<div class="field--name-field-prerequisite-courses">'
                   f'{typed}</div>')
    if prose is not None:
        markup += (f'<div class="field--name-field-pr">'
                   f'<div class="field__item">{prose}</div></div>')
    return markup + '<div class="field--name-field-credits">1</div></div>'


PUBLISHED = {"/maths/algebra-1", "/maths/algebra-2"}


def test_the_typed_field_is_found_and_the_prose_field_is_not_mistaken_for_it():
    """**The bug this probe had first.** `field--name-field-pr\\b` excludes
    `field-prerequisite-courses` — the word boundary stops at `pr` — so the
    first version read the prose field on every district and reported PWCS at
    0% linked. The repo's own figure for PWCS is 89%; a method that cannot
    reproduce the control measures nothing.
    """
    # ASSERTED, not argued. A review read the boundary the other way, and
    # the claim is load-bearing: it is why the prose pattern can be searched
    # over a whole page without stealing the typed field's match. After `pr`
    # comes `e`, so there is no word boundary and no match.
    # The field NAME is compared, not pattern-matched with a word boundary —
    # `pr` must not select `prerequisite-courses`, and a split comparison
    # says that plainly where a `\b` only implied it.
    only_typed = course_page.read_fields(
        '<div class="field--name-field-prerequisite-courses">'
        '<div class="field__item">x</div></div>')
    assert "pr" not in only_typed, "the prose lookup selected the typed field"
    assert "prerequisite-courses" in only_typed

    typed = course_page.classify(
        page(typed='<a href="/maths/algebra-1">Algebra I</a>'), PUBLISHED)
    assert typed["kind"] == "typed"
    assert typed["links"] == ["/maths/algebra-1"]
    assert typed["resolved"] == ["/maths/algebra-1"]

    prose = course_page.classify(page(prose="Audition by the band director"), PUBLISHED)
    assert prose["kind"] == "prose", (
        "a free-text prerequisite must not be counted as an edge")


def test_a_page_with_both_fields_counts_as_typed():
    """Counting it as prose would understate a district that answers the
    question in the form that resolves."""
    both = course_page.classify(
        page(typed='<a href="/maths/algebra-2">Algebra II</a>',
             prose="See your counsellor"), PUBLISHED)
    assert both["kind"] == "typed"


def test_a_link_to_a_page_the_catalogue_does_not_publish_is_not_resolved():
    """The resolution rate is the good half of the finding — "the problem is
    not broken links" — so a link that lands nowhere must not count."""
    found = course_page.classify(
        page(typed='<a href="/maths/algebra-1">A</a>'
                   '<a href="/gone/nowhere">B</a>'), PUBLISHED)
    # SORTED, because the links are deduplicated through a set — one course
    # linked twice counted twice in both numerators before.
    assert found["links"] == ["/gone/nowhere", "/maths/algebra-1"]
    assert found["resolved"] == ["/maths/algebra-1"]


def test_a_typed_field_holding_no_course_link_is_its_own_answer():
    """The CMS emits `/saml_login` inside the field on every page. A typed
    field whose only links are navigation states nothing traversable, so it
    must not count as typed — that would inflate every district including
    PWCS.

    But it is not "prose" and it is not "no field" either. Folding it into
    those reported a district that emits the field and fills it with
    navigation as one that does not use the field at all, which is a
    different fact. It gets its own kind.
    """
    found = course_page.classify(
        page(typed='<a href="/saml_login">Log in</a>',
             prose="Teacher recommendation"), PUBLISHED)
    assert found["kind"] == "typed but no course link"
    assert "Log in" in found["text"]


def test_an_absolute_link_to_the_same_host_resolves():
    """Matching only `/…` meant a district linking its prerequisites as
    `https://catalog.example.edu/x/y` was counted as having none — the
    finding this probe exists to measure, produced by not looking."""
    base = "https://catalog.example.edu"
    found = course_page.classify(
        page(typed=f'<a href="{base}/maths/algebra-1">Algebra I</a>'),
        PUBLISHED, base)
    assert found["kind"] == "typed"
    assert found["resolved"] == ["/maths/algebra-1"]


def test_a_link_to_another_host_is_not_a_course_and_not_a_failure():
    """An off-host link is not a prerequisite this catalogue publishes, and
    counting it as an unresolved link would understate resolution."""
    found = course_page.classify(
        page(typed='<a href="https://elsewhere.example/x/y">Elsewhere</a>'
                   '<a href="/maths/algebra-1">Algebra I</a>'),
        PUBLISHED, "https://catalog.example.edu")
    assert found["links"] == ["/maths/algebra-1"]
    assert found["resolved"] == ["/maths/algebra-1"]


def test_none_and_absent_are_different_answers():
    """A page with no field has not been asked; a page saying "None" has
    answered. Folding them together would move courses out of the
    denominator."""
    assert course_page.classify(page(), PUBLISHED)["kind"] == "no field"
    assert course_page.classify(page(prose="None"), PUBLISHED)["kind"] == "says none"
    assert course_page.classify(page(prose=""), PUBLISHED)["kind"] == "says none"


def test_only_two_segment_paths_count_as_courses():
    """The vendor's shape, and the rule `etl/pwcs_source.py` already uses.
    A different rule here would measure the rule rather than the district."""
    assert course_page.COURSE_PATH.match("/maths/algebra-1")
    assert not course_page.COURSE_PATH.match("/maths")
    assert not course_page.COURSE_PATH.match("/maths/algebra-1/unit-2")


def test_a_typed_field_at_the_very_end_of_a_page_is_still_found():
    """The lookahead required another `field--name-field-*` or a `</footer>`
    to follow, so a page whose prerequisite field is the LAST thing in the
    document matched nothing and was counted as stating none."""
    last = ('<div class="field--name-field-prerequisite-courses">'
            '<a href="/maths/algebra-1">Algebra I</a></div>')
    found = course_page.classify(last, PUBLISHED)
    assert found["kind"] == "typed", (
        "a typed field with nothing after it was read as absent")
    assert found["resolved"] == ["/maths/algebra-1"]


def test_a_field_with_no_item_does_not_reach_forward_to_another_field():
    """**The three prose examples were the entire evidence for this page's
    central claim**, and an unbounded `.*?` under `re.S` could have sourced
    them from a different field.

    A `field-pr` wrapper with no `field__item` of its own ran forward to the
    first one anywhere later in the document, so text belonging to
    `field-notes` was recorded as prose.
    """
    markup = ('<div class="field--name-field-pr"></div>'
              '<div class="field--name-field-notes">'
              '<div class="field__item">Wear safety goggles</div></div>')
    fields = course_page.read_fields(markup)
    assert "pr" in fields, "the field is present and must be found"
    assert "safety goggles" not in fields["pr"].readable(), (
        "the prose field reached forward into the next field")
    assert fields["pr"].bounded, "an empty field is still a bounded one"
    assert course_page.classify(markup, set())["kind"] == "says none"


def test_a_typed_field_at_the_end_does_not_swallow_the_page_footer():
    """It fell through to `\\Z` when the field is last and no lowercase
    `</footer` follows, so trailing NAVIGATION counted as prerequisite links.
    Navigation links to published courses always resolve — which is precisely
    the claim being made."""
    markup = ('<article><div class="field--name-field-prerequisite-courses">'
              '<div class="field__item">'
              '<a href="/maths/algebra-1">Algebra I</a></div></div></article>'
              '<nav><a href="/maths/algebra-2">Algebra II</a></nav>')
    found = course_page.classify(markup, PUBLISHED)
    assert found["links"] == ["/maths/algebra-1"], (
        f"navigation outside the article counted as a prerequisite: "
        f"{found['links']}")


def test_one_course_linked_twice_counts_once():
    """`links` was never deduplicated, so a course linked twice counted twice
    in BOTH numerators — inflating a rate whose whole claim is that the links
    land."""
    found = course_page.classify(
        page(typed='<a href="/maths/algebra-1">Algebra I</a>'
                   '<a href="/maths/algebra-1">Algebra I again</a>'),
        PUBLISHED)
    assert found["links"] == ["/maths/algebra-1"]
    assert found["resolved"] == ["/maths/algebra-1"]


def test_a_nested_field_does_not_truncate_the_block():
    """**Routine in a Drupal entity-reference teaser**, where each referenced
    node brings its own fields. Stopping at the first `field--name-field-`
    returned one link from a two-course prerequisite list — under-counting
    `links`, which is the denominator of the "every link resolves" claim, and
    turning a multi-prerequisite course into a single-prerequisite one."""
    markup = (
        '<div class="field field--name-field-prerequisite-courses">'
        '<div class="field__item"><a href="/math/algebra-1">Alg</a>'
        '<div class="field field--name-field-course-number">1234</div></div>'
        '<div class="field__item"><a href="/math/geometry">Geo</a></div>'
        '</div>')
    found = course_page.classify(markup, {"/math/algebra-1", "/math/geometry"})
    assert found["kind"] == "typed"
    assert found["links"] == ["/math/algebra-1", "/math/geometry"], (
        "a nested field ended the block early and dropped a prerequisite")


def test_a_sibling_field_still_ends_the_block():
    """The depth rule must not swing the other way — a field that ran into its
    neighbours is the bug this bound was added for."""
    markup = ('<div class="field--name-field-pr">'
              '<div class="field__item">Teacher recommendation</div></div>'
              '<div class="field--name-field-notes">'
              '<div class="field__item">Wear safety goggles</div></div>')
    block = course_page.read_fields(markup)["pr"].readable()
    assert "goggles" not in block, "the field ran into its neighbour"
    assert "recommendation" in block


# --------------------------------------------------------------------------
# The bounds this module documents, each tested against the case that put it
# here. The file's premise is "every bound exists because it was once
# absent" — these are the ones that had no test.


def test_a_denial_is_not_a_stated_prerequisite():
    """**The bug that reached the record.** The sentinel matched four exact
    strings, so a trailing full stop flipped the answer: `None.` counted as a
    stated prerequisite, on the district the headline comparison depends on.

    `course-prerequisites.md` records the same mistake as a past correction.
    """
    for denial in ("None", "None.", "NONE.", "none", "N/A", "n/a.", "NA",
                   "-", "–", "—", "Prerequisite: None", "Prerequisites: none.",
                   "nil", "Not applicable"):
        assert course_page.states_a_prerequisite(denial) is False, denial


def test_an_explicit_denial_written_as_a_sentence_is_not_one_either():
    """"NO PRIOR FILM EXPERIENCE REQUIRED." is in the record. It is not a
    prerequisite, and counting it as one is the same mistake as counting
    "None" — one clause longer."""
    for denial in ("Open to all Grade 11 students. NO PRIOR FILM EXPERIENCE "
                   "REQUIRED.",
                   "No prior experience required.",
                   "No previous coursework is necessary."):
        assert course_page.states_a_prerequisite(denial) is False, denial


def test_a_denial_that_names_courses_still_counts():
    """"None; after successful completion of 23132 or 23130" names courses.
    The pattern is anchored at both ends so it catches the bare forms only —
    over-tightening would lose real prerequisites, which is the same error in
    the other direction."""
    for real in ("None; after successful completion of 23132 or 23130",
                 "None required for students who passed Algebra I",
                 "Spanish I, or equivalent proficiency"):
        assert course_page.states_a_prerequisite(real) is True, real


def test_an_entity_is_decoded_before_the_field_is_judged_empty():
    """`&nbsp;` survived `plain()` as six literal characters and could never
    look empty, so a field holding only whitespace read as a statement."""
    for empty in ("&nbsp;", "&#160;", "&nbsp; &nbsp;", "  ", "&mdash;"):
        assert course_page.states_a_prerequisite(empty) is False, empty


def test_a_div_inside_a_comment_does_not_move_the_depth_count():
    """The depth counter is a token scan. A `<div` in a comment incremented
    it and never came back — and once the count is off, the field's own
    `</div>` reads as a child's and the block runs into its neighbour."""
    markup = ('<div class="field field--name-field-pr">'
              '<!-- <div> a comment -->'
              '<div class="field__item">See counsellor.</div></div>'
              '<div class="field field--name-field-notes">'
              '<div class="field__item">not eligible for credit</div></div>')
    found = course_page.classify(markup, set())
    assert found["kind"] == "prose"
    assert "not eligible" not in found["text"], (
        "the comment's <div> pushed the depth count and the block ran into "
        "its neighbour")


def test_a_div_inside_an_attribute_value_does_not_move_the_depth_count():
    """Same failure through an attribute. This one regenerated the exact
    string the page retracts as an artifact."""
    markup = ('<div class="field field--name-field-pr" data-x="<div>">'
              '<div class="field__item">See counsellor.</div></div>'
              '<div class="field field--name-field-notes">'
              '<div class="field__item">not eligible for credit</div></div>')
    found = course_page.classify(markup, set())
    assert found["text"] == "See counsellor.", (
        f"the attribute's angle brackets leaked into the block: "
        f"{found['text']!r}")


def test_an_apostrophe_in_prose_is_not_an_attribute_delimiter():
    """Masking every quoted run treated `Teacher's … student's` as a quoted
    span and blanked the text between them — and a `</div>` in that span would
    have gone with it.

    **There is no masking any more.** An apostrophe in character data is
    character data, because the parser knows which is which; the claim is kept
    as a test because it is the behaviour that was wrong, and it must not come
    back through whatever replaces the reader next.
    """
    markup = ('<div class="field field--name-field-prerequisite-courses">'
              '<div class="field__item">Teacher\'s note on student\'s work'
              '<a href="/m/a">Algebra</a></div></div>')
    found = course_page.classify(markup, {"/m/a"})
    assert found["kind"] == "typed", found
    assert found["links"] == ["/m/a"], (
        "prose between two apostrophes swallowed the link")


def test_a_field_name_inside_a_script_body_is_not_a_field():
    """A `field--name-field-pr` in a `<script>` blob is text. Selecting it
    would bound the block from a position no element opens at."""
    markup = ('<div class="field field--name-field-prerequisite-courses">'
              '<script>var x = "field--name-field-pr";</script>'
              '<div class="field__item"><a href="/m/a">A</a></div></div>')
    found = course_page.classify(markup, {"/m/a"})
    assert found["kind"] == "typed"
    assert found["links"] == ["/m/a"]


def test_a_comment_leaves_no_stray_marker_in_the_text():
    """`<[^>]+>` stops at the first `>`, so `<!-- <div> -->` left a stray
    `-->` — which then read as prose content and, in a prose field, as a
    stated prerequisite."""
    assert "-->" not in course_page.plain("<!-- <div> -->text")
    assert course_page.plain("<!-- x --> Real text") == "Real text"


def test_an_unclosed_div_cannot_swallow_the_rest_of_the_page():
    """Depth never goes negative on malformed markup, so without a ceiling
    the block would run to the end of the document. MAX_NESTING is the
    backstop for when the heuristic is wrong."""
    markup = ('<div class="field field--name-field-pr">'
              '<div class="field__item">See counsellor.'
              + "<div>" * (course_page.MAX_NESTING + 10) +
              '</div></div>'
              '<div class="field field--name-field-notes">'
              '<div class="field__item">not eligible</div></div>')
    found = course_page.classify(markup, set())
    assert "not eligible" not in found.get("text", ""), (
        "an unclosed <div> let the block swallow the next field")


def test_a_link_carrying_a_query_string_is_still_a_link():
    """`[^"#?]+` matched nothing at all for `href="/maths/algebra-1?from=x"`,
    so a prerequisite with a query string was invisible — and `links` is the
    denominator of the "every link resolves" claim."""
    for href, expected in (('/maths/algebra-1?from=x', "/maths/algebra-1"),
                           ('/maths/algebra-1#top', "/maths/algebra-1"),
                           ('/maths/algebra-1', "/maths/algebra-1")):
        found = course_page.classify(
            page(typed=f'<a href="{href}">A</a>'), PUBLISHED)
        assert found["links"] == [expected], href

"""Reading one named field out of the catalogue's markup.

Split from `tests/test_probe_pwcs.py` at the 500-line review limit, alongside
the `etl/pwcs_fields.py` it tests. Split by SUBJECT: that file is the probe —
fetching, classifying, resolving — and this is the small thing underneath.

Every test here is a template SHAPE that was wrong once, and the module's
premise is that these keep being wrong in ways a reader cannot see:

- the capture ran past the field into the next one's markup — 87 of 791
  descriptions carried `<div class="field...` as text, and the ENGINE caught
  it, not the parser
- `field__item` matched the `field__items` container, so the wrapper matched
  first and came out right by coincidence of ordering
- a field last on the page swallowed the footer, which is the failure
  `PREREQ_BLOCK` has carried a `<footer` terminator for since it was written
- a `field__label` inside the wrapper was read as content
"""

from __future__ import annotations

from etl import probe_pwcs as probe


# --------------------------------------------------------------------------
# The two fields the catalogue publishes and no loader read — edtech-kg#137.
# --------------------------------------------------------------------------

COURSE_PAGE = """<html><h1>Landscaping 1</h1>
<div class="field field--name-field-grades field--type-list-string">
  <div class="field__label">Grades</div>
  <div class="field__items">
    <div class="field__item">10,</div>
    <div class="field__item">11,</div>
    <div class="field__item">12</div>
  </div>
</div>
<div class="field field--name-field-description field--type-text-long field__item">
  <p>Landscaping offers skilled workers &amp; satisfying careers.</p>
</div>
<span class="field field--name-field-credits"><span class="field__item">1</span></span>
</html>"""


def test_a_course_page_yields_its_description_and_grade_levels():
    """Both are on the page and neither was read, so Q9 and Q14 returned null
    against a loaded district — the failure the schema's own block describes."""
    found = probe.parse_course(COURSE_PAGE, "https://catalog.pwcs.edu/x/y")
    assert found["grade_levels"] == ["10", "11", "12"], (
        "the catalogue writes the separator INSIDE the value — `10,` `11,` "
        "`12` — so a trailing comma survives unless it is stripped")
    assert found["description"] == (
        "Landscaping offers skilled workers & satisfying careers."), found["description"]


def test_a_field_stops_at_the_next_one_and_does_not_swallow_its_markup():
    """The stop condition, and the reason it is a SIBLING WRAPPER rather than
    the next `field--name-field-`.

    The looser stop ran past the description into whatever followed, and
    `text_of` does not strip a tag it is handed mid-attribute — so 87 of 791
    descriptions arrived carrying `<div class="field...` as text. The ENGINE
    caught it, not the parser: `lit()` refuses a string holding both quote
    characters, and those were the only descriptions holding a double quote.
    """
    found = probe.parse_course(COURSE_PAGE, "https://catalog.pwcs.edu/x/y")
    for leak in ("<div", "<span", "class=", "field__item", "Credits", "1"):
        if leak in ("1",):
            assert not found["description"].endswith("1"), "the credits field leaked in"
            continue
        assert leak not in found["description"], f"{leak!r} leaked into the description"
    assert "Grades" not in found["description"]


def test_a_page_with_neither_field_reports_absence_not_emptiness():
    """Absence is real here and common — 8 of 791 courses publish no
    description and 10 publish no grades. `None` and `[]` say so; `""` would
    make `c.description IS NOT NULL` true for every course."""
    found = probe.parse_course("<html><h1>Bare Course</h1></html>", "u")
    assert found["description"] is None
    assert found["grade_levels"] == []


def test_the_items_container_is_not_read_as_an_item():
    """`field__item` also matches inside `class="field__items"`.

    `[^>]*` absorbed the `s"`, so the CONTAINER matched first and its capture
    ran to the first `</div>` inside it. On the current template that is the
    first real item, so the answer came out right by coincidence of ordering.
    Move the label inside `field__items` — which Drupal templates do — and
    `Grades` is emitted as a grade level. Verified before the fix.
    """
    label_inside = """<html><h1>C</h1>
<div class="field field--name-field-grades">
  <div class="field__items">
    <div class="field__label">Grades</div>
    <div class="field__item">10,</div>
    <div class="field__item">11</div>
  </div>
</div></html>"""
    label_outside = label_inside.replace(
        '<div class="field__items">\n    <div class="field__label">Grades</div>',
        '<div class="field__label">Grades</div>\n  <div class="field__items">')
    for markup, where in ((label_inside, "inside"), (label_outside, "outside")):
        found = probe.parse_course(markup, "u")["grade_levels"]
        assert found == ["10", "11"], f"label {where} the container gave {found}"


def test_a_field_that_is_last_on_the_page_does_not_swallow_the_footer():
    """`PREREQ_BLOCK` has carried `<footer` since it was written, and its
    comment says why in as many words: reading a field out of flattened page
    text "would run it into the footer and turn the school's street address
    into a course name."

    The field readers did not. A description that is the LAST field, on a page
    with no `</article>`, fell through to `$` and took the address and the nav
    with it. Every earlier test here placed a sibling field after the
    description, so none of them reached the case.
    """
    markup = ("<html><h1>C</h1>\n"
              '<div class="field field--name-field-description field__item">'
              "<p>Real text.</p></div>\n"
              "<footer><div>Prince William County Schools, 14715 Bristow Road,"
              " Manassas VA 20112</div><nav>Home About</nav></footer></html>")
    found = probe.parse_course(markup, "u")["description"]
    assert found == "Real text.", found


def test_a_field_label_is_stripped_rather_than_ending_the_field():
    """The labelled shape Drupal also emits.

    `field\\b` does not match `field__label` — `_` is a word character, so
    there is no boundary — and the label sits INSIDE the wrapper, so the
    description came out as "Description Real text." Ending the capture at the
    label instead returns nothing at all, which is worse, so it is removed from
    the capture. `field_items` already defends against label placement; this is
    the same variation on the other reader.
    """
    markup = ("<html><h1>C</h1>\n"
              '<div class="field field--name-field-description">\n'
              '  <div class="field__label">Description</div>\n'
              '  <div class="field__item"><p>Real text.</p></div>\n'
              "</div>\n"
              '<span class="field field--name-field-credits">'
              '<span class="field__item">1</span></span></html>')
    found = probe.parse_course(markup, "u")["description"]
    assert found == "Real text.", found

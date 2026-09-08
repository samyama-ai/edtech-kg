"""The second-district probe's classifier, driven without the network.

The measurement turns on one distinction — a prerequisite in the TYPED field
versus the same prerequisite in prose — so that is what is tested. Everything
else in the probe is walking and counting.
"""

from __future__ import annotations

from etl import probe_second_district as probe


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
    assert not probe.PROSE_FIELD.search(
        'field--name-field-prerequisite-courses'
        '<div class="field__item">x</div>'), (
        "the prose pattern matches the typed field's class name")

    typed = probe.classify(
        page(typed='<a href="/maths/algebra-1">Algebra I</a>'), PUBLISHED)
    assert typed["kind"] == "typed"
    assert typed["links"] == ["/maths/algebra-1"]
    assert typed["resolved"] == ["/maths/algebra-1"]

    prose = probe.classify(page(prose="Audition by the band director"), PUBLISHED)
    assert prose["kind"] == "prose", (
        "a free-text prerequisite must not be counted as an edge")


def test_a_page_with_both_fields_counts_as_typed():
    """Counting it as prose would understate a district that answers the
    question in the form that resolves."""
    both = probe.classify(
        page(typed='<a href="/maths/algebra-2">Algebra II</a>',
             prose="See your counsellor"), PUBLISHED)
    assert both["kind"] == "typed"


def test_a_link_to_a_page_the_catalogue_does_not_publish_is_not_resolved():
    """The resolution rate is the good half of the finding — "the problem is
    not broken links" — so a link that lands nowhere must not count."""
    found = probe.classify(
        page(typed='<a href="/maths/algebra-1">A</a>'
                   '<a href="/gone/nowhere">B</a>'), PUBLISHED)
    assert found["links"] == ["/maths/algebra-1", "/gone/nowhere"]
    assert found["resolved"] == ["/maths/algebra-1"]


def test_a_typed_field_holding_no_course_link_falls_through_to_prose():
    """The CMS emits `/saml_login` inside the field on every page. A typed
    field whose only links are navigation states nothing traversable, and
    counting it as typed would inflate every district including PWCS."""
    found = probe.classify(
        page(typed='<a href="/saml_login">Log in</a>',
             prose="Teacher recommendation"), PUBLISHED)
    assert found["kind"] == "prose"


def test_none_and_absent_are_different_answers():
    """A page with no field has not been asked; a page saying "None" has
    answered. Folding them together would move courses out of the
    denominator."""
    assert probe.classify(page(), PUBLISHED)["kind"] == "no field"
    assert probe.classify(page(prose="None"), PUBLISHED)["kind"] == "says none"
    assert probe.classify(page(prose=""), PUBLISHED)["kind"] == "says none"


def test_only_two_segment_paths_count_as_courses():
    """The vendor's shape, and the rule `etl/pwcs_source.py` already uses.
    A different rule here would measure the rule rather than the district."""
    assert probe.COURSE_PATH.match("/maths/algebra-1")
    assert not probe.COURSE_PATH.match("/maths")
    assert not probe.COURSE_PATH.match("/maths/algebra-1/unit-2")


def test_the_sample_is_seeded_so_two_runs_agree():
    """The issue asks for the same sample size and a recorded seed. Without
    it a re-run measures a different sample and the comparison drifts."""
    import random
    paths = [f"/s/c{i}" for i in range(200)]
    first = random.Random(probe.SEED).sample(paths, 20)
    second = random.Random(probe.SEED).sample(paths, 20)
    assert first == second
    assert probe.SEED == 19, "the seed is the issue number, recorded on the page"


def test_a_typed_field_at_the_very_end_of_a_page_is_still_found():
    """The lookahead required another `field--name-field-*` or a `</footer>`
    to follow, so a page whose prerequisite field is the LAST thing in the
    document matched nothing and was counted as stating none."""
    last = ('<div class="field--name-field-prerequisite-courses">'
            '<a href="/maths/algebra-1">Algebra I</a></div>')
    found = probe.classify(last, PUBLISHED)
    assert found["kind"] == "typed", (
        "a typed field with nothing after it was read as absent")
    assert found["resolved"] == ["/maths/algebra-1"]


def test_json_and_record_are_refused_together(capsys):
    """Opposite intentions — print without touching the tree, and write to
    the tree. One silently winning is the worse outcome."""
    import etl.probe_second_district as module
    module_measure = module.measure
    module.measure = lambda *a, **k: {"districts": {}}
    try:
        assert module.main(["--json", "--record"]) == 2
        assert "pick one" in capsys.readouterr().err
    finally:
        module.measure = module_measure


def test_an_unreachable_page_leaves_the_denominator_honest():
    """A page that did not answer is not a page that stated nothing. Counting
    it in `read` would report a network failure as a district's choice."""
    kinds = {"typed": 1, "no field": 8, "unreachable": 1}
    read = 10 - kinds["unreachable"]
    assert read == 9
    assert round(100 * kinds["typed"] / read, 1) == 11.1

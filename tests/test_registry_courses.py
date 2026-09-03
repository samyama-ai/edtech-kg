"""The one classifier both the sample and the #58 sweep call.

`etl/registry_courses.py` was extracted so that the full sweep of 47,862
courses and the 600-course sample cannot answer the same question differently.
That is the property worth testing, so the last test here drives the extracted
function and the probe that calls it over the same records and requires the
same answer.

The rest cover the distinctions the counting rests on — STATES, RESOLVES and
EMPTY — because every one of them has been got wrong at least once in this
repo's history, and each wrong version moved a figure a document quotes.
"""

import pytest

from etl import probe_registry as probe
from etl import registry_courses as courses
from tests.registry_stubs import course, paged, prereq


def node(**fields):
    return {"@type": "ceterms:Course", **fields}


# --- text(): the CTDL value shapes ------------------------------------------

@pytest.mark.parametrize("value, want", [
    ("plain", "plain"),
    ({"en-US": "us"}, "us"),
    ({"en": "en"}, "en"),
    ({"fr": "fr"}, "fr"),
    # The list-valued map that used to read as empty, silently turning a stated
    # prerequisite into a course with none.
    ([{"en-US": "one"}, {"en-US": "two"}], "one two"),
    (None, ""),
    (7, "7"),
    (True, "True"),
])
def test_text_reads_every_shape(value, want):
    assert courses.text(value) == want


@pytest.mark.parametrize("value, want", [
    (None, []),
    ([1, 2], [1, 2]),
    ({"a": 1}, [{"a": 1}]),     # the single-condition form, once an AttributeError
    ("s", ["s"]),
])
def test_as_list_accepts_the_bare_form(value, want):
    assert courses.as_list(value) == want


# --- is_reference(): pointer or prose ---------------------------------------

@pytest.mark.parametrize("value, expected", [
    ({"@id": "https://x.test/c"}, True),
    ({"@id": ""}, False),
    ({}, False),
    ("https://x.test/c", True),
    ("ce-1234", True),
    ("CE-1234", True),
    # The behaviour the whole finding is about: free text in the target field.
    ("PSYC101", False),
    ("MATH 113, MATH 114 (Grade of C or better)", False),
    ("", False),
    ("   ", False),
    (None, False),
    (7, False),
])
def test_is_reference_is_the_same_strict_test_everywhere(value, expected):
    assert courses.is_reference(value) is expected


# --- classify(): the three states -------------------------------------------

def test_a_typed_edge_pointing_somewhere_states_and_resolves():
    said = courses.classify(node(**{
        "ceterms:prerequisite": [{"@id": "https://x.test/other"}]}))
    assert (said["states"], said["resolves"]) == (True, True)
    assert said["uses_typed_edge"] is True


def test_a_typed_edge_holding_prose_states_without_resolving():
    """Present but empty is not a reference. Counting the key alone would
    credit the Registry with resolvable edges it does not publish."""
    said = courses.classify(node(**{"ceterms:prerequisite": ["PSYC101"]}))
    assert (said["states"], said["resolves"]) == (True, False)
    assert said["uses_typed_edge"] is True


def test_a_prose_condition_states_without_resolving():
    said = courses.classify(node(**prereq("PSYC101")))
    assert (said["states"], said["resolves"]) == (True, False)
    assert said["prose"] == ["PSYC101"]
    assert said["uses_typed_edge"] is False


@pytest.mark.parametrize("described", ["None", "none", "N/A", "na", "-", ""])
def test_a_condition_saying_there_are_none_is_empty_not_stated(described):
    """"Prerequisites: None" is a statement that there are none. Counting it
    as a stated prerequisite inflates the rate the documents quote."""
    said = courses.classify(node(**prereq(described)))
    assert (said["states"], said["empty"]) == (False, True)


def test_a_course_with_two_prerequisite_blocks_counts_once():
    """Per COURSE, not per condition — a course carrying "Prerequisites" and
    "Prerequisite (recommended)" used to increment the count twice, so the
    figure counted profiles while the documents read it as a share of courses.
    """
    said = courses.classify(node(**{"ceterms:requires": [
        {"ceterms:name": {"en-US": "Prerequisites"},
         "ceterms:description": {"en-US": "PSYC101"}},
        {"ceterms:name": {"en-US": "Prerequisite (recommended)"},
         "ceterms:description": {"en-US": "MATH113"}}]}))
    assert said["states"] is True and said["resolves"] is False
    assert len(said["prose"]) == 2, "both are collected; the COURSE counts once"


def test_a_stated_course_is_never_also_empty():
    """`states` and `empty` are exclusive. A course with one blank condition
    and one real one states a prerequisite; counting it in both buckets makes
    the two figures sum past the course count."""
    said = courses.classify(node(**{"ceterms:requires": [
        {"ceterms:name": {"en-US": "Prerequisites"},
         "ceterms:description": {"en-US": "None"}},
        {"ceterms:name": {"en-US": "Prerequisites"},
         "ceterms:description": {"en-US": "PSYC101"}}]}))
    assert (said["states"], said["empty"]) == (True, False)


def test_a_condition_that_is_not_about_prerequisites_is_ignored():
    said = courses.classify(node(**{"ceterms:requires": [
        {"ceterms:name": {"en-US": "Admission requirements"},
         "ceterms:description": {"en-US": "A high school diploma"}}]}))
    assert (said["states"], said["empty"]) == (False, False)


@pytest.mark.parametrize("field", list(courses.RESOLVABLE))
def test_a_condition_targeting_something_resolvable_resolves(field):
    said = courses.classify(node(**{"ceterms:requires": [
        {"ceterms:name": {"en-US": "Prerequisites"},
         field: [{"@id": "https://x.test/other"}]}]}))
    assert (said["states"], said["resolves"]) == (True, True)


@pytest.mark.parametrize("field", list(courses.RESOLVABLE))
def test_free_text_in_a_target_field_does_not_resolve(field):
    """The exact case `is_reference` was tightened for."""
    said = courses.classify(node(**{"ceterms:requires": [
        {"ceterms:name": {"en-US": "Prerequisites"}, field: ["PSYC101"]}]}))
    assert said["resolves"] is False


def test_a_competency_target_is_not_a_resolvable_prerequisite():
    """A competency says what you must be able to DO, not which course you must
    have taken. It is deliberately not in RESOLVABLE."""
    assert "ceterms:targetCompetency" not in courses.RESOLVABLE
    said = courses.classify(node(**{"ceterms:requires": [
        {"ceterms:name": {"en-US": "Prerequisites"},
         "ceterms:targetCompetency": [{"@id": "https://x.test/comp"}]}]}))
    assert said["resolves"] is False


# --- courses_in(): envelopes are not courses --------------------------------

def test_every_course_in_one_graph_is_returned():
    """One `@graph` can carry several Course nodes, which is why counting
    envelopes and counting courses are different numbers."""
    envelope = {"decoded_resource": {"@graph": [
        {"@type": "ceterms:PathwayComponent"},
        {"@type": "ceterms:Course", "ceterms:ctid": "a"},
        {"@type": "Course", "ceterms:ctid": "b"}]}}
    assert [n["ceterms:ctid"] for n in courses.courses_in(envelope)] == ["a", "b"]


def test_a_record_with_no_graph_falls_back_to_the_resource():
    assert len(courses.courses_in(course(**{"ceterms:ctid": "a"}))) == 1


@pytest.mark.parametrize("bad", [None, "text", 7, []])
def test_a_malformed_envelope_yields_no_courses(bad):
    assert courses.courses_in(bad) == []


# --- the invariant this extraction exists for -------------------------------

def test_the_sample_probe_and_the_classifier_agree(monkeypatch):
    """The property #58 rests on.

    The full sweep replaces `course_prerequisites`'s figure. If the probe
    counted through its own copy of this logic, the two could diverge and the
    divergence would look like a finding. Here the probe walks stubbed records
    and its totals are reconciled against `classify` applied to the same nodes.
    """
    records = [
        course(**{"ceterms:prerequisite": [{"@id": "https://x.test/a"}]}),
        course(**prereq("PSYC101")),
        course(**prereq("None")),
        course(**{"ceterms:requires": [
            {"ceterms:name": {"en-US": "Prerequisites"},
             "ceterms:targetLearningOpportunity": [{"@id": "https://x.test/b"}]}]}),
        course(),
    ]
    paged(monkeypatch, {1: records}, x_total=len(records))
    got = probe.course_prerequisites(sample=len(records))

    said = [courses.classify(n) for r in records for n in courses.courses_in(r)]
    assert got["courses_sampled"] == len(said)
    assert got["stating_a_prerequisite"] == sum(s["states"] for s in said)
    assert got["resolvable"] == sum(s["resolves"] for s in said)
    assert got["stated_but_empty"] == sum(s["empty"] for s in said)
    assert got["free_text_only"] == (got["stating_a_prerequisite"]
                                     - got["resolvable"])

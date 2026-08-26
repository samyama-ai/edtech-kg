"""How the Registry's published courses are sampled, and what resolves — #53.

The network is stubbed throughout. Under test: the sampling method the
review of #57 asked to be made explicit, the shapes CTDL actually
publishes, and the refusals.
"""

import json
import urllib.error
import urllib.parse

import pytest

from etl import probe_registry as probe
from etl import registry_read as read
from tests.registry_stubs import course, headers_stub, paged, prereq, stub


def test_the_publisher_spread_is_reported(monkeypatch):
    """A verdict drawn from a sample that turns out to be three publishers is a
    fact about those three."""
    stub(monkeypatch, json.dumps([
        {"published_by": "org/a", "decoded_resource": {"@type": "ceterms:Course"}},
        {"published_by": "org/a", "decoded_resource": {"@type": "ceterms:Course"}},
        {"published_by": "org/b", "decoded_resource": {"@type": "ceterms:Course"}},
    ]).encode(), x_total=150)
    assert probe.course_prerequisites(sample=50)["distinct_publishers"] == 2


def test_a_free_text_condition_is_not_counted_as_resolvable(monkeypatch):
    """"PSYC101" is a string. Resolving it means guessing which catalogue it
    belongs to, so it is counted as stated-but-not-resolvable."""
    body = json.dumps([course(**{"ceterms:requires": [
        {"ceterms:name": {"en-US": "Prerequisites"},
         "ceterms:description": {"en-US": "PSYC101"}}]})]).encode()
    stub(monkeypatch, body)
    r = probe.course_prerequisites(sample=50)
    assert r["stating_a_prerequisite"] == 1
    assert r["resolvable"] == 0
    assert r["free_text_only"] == 1
    assert r["examples"] == ["PSYC101"]


def test_a_targeted_condition_counts_as_resolvable(monkeypatch):
    body = json.dumps([course(**{"ceterms:requires": [
        {"ceterms:name": {"en-US": "Prerequisites"},
         "ceterms:targetLearningOpportunity": [{"@id": "https://x/course/1"}]}]})]).encode()
    stub(monkeypatch, body)
    r = probe.course_prerequisites(sample=50)
    assert (r["stating_a_prerequisite"], r["resolvable"], r["free_text_only"]) == (1, 1, 0)


def test_the_typed_property_counts_as_resolvable(monkeypatch):
    stub(monkeypatch, json.dumps([course(**{
        "ceterms:prerequisite": [{"@id": "https://x/course/2"}]})]).encode())
    r = probe.course_prerequisites(sample=50)
    assert (r["stating_a_prerequisite"], r["resolvable"]) == (1, 1)


def test_a_condition_that_is_not_a_prerequisite_is_not_counted(monkeypatch):
    """Courses carry `ceterms:requires` for co-requisites, residency and fees.
    Counting all of them would overstate the rate."""
    stub(monkeypatch, json.dumps([course(**{"ceterms:requires": [
        {"ceterms:name": {"en-US": "Residency requirement"},
         "ceterms:description": {"en-US": "Must live in-district"}}]})]).encode())
    r = probe.course_prerequisites(sample=50)
    assert r["courses_sampled"] == 1 and r["stating_a_prerequisite"] == 0


def test_non_course_records_are_not_counted_in_the_denominator(monkeypatch):
    stub(monkeypatch, json.dumps([
        course(), {"decoded_resource": {"@type": "ceterms:Credential"}}]).encode())
    assert probe.course_prerequisites(sample=50)["courses_sampled"] == 1


def test_zero_courses_is_refused_rather_than_reported_as_a_rate(monkeypatch):
    """A rate over an empty sample is not a finding — the same refusal the
    education and state-course probes make."""
    stub(monkeypatch, b"[]")
    with pytest.raises(ValueError, match="refusing"):
        probe.course_prerequisites(sample=50)


def test_every_sampled_page_is_accumulated(monkeypatch):
    """Twelve pages must contribute twelve pages' worth. A stub that ignores the
    page number cannot tell that apart from reading page 1 twelve times."""
    pages, _ = read.sample_pages(600, 47861)
    paged(monkeypatch, {p: [course(**prereq()), course()] for p in pages})
    r = probe.course_prerequisites(sample=600)
    assert r["courses_sampled"] == 2 * len(pages) == 24
    assert r["stating_a_prerequisite"] == len(pages) == 12


def test_a_page_that_returns_nothing_does_not_abort_the_walk(monkeypatch):
    pages, _ = read.sample_pages(600, 47861)
    bodies = {p: [course(**prereq())] for p in pages}
    bodies[pages[3]] = []
    paged(monkeypatch, bodies)
    assert probe.course_prerequisites(sample=600)["courses_sampled"] == len(pages) - 1


def test_a_graph_wrapped_envelope_has_every_course_counted(monkeypatch):
    """Registry envelopes frequently carry a @graph of many nodes rather than a
    single resource. Only the Course nodes count, and all of them do."""
    paged(monkeypatch, {1: [{"decoded_resource": {"@graph": [
        {"@type": "ceterms:Course", **prereq()},
        {"@type": "ceterms:Course"},
        {"@type": "ceterms:CredentialOrganization"},
    ]}}]})
    r = probe.course_prerequisites(sample=50)
    assert r["courses_sampled"] == 2
    assert r["stating_a_prerequisite"] == 1


def test_a_single_condition_object_is_read_like_a_list(monkeypatch):
    """`ceterms:requires` is a list with several conditions and a bare object
    with one. Assuming the list raised AttributeError on real records."""
    paged(monkeypatch, {1: [course(**{"ceterms:requires": {
        "ceterms:name": {"en-US": "Prerequisites"},
        "ceterms:description": {"en-US": "PSYC101"}}})]})
    assert probe.course_prerequisites(sample=50)["stating_a_prerequisite"] == 1


def test_a_list_valued_language_map_is_not_read_as_absent(monkeypatch):
    """CTDL language maps are a dict, a string, or a list of either. The list
    form used to read as empty, silently turning a stated prerequisite into a
    course with none — an undercount that looks like a finding."""
    paged(monkeypatch, {1: [course(**{"ceterms:requires": [{
        "ceterms:name": [{"en-US": "Prerequisites"}],
        "ceterms:description": ["PSYC101", "and MATH 100"]}]})]})
    r = probe.course_prerequisites(sample=50)
    assert r["stating_a_prerequisite"] == 1
    assert r["examples"] and "PSYC101" in r["examples"][0]


def test_a_non_dict_condition_is_skipped_not_crashed(monkeypatch):
    paged(monkeypatch, {1: [course(**{"ceterms:requires": ["a bare string"]})]})
    assert probe.course_prerequisites(sample=50)["stating_a_prerequisite"] == 0


def test_at_most_six_examples_are_kept(monkeypatch):
    """The examples exist to let a reader check the "free text" claim, not to
    reproduce the sample."""
    paged(monkeypatch, {1: [course(**prereq(f"COURSE{i}")) for i in range(20)]})
    kept = probe.course_prerequisites(sample=50)["examples"]
    assert len(kept) == probe.MAX_EXAMPLES


def test_a_long_example_is_truncated(monkeypatch):
    paged(monkeypatch, {1: [course(**prereq("X" * 300))]})
    example = probe.course_prerequisites(sample=50)["examples"][0]
    assert len(example) == probe.EXAMPLE_CHARS


def test_asking_for_fewer_than_one_page_samples_that_many(monkeypatch):
    """`--courses 20` used to read a full page of 50 and report "20 sampled"."""
    paged(monkeypatch, {1: [course() for _ in range(50)]})
    assert probe.course_prerequisites(sample=20)["courses_sampled"] == 20


def test_a_graph_of_many_courses_cannot_push_past_the_cap(monkeypatch):
    """The cap was checked once per envelope. One @graph carrying 40 Course
    nodes then sampled 40 when 10 were asked for."""
    paged(monkeypatch, {1: [{"decoded_resource": {"@graph": [
        {"@type": "ceterms:Course"} for _ in range(40)]}}]})
    assert probe.course_prerequisites(sample=10)["courses_sampled"] == 10


def test_reaching_the_cap_stops_fetching_further_pages(monkeypatch):
    """`break` only left the inner loop, so every remaining page was still
    downloaded and discarded.

    A page of 50 envelopes normally yields 50 courses, so the cap lands exactly
    at the end of the last page and nothing is skipped. It bites early only when
    envelopes carry multi-node @graphs — which is the common shape here.
    """
    fetched = []
    class R:
        headers = {"x-total": "47861"}
        def __init__(self, body): self._b = body
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return self._b
    def urlopen(request, *a, **k):
        query = urllib.parse.parse_qs(urllib.parse.urlparse(request.full_url).query)
        if "page" in query:
            fetched.append(int(query["page"][0]))
        # 50 envelopes, each a @graph of 20 courses = 1,000 courses per page.
        return R(json.dumps([{"decoded_resource": {"@graph": [
            {"@type": "ceterms:Course"} for _ in range(20)]}} for _ in range(50)]).encode())
    monkeypatch.setattr(read.urllib.request, "urlopen", urlopen)
    r = probe.course_prerequisites(sample=600)
    assert r["courses_sampled"] == 600
    assert len(fetched) == 1, f"cap reached on page 1 but fetched pages {fetched}"


def test_a_corrupt_body_is_malformed_not_refused(monkeypatch):
    """json.JSONDecodeError subclasses ValueError, so a truncated response used
    to exit 1 under "refused" — the category for figures we decline to report,
    not for a broken source."""
    class R:
        headers = {"x-total": "47861"}
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'[{"decoded_resource": '
    monkeypatch.setattr(read.urllib.request, "urlopen", lambda *a, **k: R())
    with pytest.raises(read.MalformedSource, match="did not parse"):
        probe.course_prerequisites(sample=50)


def test_an_empty_typed_prerequisite_reads_as_absent(monkeypatch):
    """The key alone used to count. `ceterms:prerequisite: []` is the key with
    nothing in it, which is the same fact as not having the key."""
    paged(monkeypatch, {1: [course(**{"ceterms:prerequisite": []})]})
    r = probe.course_prerequisites(sample=50)
    assert (r["stating_a_prerequisite"], r["resolvable"]) == (0, 0)


def test_a_typed_prerequisite_holding_nothing_usable_is_stated_not_resolved(monkeypatch):
    """A non-empty list whose entries carry no reference. Stated, because the
    publisher meant to say something; not resolvable, because it does not
    resolve — which is the distinction this whole page rests on."""
    paged(monkeypatch, {1: [course(**{"ceterms:prerequisite": [{}, ""]})]})
    r = probe.course_prerequisites(sample=50)
    assert (r["stating_a_prerequisite"], r["resolvable"]) == (1, 0)


def test_a_populated_typed_prerequisite_still_counts(monkeypatch):
    paged(monkeypatch, {1: [course(**{"ceterms:prerequisite": [{"@id": "https://x/c/1"}]})]})
    assert probe.course_prerequisites(sample=50)["resolvable"] == 1


def test_a_community_that_does_not_answer_is_named(monkeypatch):
    """`unattributed` is global minus the readable communities. A community
    that errored used to vanish into that remainder and read as the gated
    community's records."""
    headers_stub(monkeypatch, {"/search": 100, "/ce-registry/search": 90,
                               "/fdoe/search": None, "/mytxlibrary/search": 0,
                               "/learning-registry/search": 0,
                               "/chaffeycollege/search": 401})
    r = probe.registry_totals()
    assert r["failed_communities"] == ["fdoe"]
    assert r["secured_communities"] == ["chaffeycollege"]


def test_a_non_string_language_value_does_not_crash(monkeypatch):
    """A CTDL value that is a number reached `.lower()` as-is."""
    paged(monkeypatch, {1: [course(**{"ceterms:requires": [
        {"ceterms:name": 101, "ceterms:description": {"en-US": "PSYC101"}}]})]})
    assert probe.course_prerequisites(sample=50)["stating_a_prerequisite"] == 0


def test_a_search_page_that_is_not_a_list_is_malformed(monkeypatch):
    """An error object served with a 200 would be iterated as if it were
    envelopes, yielding its keys."""
    class R:
        headers = {"x-total": "47861"}
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"error": "rate limited"}'
    monkeypatch.setattr(read.urllib.request, "urlopen", lambda *a, **k: R())
    with pytest.raises(read.MalformedSource, match="not a list"):
        probe.course_prerequisites(sample=50)


def test_the_paged_stub_serves_the_total_it_is_given(monkeypatch):
    """`paged` took an x_total no test ever varied, so the population branch it
    feeds was never exercised with anything but the default."""
    paged(monkeypatch, {1: [course()]}, x_total=120)
    assert probe.course_prerequisites(sample=600)["population"] == 120


def test_an_empty_target_is_not_a_resolvable_reference(monkeypatch):
    """`k in condition` counted a present-but-empty `ceterms:targetCredential`
    as resolvable, contradicting the truthiness test the typed branch one level
    above already applied — and inflating the one number this module produces."""
    paged(monkeypatch, {1: [course(**{"ceterms:requires": [
        {"ceterms:name": {"en-US": "Prerequisites"},
         "ceterms:targetCredential": [],
         "ceterms:description": {"en-US": "PSYC101"}}]})]})
    r = probe.course_prerequisites(sample=50)
    assert (r["stating_a_prerequisite"], r["resolvable"]) == (1, 0)


def test_a_populated_target_still_resolves(monkeypatch):
    paged(monkeypatch, {1: [course(**{"ceterms:requires": [
        {"ceterms:name": {"en-US": "Prerequisites"},
         "ceterms:targetCredential": [{"@id": "https://x/c/1"}]}]})]})
    assert probe.course_prerequisites(sample=50)["resolvable"] == 1


def test_a_non_dict_envelope_is_skipped_not_crashed(monkeypatch):
    """The list shape is validated; its elements were not. A bare string in the
    array raised AttributeError on `.get`."""
    paged(monkeypatch, {1: ["a bare string", course(), None]})
    assert probe.course_prerequisites(sample=50)["courses_sampled"] == 1


def test_two_matching_conditions_on_one_course_count_once(monkeypatch):
    """The loop had no per-course flag, so a course carrying "Prerequisites"
    and "Prerequisite (recommended)" incremented the count twice — the figure
    counted condition profiles while both documents read it as a share of
    courses."""
    paged(monkeypatch, {1: [course(**{"ceterms:requires": [
        {"ceterms:name": {"en-US": "Prerequisites"},
         "ceterms:description": {"en-US": "PSYC101"}},
        {"ceterms:name": {"en-US": "Prerequisite (recommended)"},
         "ceterms:description": {"en-US": "MATH100"}}]})]})
    r = probe.course_prerequisites(sample=50)
    assert r["courses_sampled"] == 1
    assert r["stating_a_prerequisite"] == 1


@pytest.mark.parametrize("description", [None, "", "   ", "None", "n/a"])
def test_a_prerequisite_block_carrying_nothing_is_not_free_text(monkeypatch, description):
    """A profile named "Prerequisites" whose description is absent, empty, or
    the word "None" was counted as stating one and then as free text. "None" is
    a statement that there are none; an empty one says nothing at all."""
    condition = {"ceterms:name": {"en-US": "Prerequisites"}}
    if description is not None:
        condition["ceterms:description"] = {"en-US": description}
    paged(monkeypatch, {1: [course(**{"ceterms:requires": [condition]})]})
    r = probe.course_prerequisites(sample=50)
    assert r["stating_a_prerequisite"] == 0
    assert r["free_text_only"] == 0
    assert r["stated_but_empty"] == 1


def test_pages_read_is_what_was_fetched_not_what_was_planned(monkeypatch):
    """`pages_read` returned the plan. The cap can end the walk early, so on
    such a run the documents quoted a reach the run did not have."""
    paged(monkeypatch, {1: [{"decoded_resource": {"@graph": [
        {"@type": "ceterms:Course"} for _ in range(20)]}} for _ in range(50)]})
    r = probe.course_prerequisites(sample=600)
    assert r["pages_read"] == [1], r["pages_read"]
    assert "single page" in r["sampling"], r["sampling"]
    assert "1-870" not in r["sampling"], "claimed a reach the walk did not have"


def test_a_competency_target_is_not_a_resolvable_prerequisite(monkeypatch):
    """A competency target says what you must be able to do, not which course
    you must have taken. The page argues about the Course -> Course edge."""
    paged(monkeypatch, {1: [course(**{"ceterms:requires": [
        {"ceterms:name": {"en-US": "Prerequisites"},
         "ceterms:targetCompetency": [{"@id": "https://x/c/1"}],
         "ceterms:description": {"en-US": "Able to weld"}}]})]})
    assert probe.course_prerequisites(sample=50)["resolvable"] == 0


def test_a_bare_string_prerequisite_must_look_like_a_reference(monkeypatch):
    """Any non-empty string counted as resolvable, so free text in the typed
    property would have moved the one number this file produces."""
    paged(monkeypatch, {1: [course(**{"ceterms:prerequisite": ["see the catalogue"]})]})
    r = probe.course_prerequisites(sample=50)
    assert (r["stating_a_prerequisite"], r["resolvable"]) == (1, 0)


def test_a_uri_string_prerequisite_still_resolves(monkeypatch):
    paged(monkeypatch, {1: [course(**{"ceterms:prerequisite": ["https://x/course/1"]})]})
    assert probe.course_prerequisites(sample=50)["resolvable"] == 1


def test_a_dict_without_an_id_is_not_a_reference(monkeypatch):
    paged(monkeypatch, {1: [course(**{"ceterms:prerequisite": [{"name": "Algebra"}]})]})
    assert probe.course_prerequisites(sample=50)["resolvable"] == 0


@pytest.mark.parametrize("field", list(probe.RESOLVABLE))
def test_a_bare_string_target_is_not_a_reference(monkeypatch, field):
    """The mirror of test_a_bare_string_prerequisite_must_look_like_a_reference,
    on the branch that actually fires: every resolvable hit in the live sample
    arrives through `ceterms:requires`, so the strict test was on the dead path
    and the loose one on the live path."""
    paged(monkeypatch, {1: [course(**{"ceterms:requires": [
        {"ceterms:name": {"en-US": "Prerequisites"}, field: ["PSYC101"],
         "ceterms:description": {"en-US": "PSYC101"}}]})]})
    r = probe.course_prerequisites(sample=50)
    assert (r["stating_a_prerequisite"], r["resolvable"]) == (1, 0)


@pytest.mark.parametrize("field", list(probe.RESOLVABLE))
def test_a_target_without_an_id_is_not_a_reference(monkeypatch, field):
    paged(monkeypatch, {1: [course(**{"ceterms:requires": [
        {"ceterms:name": {"en-US": "Prerequisites"},
         field: [{"@type": "ceterms:Credential"}],
         "ceterms:description": {"en-US": "a credential"}}]})]})
    assert probe.course_prerequisites(sample=50)["resolvable"] == 0


@pytest.mark.parametrize("field", list(probe.RESOLVABLE))
def test_a_target_with_an_id_still_resolves(monkeypatch, field):
    paged(monkeypatch, {1: [course(**{"ceterms:requires": [
        {"ceterms:name": {"en-US": "Prerequisites"},
         field: [{"@id": "https://x/c/1"}]}]})]})
    assert probe.course_prerequisites(sample=50)["resolvable"] == 1


@pytest.mark.parametrize("value,expected", [
    ({"@id": "https://x/c/1"}, True),
    ({"@type": "ceterms:Course"}, False),
    ("https://x/c/1", True),
    ("ce-registry/course/1", True),
    ("PSYC101", False),
    ("", False),
    (None, False),
    (42, False),
])
def test_one_reference_test_governs_both_branches(value, expected):
    """Asserted directly, so the two call sites cannot drift apart again — the
    asymmetry this closes is the fourth of its kind in this PR."""
    assert probe.is_reference(value) is expected

"""How the Registry's published courses are sampled, and what resolves — #53.

The network is stubbed throughout. Under test: the sampling method the
review of #57 asked to be made explicit, the shapes CTDL actually
publishes, and the refusals.
"""

import argparse
import json
import re
import urllib.error
import urllib.parse

import pytest

from etl import probe_registry as probe
from tests.registry_stubs import course, headers_stub, paged, prereq, stub

def test_pages_are_spread_across_the_population_not_taken_from_the_head():
    """Reading pages 1..12 samples whatever sorts first, which one publisher's
    bulk upload can dominate. Spreading them changed the measured rate from
    83/600 to 150/600 — the concern was real."""
    population = 47861
    wanted = 600
    pages, size = probe.sample_pages(wanted, population)
    total_pages = -(-population // probe.PER_PAGE)

    assert pages[0] == 1
    assert len(pages) == len(set(pages)) == -(-wanted // probe.PER_PAGE)
    # Derived from the constants rather than hard-coded, so changing PER_PAGE
    # does not silently turn this into a test of nothing.
    assert pages[-1] > total_pages * 0.8, "does not reach the far end"
    assert size == probe.PER_PAGE

def described(wanted: int, population: int | None) -> str:
    """The string the probe actually prints, for a walk that read every page it
    planned. Pointed at `describe()`, because that is the live implementation —
    these guards used to assert on a string `sample_pages` returned and nobody
    printed, so both retired claims could be reintroduced through a green
    suite."""
    pages, size = probe.sample_pages(wanted, population)
    return probe.describe(pages, size, population)


@pytest.mark.parametrize("population", [None, 0, 100, 47861])
def test_the_sampling_description_never_claims_randomness(population):
    """Stripping the literal "not random" would also hide "not randomly-ish".
    Asserting on the whole clause is what actually pins the claim."""
    how = described(600, population)
    for match in re.finditer(r"\brandom\w*", how):
        prefix = how[max(0, match.start() - 4):match.start()]
        assert prefix.endswith("not "), f"claims randomness: {how}"

def test_a_population_smaller_than_the_sample_reads_everything():
    pages, _ = probe.sample_pages(600, 120)
    assert pages == [1, 2, 3]
    assert "whole population, not a sample" in described(600, 120)

def test_an_unknown_population_falls_back_and_says_so():
    """If x-total is missing the pages cannot be spread. That is a weaker
    sample and the description has to admit it rather than look identical."""
    pages, _ = probe.sample_pages(600, None)
    assert pages == list(range(1, 13))
    how = described(600, None)
    assert "population unknown" in how and "biased" in how


def test_a_truncated_walk_with_an_unknown_population_is_described(monkeypatch):
    """Both weaknesses at once: the cap ended the walk early AND the population
    is unknown, so the description can claim neither a reach nor a spread. The
    branch existed and nothing exercised it."""
    how = probe.describe([1, 2], probe.PER_PAGE, None)
    assert "population unknown" in how
    assert "biased" in how
    for match in re.finditer(r"\brandom\w*", how):
        assert how[max(0, match.start() - 4):match.start()].endswith("not ")


def test_a_walk_that_read_nothing_says_so():
    assert probe.describe([], probe.PER_PAGE, 47861) == "nothing was read"

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
    pages, _ = probe.sample_pages(600, 47861)
    paged(monkeypatch, {p: [course(**prereq()), course()] for p in pages})
    r = probe.course_prerequisites(sample=600)
    assert r["courses_sampled"] == 2 * len(pages) == 24
    assert r["stating_a_prerequisite"] == len(pages) == 12

def test_a_page_that_returns_nothing_does_not_abort_the_walk(monkeypatch):
    pages, _ = probe.sample_pages(600, 47861)
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
    monkeypatch.setattr(probe.urllib.request, "urlopen", urlopen)
    r = probe.course_prerequisites(sample=600)
    assert r["courses_sampled"] == 600
    assert len(fetched) == 1, f"cap reached on page 1 but fetched pages {fetched}"

def test_the_sampling_description_does_not_claim_the_tail_it_skips():
    """Stride 79 over 12 pages reaches page 870 of 958. Saying "spread across
    all 958 pages" claimed 88 pages — about 4,400 courses — that are never read."""
    population = 47861
    pages, _ = probe.sample_pages(600, population)
    how = described(600, population)
    total_pages = -(-population // probe.PER_PAGE)
    assert pages[-1] < total_pages, "the stride does reach the end after all"
    assert f"{pages[0]}-{pages[-1]}" in how
    assert f"{total_pages:,}" in how
    assert "not sampled" in how
    assert f"all {total_pages:,} pages" not in how

def test_asking_for_zero_or_fewer_courses_is_rejected_by_the_cli():
    """It used to build per_page=0 and then fail with "no course records
    returned", blaming the source for a bad argument. Then it raised inside
    sample_pages and exited under "refused" — the category this module reserves
    for figures it declines to report. Bad CLI input is argparse's job."""
    for bad in ("0", "-5"):
        with pytest.raises(argparse.ArgumentTypeError, match="at least 1"):
            probe.positive(bad)


def test_the_cli_rejects_it_before_any_request_is_made(monkeypatch):
    """Nothing should be fetched to discover that an argument is invalid."""
    monkeypatch.setattr(probe.urllib.request, "urlopen",
                        lambda *a, **k: pytest.fail("fetched despite bad input"))
    with pytest.raises(SystemExit) as exit_code:
        probe.main(["--courses", "0"])
    assert exit_code.value.code == 2        # argparse usage error

def test_a_corrupt_body_is_malformed_not_refused(monkeypatch):
    """json.JSONDecodeError subclasses ValueError, so a truncated response used
    to exit 1 under "refused" — the category for figures we decline to report,
    not for a broken source."""
    class R:
        headers = {"x-total": "47861"}
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'[{"decoded_resource": '
    monkeypatch.setattr(probe.urllib.request, "urlopen", lambda *a, **k: R())
    with pytest.raises(probe.MalformedSource, match="did not parse"):
        probe.course_prerequisites(sample=50)

def test_a_corrupt_body_exits_three_through_main(monkeypatch):
    monkeypatch.setattr(probe, "registry_totals", lambda: {"source": "x"})
    monkeypatch.setattr(probe, "course_prerequisites",
                        lambda sample: (_ for _ in ()).throw(probe.MalformedSource("bad")))
    assert probe.main([]) == 3

def test_a_sample_that_is_not_a_multiple_of_a_page_is_not_short_changed():
    """`--courses 130` asked for three pages' worth and got two, silently
    sampling 100 while reporting the request. Ceiling, not floor."""
    pages, _ = probe.sample_pages(130, 47861)
    assert len(pages) == 3

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
    monkeypatch.setattr(probe.urllib.request, "urlopen", lambda *a, **k: R())
    with pytest.raises(probe.MalformedSource, match="not a list"):
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


def test_the_publisher_spread_is_printed_not_only_in_json(monkeypatch, capsys):
    """The docstring says publisher spread is reported alongside the rate, and
    the document quotes "13 distinct publishers" — but only --json carried it."""
    paged(monkeypatch, {1: [course()]})
    monkeypatch.setattr(probe, "registry_totals", lambda: {
        "source": "x", "envelopes_root": 1, "resources_all_communities": 1,
        "communities": {}, "ce_registry_by_type": {}, "deleted_resources": 0,
        "provisional_resources": 0, "unattributed": 0,
        "secured_communities": [], "failed_communities": []})
    probe.probe(sample=50)
    assert "distinct publishers" in capsys.readouterr().out


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


def test_both_probes_print_the_same_prerequisite_table(capsys):
    """probe_ctdl kept its own copy and it had already drifted — missing the
    stated-but-empty and publisher-spread lines. One printer, so it cannot."""
    import inspect
    from etl import probe_ctdl
    assert "print_prerequisites" in inspect.getsource(probe_ctdl)
    assert "stating a prerequisite" not in inspect.getsource(probe_ctdl), "a second copy"


def test_both_probes_share_one_command_line():
    """The two main() functions were byte-identical, which is how probe_ctdl
    kept type=int and no MalformedSource handler for a round after
    probe_registry gained both."""
    import inspect
    from etl import probe_ctdl
    assert "run_cli(" in inspect.getsource(probe_ctdl.main)
    assert "add_argument" not in inspect.getsource(probe_ctdl.main)

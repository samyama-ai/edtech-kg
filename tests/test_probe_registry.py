"""Tests for the Credential Registry probe.

The network is stubbed throughout. Under test: the two-totals reconciliation
(#59), the sampling method the review of #57 asked to be made explicit, the
shapes CTDL actually publishes, and the refusals.

The #59 tests lived in test_probe_ctdl.py until the code moved to
etl/probe_registry.py. They passed there only because probe_ctdl re-exports the
functions, which is exactly the kind of drift that makes a test file's docstring
stop being true.
"""

import io
import json
import urllib.error
import urllib.parse

import pytest

from etl import probe_registry as probe


def stub(monkeypatch, payload: bytes, x_total: int | None = None):
    class R:
        headers = {"x-total": str(x_total)} if x_total is not None else {}
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return payload
    monkeypatch.setattr(probe.urllib.request, "urlopen", lambda *a, **k: R())


# --------------------------------------------------------------------------
# how the sample is chosen — the review of #57 called this under-specified
# --------------------------------------------------------------------------

def test_pages_are_spread_across_the_population_not_taken_from_the_head():
    """Reading pages 1..12 samples whatever sorts first, which one publisher's
    bulk upload can dominate. Spreading them changed the measured rate from
    83/600 to 150/600 — the concern was real."""
    pages, how = probe.sample_pages(600, 47861)
    assert pages[0] == 1 and len(pages) == 12
    assert pages[-1] > 800                      # reaches the far end
    assert len(set(pages)) == 12                # no page read twice
    assert "stride" in how and "not random" in how


def test_the_sampling_description_never_claims_randomness():
    for population in (None, 0, 100, 47861):
        assert "random" not in probe.sample_pages(600, population)[1].replace(
            "not random", "")


def test_a_population_smaller_than_the_sample_reads_everything():
    pages, how = probe.sample_pages(600, 120)
    assert pages == [1, 2, 3]
    assert "whole population, not a sample" in how


def test_an_unknown_population_falls_back_and_says_so():
    """If x-total is missing the pages cannot be spread. That is a weaker
    sample and the description has to admit it rather than look identical."""
    pages, how = probe.sample_pages(600, None)
    assert pages == list(range(1, 13))
    assert "population unknown" in how and "biased" in how


def test_the_publisher_spread_is_reported(monkeypatch):
    """A verdict drawn from a sample that turns out to be three publishers is a
    fact about those three."""
    stub(monkeypatch, json.dumps([
        {"published_by": "org/a", "decoded_resource": {"@type": "ceterms:Course"}},
        {"published_by": "org/a", "decoded_resource": {"@type": "ceterms:Course"}},
        {"published_by": "org/b", "decoded_resource": {"@type": "ceterms:Course"}},
    ]).encode(), x_total=150)
    assert probe.course_prerequisites(sample=50)["distinct_publishers"] == 2


# --------------------------------------------------------------------------
# prerequisites in published courses — the number the probe exists for
# --------------------------------------------------------------------------

def course(**extra):
    return {"decoded_resource": {"@type": "ceterms:Course", **extra}}


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


# --------------------------------------------------------------------------
# the two totals (#59)
# --------------------------------------------------------------------------

def headers_stub(monkeypatch, table, root=None):
    """Serve x-total per path, and the API root as JSON."""
    class R:
        def __init__(self, h=None, body=b""): self.headers, self._b = h or {}, body
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return self._b

    def urlopen(request, *a, **k):
        url = request.full_url
        path = url[len(probe.REGISTRY):].split("?")[0]
        if request.get_method() == "HEAD":
            value = table.get(url) if url in table else table.get(path)
            if value == 401:
                raise urllib.error.HTTPError(url, 401, "no", {}, io.BytesIO(b""))
            return R({"x-total": str(value)} if value is not None else {})
        return R(body=json.dumps(root or {"total_envelopes": 10}).encode())

    monkeypatch.setattr(probe.urllib.request, "urlopen", urlopen)


def test_a_gated_community_reads_as_secured_not_as_empty(monkeypatch):
    """chaffeycollege returns 401. Printing that as a blank alongside
    mytxlibrary's real zero would state that it publishes nothing."""
    headers_stub(monkeypatch, {"/chaffeycollege/search": 401, "/search": 5})
    r = probe.registry_totals()
    assert r["communities"]["chaffeycollege"] == "secured"
    assert r["communities"]["mytxlibrary"] is None       # no header ≠ secured


def test_the_two_totals_are_labelled_by_what_they_count(monkeypatch):
    headers_stub(monkeypatch, {"/search": 682259}, root={"total_envelopes": 406431})
    r = probe.registry_totals()
    assert r["envelopes_root"] == 406431
    assert r["resources_all_communities"] == 682259
    assert "root_total_envelopes" not in r        # the old unlabelled name is gone


def test_the_unreadable_remainder_is_reported_not_hidden(monkeypatch):
    """Global minus the readable communities is what the gated one holds. If it
    ever exceeds that, a community exists which COMMUNITIES does not list."""
    headers_stub(monkeypatch, {
        "/search": 100, "/ce-registry/search": 90, "/fdoe/search": 9,
        "/mytxlibrary/search": 0, "/learning-registry/search": 0,
        "/chaffeycollege/search": 401})
    assert probe.registry_totals()["unattributed"] == 1


def test_deleted_and_provisional_are_measured_not_assumed(monkeypatch):
    """Both are plausible explanations for the gap. The probe rules them out by
    asking rather than by asserting they are zero."""
    headers_stub(monkeypatch, {
        f"{probe.REGISTRY}/ce-registry/search?per_page=1&include_deleted=only": 7,
        f"{probe.REGISTRY}/search?per_page=1&provisional=only": 3,
        "/search": 100})
    r = probe.registry_totals()
    assert r["deleted_resources"] == 7 and r["provisional_resources"] == 3


def test_query_params_are_appended_to_the_search_path(monkeypatch):
    seen = []
    class R:
        headers = {"x-total": "1"}
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(probe.urllib.request, "urlopen",
                        lambda rq, *a, **k: (seen.append(rq.full_url), R())[1])
    probe.total("/ce-registry/search", include_deleted="only")
    assert seen[0].endswith("/ce-registry/search?per_page=1&include_deleted=only")


# --------------------------------------------------------------------------
# shapes the source actually publishes, and the paths the review found bare
# --------------------------------------------------------------------------

def paged(monkeypatch, by_page: dict, x_total: int = 47861):
    """A stub that varies by page, so multi-page accumulation is real.

    The earlier stub ignored the URL, so every page returned the same body and a
    12-page walk was indistinguishable from reading one page twelve times."""
    class R:
        def __init__(self, body): self._b, self.headers = body, {"x-total": str(x_total)}
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return self._b

    def urlopen(request, *a, **k):
        # Parsed properly rather than by string search: "per_page=" contains
        # "page=", and splitting on it silently read page 50 instead of page 1.
        query = urllib.parse.parse_qs(urllib.parse.urlparse(request.full_url).query)
        page = int(query.get("page", ["1"])[0])
        return R(json.dumps(by_page.get(page, [])).encode())
    monkeypatch.setattr(probe.urllib.request, "urlopen", urlopen)


def course(**extra):
    return {"decoded_resource": {"@type": "ceterms:Course", **extra}}


def prereq(description="PSYC101"):
    return {"ceterms:requires": [{"ceterms:name": {"en-US": "Prerequisites"},
                                  "ceterms:description": {"en-US": description}}]}


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
    assert len(probe.course_prerequisites(sample=50)["examples"]) == 6


def test_a_long_example_is_truncated(monkeypatch):
    paged(monkeypatch, {1: [course(**prereq("X" * 300))]})
    assert len(probe.course_prerequisites(sample=50)["examples"][0]) == 90


def test_asking_for_fewer_than_one_page_samples_that_many(monkeypatch):
    """`--courses 20` used to read a full page of 50 and report "20 sampled"."""
    paged(monkeypatch, {1: [course() for _ in range(50)]})
    assert probe.course_prerequisites(sample=20)["courses_sampled"] == 20


def test_query_values_are_url_encoded(monkeypatch):
    seen = []
    class R:
        headers = {"x-total": "1"}
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(probe.urllib.request, "urlopen",
                        lambda rq, *a, **k: (seen.append(rq.full_url), R())[1])
    probe.total("/ce-registry/search", fts="a b&c")
    assert " " not in seen[0] and "a+b%26c" in seen[0]

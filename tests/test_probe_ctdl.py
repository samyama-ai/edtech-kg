"""Tests for the CTDL probe.

The network is stubbed throughout. What is being tested is the parsing and the
refusals — the things that would otherwise turn a broken fetch into a confident
number in a document.
"""

import io
import json
import urllib.error

import pytest

from etl import probe_ctdl as probe


def stub(monkeypatch, payload: bytes):
    class Response:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return payload
        headers = {}
    monkeypatch.setattr(probe.urllib.request, "urlopen", lambda *a, **k: Response())


GRAPH = {
    "@graph": [
        {"@id": "ceterms:Course", "@type": "rdfs:Class"},
        {"@id": "ceterms:Pathway", "@type": "rdfs:Class"},
        {"@id": "ceterms:ConditionProfile", "@type": "rdfs:Class"},
        {"@id": "ceterms:prerequisite", "@type": "rdf:Property",
         "schema:domainIncludes": {"@id": "ceterms:Course"},
         "schema:rangeIncludes": [{"@id": "ceterms:Course"}]},
    ]
}


# --------------------------------------------------------------------------
# the vocabulary
# --------------------------------------------------------------------------

def test_terms_are_counted_by_rdf_type(monkeypatch):
    stub(monkeypatch, json.dumps(GRAPH).encode())
    v = probe.vocabulary()
    assert v["terms"] == 4
    assert v["by_type"] == {"rdfs:Class": 3, "rdf:Property": 1}


def test_prerequisite_is_reported_with_the_names_ctdl_uses(monkeypatch):
    """`domainIncludes` / `rangeIncludes` are non-committal lists carrying no
    entailment. Printing them as `domain` / `range` would claim more than the
    source says — the review of #54 asked for the source's own names."""
    stub(monkeypatch, json.dumps(GRAPH).encode())
    p = probe.vocabulary()["prerequisite"]
    assert set(p) == {"domainIncludes", "rangeIncludes"}
    assert p["domainIncludes"] == ["ceterms:Course"]
    assert p["rangeIncludes"] == ["ceterms:Course"]


def test_a_single_dict_and_a_list_are_read_the_same_way(monkeypatch):
    """The source writes one value as a bare object and several as a list."""
    stub(monkeypatch, json.dumps(GRAPH).encode())
    p = probe.vocabulary()["prerequisite"]
    assert isinstance(p["domainIncludes"], list)          # was a bare dict
    assert isinstance(p["rangeIncludes"], list)


def test_a_missing_property_is_none_rather_than_an_invented_blank(monkeypatch):
    stub(monkeypatch, json.dumps({"@graph": [{"@id": "x", "@type": "rdfs:Class"}]}).encode())
    assert probe.vocabulary()["prerequisite"] is None


def test_an_html_error_page_is_refused(monkeypatch):
    """A 200 carrying an error page would otherwise be reported as zero classes."""
    stub(monkeypatch, b"<html>Service Unavailable</html>")
    with pytest.raises(ValueError, match="did not return JSON"):
        probe.vocabulary()


def test_an_empty_graph_is_refused(monkeypatch):
    stub(monkeypatch, json.dumps({"@graph": []}).encode())
    with pytest.raises(ValueError, match="refusing"):
        probe.vocabulary()


def test_an_http_error_names_the_status(monkeypatch):
    monkeypatch.setattr(probe.urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(
                            urllib.error.HTTPError("u", 503, "no", {}, io.BytesIO(b""))))
    with pytest.raises(RuntimeError, match="503"):
        probe.get("https://example.invalid/x")


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
# the CLI
# --------------------------------------------------------------------------

def test_refusal_exits_nonzero_without_printing_a_table(monkeypatch, capsys):
    stub(monkeypatch, b"<html>down</html>")
    assert probe.main(["--json"]) == 1
    assert "terms" not in capsys.readouterr().out


def test_an_unreachable_source_exits_two(monkeypatch):
    monkeypatch.setattr(probe.urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(urllib.error.URLError("dns")))
    assert probe.main([]) == 2


def test_json_output_carries_a_timestamp(monkeypatch, capsys):
    stub(monkeypatch, json.dumps(GRAPH).encode())
    monkeypatch.setattr(probe, "registry_totals", lambda: {"source": "x"})
    monkeypatch.setattr(probe, "course_prerequisites",
                        lambda sample: {"courses_sampled": 1, "stating_a_prerequisite": 0,
                                        "resolvable": 0, "free_text_only": 0, "examples": []})
    assert probe.main(["--json"]) == 0
    assert "retrieved_at" in json.loads(capsys.readouterr().out)


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

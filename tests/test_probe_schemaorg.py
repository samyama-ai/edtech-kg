"""Tests for the schema.org probe.

The network is stubbed. Under test: the term lookup, the range reading that
decides #33's prerequisite row, and the refusals.
"""

import io
import json
import urllib.error

import pytest

from etl import probe_schemaorg as probe


GRAPH = {"@graph": [
    {"@id": "schema:Course", "@type": "rdfs:Class"},
    {"@id": "schema:CourseInstance", "@type": "rdfs:Class"},
    {"@id": "schema:EducationalOccupationalProgram", "@type": "rdfs:Class"},
    {"@id": "schema:EducationalOccupationalCredential", "@type": "rdfs:Class"},
    {"@id": "schema:Occupation", "@type": "rdfs:Class"},
    {"@id": "schema:EducationalOrganization", "@type": "rdfs:Class"},
    {"@id": "schema:CollegeOrUniversity", "@type": "rdfs:Class"},
    {"@id": "schema:coursePrerequisites", "@type": "rdf:Property",
     "schema:domainIncludes": {"@id": "schema:Course"},
     "schema:rangeIncludes": [{"@id": "schema:Course"}, {"@id": "schema:Text"}],
     "rdfs:comment": "Requirements for taking the Course."},
    {"@id": "schema:programPrerequisites", "@type": "rdf:Property"},
    {"@id": "schema:hasCourse", "@type": "rdf:Property"},
    {"@id": "schema:occupationalCategory", "@type": "rdf:Property"},
    {"@id": "schema:educationalCredentialAwarded", "@type": "rdf:Property"},
    {"@id": "schema:competencyRequired", "@type": "rdf:Property"},
    {"@id": "schema:provider", "@type": "rdf:Property",
     "schema:rangeIncludes": [{"@id": "schema:Organization"}]},
]}


def stub(monkeypatch, payload: bytes):
    class R:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return payload
    monkeypatch.setattr(probe.urllib.request, "urlopen", lambda *a, **k: R())


def test_every_wanted_term_is_looked_up(monkeypatch):
    stub(monkeypatch, json.dumps(GRAPH).encode())
    v = probe.vocabulary()
    assert v["wanted"] == len(probe.WANTED)
    assert v["present"] == len(probe.WANTED)
    assert v["absent"] == []


def test_an_absent_term_is_recorded_not_skipped(monkeypatch):
    """A missing term is a finding for #33 — it means align or mint. Dropping
    it from the output would read as though it had been checked and found."""
    graph = {"@graph": [n for n in GRAPH["@graph"] if n["@id"] != "schema:Occupation"]}
    stub(monkeypatch, json.dumps(graph).encode())
    v = probe.vocabulary()
    assert v["absent"] == ["schema:Occupation"]
    assert v["terms"]["schema:Occupation"] is None
    assert v["present"] == len(probe.WANTED) - 1


def test_the_prerequisite_range_is_read_both_ways(monkeypatch):
    """The fact #33 turns on: schema.org's prerequisite accepts a Course
    reference AND free text, where CTDL's accepts only a Course."""
    stub(monkeypatch, json.dumps(GRAPH).encode())
    v = probe.vocabulary()
    assert v["course_prerequisite_accepts_course"] is True
    assert v["course_prerequisite_accepts_text"] is True


def test_a_course_only_range_does_not_report_text_support(monkeypatch):
    """The negative case, so the flag means something. If schema.org were as
    strict as CTDL this must say so rather than defaulting to True."""
    graph = json.loads(json.dumps(GRAPH))
    for n in graph["@graph"]:
        if n["@id"] == "schema:coursePrerequisites":
            n["schema:rangeIncludes"] = [{"@id": "schema:Course"}]
    stub(monkeypatch, json.dumps(graph).encode())
    v = probe.vocabulary()
    assert v["course_prerequisite_accepts_course"] is True
    assert v["course_prerequisite_accepts_text"] is False


def test_a_missing_prerequisite_term_does_not_crash_the_flags(monkeypatch):
    graph = {"@graph": [n for n in GRAPH["@graph"]
                        if n["@id"] != "schema:coursePrerequisites"]}
    stub(monkeypatch, json.dumps(graph).encode())
    v = probe.vocabulary()
    assert v["course_prerequisite_accepts_text"] is False


def test_a_bare_string_and_a_list_flatten_the_same():
    assert probe.ids({"@id": "schema:Course"}) == ["schema:Course"]
    assert probe.ids([{"@id": "a"}, {"@id": "b"}]) == ["a", "b"]
    assert probe.ids("schema:Text") == ["schema:Text"]
    assert probe.ids(None) == []


def test_an_html_error_page_is_refused(monkeypatch):
    """A 200 carrying an error page would report every term as absent — which
    reads as "schema.org does not define these" rather than "the fetch broke"."""
    stub(monkeypatch, b"<html>503</html>")
    with pytest.raises(ValueError, match="did not return JSON"):
        probe.vocabulary()


def test_an_empty_graph_is_refused(monkeypatch):
    stub(monkeypatch, json.dumps({"@graph": []}).encode())
    with pytest.raises(ValueError, match="refusing"):
        probe.vocabulary()


def test_an_unreachable_source_exits_two(monkeypatch):
    monkeypatch.setattr(probe.urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(urllib.error.URLError("dns")))
    assert probe.main([]) == 2


def test_a_refusal_exits_one(monkeypatch):
    stub(monkeypatch, b"<html>down</html>")
    assert probe.main([]) == 1


def test_json_output_carries_a_timestamp(monkeypatch, capsys):
    stub(monkeypatch, json.dumps(GRAPH).encode())
    assert probe.main(["--json"]) == 0
    assert "retrieved_at" in json.loads(capsys.readouterr().out)


# --------------------------------------------------------------------------
# the cited definition URLs — #33 requires a reader can check every mapping
# --------------------------------------------------------------------------

def test_a_dead_citation_is_reported_not_raised(monkeypatch):
    """One dead link must not hide the others, so every URL is checked and the
    broken ones collected."""
    def urlopen(request, *a, **k):
        if request.full_url.endswith("/gone"):
            raise urllib.error.HTTPError(request.full_url, 404, "no", {}, io.BytesIO(b""))
        class R:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *a): return False
        return R()
    monkeypatch.setattr(probe.urllib.request, "urlopen", urlopen)
    check = probe.check_cited(["https://x/ok", "https://x/gone", "https://x/also-ok"])
    assert check["checked"] == 3
    assert check["broken"] == {"https://x/gone": 404}


def test_every_url_the_decision_cites_is_in_the_check_list():
    """The list exists to keep docs/ontology-reuse.md auditable. If a term is
    cited there and not listed here, its rot goes unnoticed."""
    assert len(probe.CITED) == len(set(probe.CITED))
    assert all(u.startswith("https://") for u in probe.CITED)
    for term in ("coursePrerequisites", "isPreparationFor", "occupationalCategory"):
        assert any(term in u for u in probe.CITED), term


def test_check_urls_exits_nonzero_when_a_citation_is_dead(monkeypatch):
    monkeypatch.setattr(probe, "check_cited",
                        lambda *a: {"checked": 2, "results": {"u": 404},
                                    "broken": {"u": 404}})
    assert probe.main(["--check-urls"]) == 1


def test_check_urls_exits_zero_when_all_resolve(monkeypatch):
    monkeypatch.setattr(probe, "check_cited",
                        lambda *a: {"checked": 2, "results": {"u": 200}, "broken": {}})
    assert probe.main(["--check-urls"]) == 0

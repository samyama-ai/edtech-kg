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
# The network lives in probe_registry — probe_ctdl imports `get` from it and no
# longer touches urllib itself. Patching here is what the code actually calls.
from etl import probe_registry as net


def stub(monkeypatch, payload: bytes):
    class Response:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return payload
        headers = {}
    monkeypatch.setattr(net.urllib.request, "urlopen", lambda *a, **k: Response())


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
    with pytest.raises(net.MalformedSource, match="did not return JSON"):
        probe.vocabulary()


def test_an_empty_graph_is_refused(monkeypatch):
    stub(monkeypatch, json.dumps({"@graph": []}).encode())
    with pytest.raises(ValueError, match="refusing"):
        probe.vocabulary()


def test_an_http_error_names_the_status(monkeypatch):
    monkeypatch.setattr(net.urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(
                            urllib.error.HTTPError("u", 503, "no", {}, io.BytesIO(b""))))
    with pytest.raises(RuntimeError, match="503"):
        net.get("https://example.invalid/x")


# --------------------------------------------------------------------------
# the CLI
# --------------------------------------------------------------------------

def test_an_html_error_page_exits_as_malformed_not_refused(monkeypatch, capsys):
    """A 200 carrying HTML and a truncated JSON body are the same class of
    failure. They were exiting under two different categories."""
    stub(monkeypatch, b"<html>down</html>")
    assert probe.main(["--json"]) == 3
    assert "terms" not in capsys.readouterr().out


def test_an_unreachable_source_exits_two(monkeypatch):
    monkeypatch.setattr(net.urllib.request, "urlopen",
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


def test_a_corrupt_vocabulary_body_exits_three_not_as_a_traceback(monkeypatch):
    """`vocabulary()` used bare json.loads, so a truncated body raised
    JSONDecodeError — a ValueError, reported as "refused" — and MalformedSource
    was not caught in main() at all, giving a traceback instead of exit 3."""
    class R:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"@graph": [{"@id": '
    monkeypatch.setattr(net.urllib.request, "urlopen", lambda *a, **k: R())
    assert probe.main([]) == 3


def test_the_registry_tables_come_from_one_place():
    """The print block was duplicated verbatim in both modules and had already
    drifted. probe_ctdl must use the shared one, not carry a copy."""
    import inspect
    source = inspect.getsource(probe)
    assert "print_registry" in source
    assert "resources by community" not in source, "a second copy of the block"

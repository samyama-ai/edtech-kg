"""The CASE probe's classification, driven without the network.

The finding is a set of NEGATIVE results, so what matters is that each one is
reached by looking. A path that refused, a path that returned the app's own
markup, and a path that was never asked all produce "no CASE JSON" and mean
different things.
"""

from __future__ import annotations

import json

import pytest

from etl import probe_case as probe


def test_a_refusal_is_a_measurement_and_not_an_exception(monkeypatch):
    """**A 403 on a registry advertised as "free to browse and use" is the
    finding.** It has to come back as data rather than as an exception the
    caller turns into a shrug."""
    import urllib.error
    monkeypatch.setattr(
        probe.urllib.request, "urlopen",
        lambda *a, **k: (_ for _ in ()).throw(
            urllib.error.HTTPError("u", 403, "Forbidden", {}, None)))
    status, body = probe.fetch("https://x.test/uri/")
    assert status == 403
    assert body == ""


def test_a_host_that_does_not_answer_at_all_raises(monkeypatch):
    """Distinct from a refusal. "The registry refuses" and "the network was
    down" are different findings and the page states the first."""
    import urllib.error
    monkeypatch.setattr(
        probe.urllib.request, "urlopen",
        lambda *a, **k: (_ for _ in ()).throw(urllib.error.URLError("down")))
    with pytest.raises(probe.Unreachable):
        probe.fetch("https://x.test/")


def test_the_apps_own_markup_is_not_an_endpoint(monkeypatch):
    """A single-page application answers 200 for every path with the same
    shell. Counting that as a served path would report a browser app as a
    CASE API."""
    shell = "<html><body>Standards Satchel</body></html>"
    monkeypatch.setattr(probe, "fetch", lambda url: (200, shell))
    found = probe.case_network()
    assert found["reachable_as_data"] is False
    assert all(f["same_as_root"] for f in found["paths"].values()), (
        "a path returning the root's markup must be marked as such")
    assert found["serves_case_json"] == []


def test_real_case_json_is_recognised(monkeypatch):
    """The negative must be reachable only by looking, so the positive has to
    work — otherwise "0 paths serve CASE JSON" is true of any input."""
    body = '{"CFDocuments": [{"identifier": "x", "creator": "A State"}]}'
    monkeypatch.setattr(
        probe, "fetch",
        lambda url: (200, body) if url.endswith("CFDocuments") else (200, "<html>"))
    found = probe.case_network()
    assert found["reachable_as_data"] is True
    assert found["serves_case_json"]


def test_opensalt_reports_who_authored_the_documents(monkeypatch):
    """"A sandbox" is a claim about the CREATORS, so a probe that counted
    documents and not creators could not support it."""
    # **The SPEC spelling.** `licenceUri` — British — is in no version of
    # the CASE model, and feeding it here is what let the probe's own
    # misspelling pass: the fixture agreed with the code and neither agreed
    # with the specification.
    body = ('{"CFDocuments": ['
            '{"creator": "PCG Test Prep"}, {"creator": "PCG Test Prep"},'
            '{"creator": "ETS", "licenseUri": {"title": "CC BY", '
            '"uri": "http://x"}}]}')
    monkeypatch.setattr(probe, "fetch", lambda url: (200, body))
    found = probe.opensalt()
    assert found["documents"] == 3
    assert found["distinct_creators"] == 2
    assert found["top_creators"][0] == ("PCG Test Prep", 2)
    # A LinkURI is an object, so truthiness is the test — a populated one is
    # a non-empty dict, not a string.
    assert found["documents_by_licence_field"]["licenseUri"] == 1
    assert found["documents_by_licence_field"]["licenceUri"] == 0


def test_the_key_set_is_recorded_so_a_zero_is_checkable():
    """A count of a key that does not exist is zero however the server
    behaves. Recording what the documents ACTUALLY carry is what makes the
    page's "no licence field is published" claim checkable — and makes a
    future field rename visible rather than silently zero."""
    body = '{"CFDocuments": [{"creator": "A", "title": "T"}, {"creator": "B"}]}'
    found = probe.licence_fields(json.loads(body)["CFDocuments"])
    assert found["keys_observed"] == {"creator": 2, "title": 1}
    assert all(v == 0 for v in found["documents_by_licence_field"].values())


def test_a_non_case_answer_from_opensalt_is_not_counted_as_zero_documents(
        monkeypatch):
    """A server returning HTML has not published no standards — it has not
    answered the question. Reporting 0 would fold a broken route into the
    finding."""
    monkeypatch.setattr(probe, "fetch", lambda url: (200, "<html>nope</html>"))
    found = probe.opensalt()
    assert found["documents"] == 0
    assert "did not return CASE JSON" in found["note"]


def test_the_cpalms_search_looks_for_links_and_codes(monkeypatch):
    """Two ways an alignment could be in the markup. Searching one would
    report a zero that was never asked of the other."""
    markup = ('<a href="/PreviewStandard/Preview/91">MA.912.AR.1.1</a>'
              '<a href="/PreviewStandard/Preview/92">x</a>')
    monkeypatch.setattr(probe, "fetch", lambda url: (200, markup))
    found = probe.cpalms()
    pages = len(probe.CPALMS_COURSES)
    assert found["standard_links"] == 2 * pages
    assert found["standard_codes"] == 1 * pages


def test_identical_documents_for_different_courses_are_recognised(monkeypatch):
    """**The finding three pages turned out to carry.** One document for
    three course ids means the server publishes no course content at all —
    the whole page is assembled in a browser, and the missing alignment is a
    consequence rather than a separate fact."""
    monkeypatch.setattr(probe, "fetch", lambda url: (200, "<html>shell</html>"))
    found = probe.cpalms()
    assert found["distinct_documents"] == 1
    assert found["serves_one_document_for_every_course"] is True
    assert not any(p["names_its_own_course_id"] for p in found["pages"])


def test_distinct_documents_are_not_reported_as_a_shell(monkeypatch):
    """Identical bytes alone could be a coincidence of length. A server
    genuinely publishing per-course pages must not be called a shell."""
    monkeypatch.setattr(
        probe, "fetch",
        lambda url: (200, f"<html>course {url.rsplit('/', 1)[-1]}</html>"))
    found = probe.cpalms()
    assert found["distinct_documents"] == len(probe.CPALMS_COURSES)
    assert found["serves_one_document_for_every_course"] is False
    assert all(p["names_its_own_course_id"] for p in found["pages"])

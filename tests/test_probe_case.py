"""The CASE probe's classification, driven without the network.

The finding is a set of NEGATIVE results, so what matters is that each one is
reached by looking. A path that refused, a path that returned the app's own
markup, and a path that was never asked all produce "no CASE JSON" and mean
different things.
"""

from __future__ import annotations

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
    body = ('{"CFDocuments": ['
            '{"creator": "PCG Test Prep"}, {"creator": "PCG Test Prep"},'
            '{"creator": "ETS", "licenceUri": "http://x"}]}')
    monkeypatch.setattr(probe, "fetch", lambda url: (200, body))
    found = probe.opensalt()
    assert found["documents"] == 3
    assert found["distinct_creators"] == 2
    assert found["top_creators"][0] == ("PCG Test Prep", 2)
    assert found["documents_with_a_licence_uri"] == 1


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
    assert found["standard_links"] == 2
    assert found["standard_codes"] == 1

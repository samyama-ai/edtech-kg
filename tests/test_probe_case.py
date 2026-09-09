"""The CASE probe's classification, driven without the network.

The finding is a set of NEGATIVE results, so what matters is that each one is
reached by looking. A path that refused, a path that returned the app's own
markup, and a path that was never asked all produce "no CASE JSON" and mean
different things.
"""

from __future__ import annotations

import io
import json
import urllib.error

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
    status, body, _ = probe.fetch("https://x.test/uri/")
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
    monkeypatch.setattr(probe, "fetch", lambda url: (200, shell, "text/html"))
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
        lambda url: (200, body, "application/json") if url.endswith("CFDocuments") else (200, "<html>", "text/html"))
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
    monkeypatch.setattr(probe, "fetch", lambda url: (200, body, "text/html"))
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
    monkeypatch.setattr(probe, "fetch", lambda url: (200, "<html>nope</html>", "text/html"))
    found = probe.opensalt()
    assert found["documents"] == 0
    assert "did not return CASE JSON" in found["note"]


def test_the_cpalms_search_looks_for_links_and_codes(monkeypatch):
    """Two ways an alignment could be in the markup. Searching one would
    report a zero that was never asked of the other."""
    markup = ('<a href="/PreviewStandard/Preview/91">MA.912.AR.1.1</a>'
              '<a href="/PreviewStandard/Preview/92">x</a>')
    monkeypatch.setattr(probe, "fetch", lambda url: (200, markup, "text/html"))
    found = probe.cpalms()
    pages = len(probe.CPALMS_COURSES)
    assert found["standard_links"] == 2 * pages
    assert found["standard_codes"] == 1 * pages


def test_identical_documents_for_different_courses_are_recognised(monkeypatch):
    """**The finding three pages turned out to carry.** One document for
    three course ids means the server publishes no course content at all —
    the whole page is assembled in a browser, and the missing alignment is a
    consequence rather than a separate fact."""
    monkeypatch.setattr(probe, "fetch", lambda url: (200, "<html>shell</html>", "text/html"))
    found = probe.cpalms()
    assert found["distinct_documents"] == 1
    assert found["serves_one_document_for_every_course"] is True
    assert not any(p["names_its_own_course_id"] for p in found["pages"])


def test_distinct_documents_are_not_reported_as_a_shell(monkeypatch):
    """Identical bytes alone could be a coincidence of length. A server
    genuinely publishing per-course pages must not be called a shell."""
    monkeypatch.setattr(
        probe, "fetch",
        lambda url: (200, f"<html>course {url.rsplit('/', 1)[-1]}</html>", "text/html"))
    found = probe.cpalms()
    assert found["distinct_documents"] == len(probe.CPALMS_COURSES)
    assert found["serves_one_document_for_every_course"] is False
    assert all(p["names_its_own_course_id"] for p in found["pages"])


def test_a_refusals_body_is_recorded_not_discarded(monkeypatch):
    """**Blocker 1.** `return refused.code, ""` threw away the most
    informative thing on route 1.

    The two spec paths answer `{"message": "Invalid credentials provided 1"}`
    — 44 bytes of `application/json`. Discarded, the record showed
    `bytes: 0`, which is an artefact of the discard published in a table of
    measurements; and the page then read the silence as "CASE Network 2 is a
    browser application" when the body says it is an authenticated API asking
    for credentials.
    """
    class Refused(urllib.error.HTTPError):
        def __init__(self):
            super().__init__("https://x/CFDocuments", 403, "Forbidden", {},
                             io.BytesIO(
                                 b'{"message":"Invalid credentials provided 1"}'))

    def raise_403(request, timeout=None):
        raise Refused()

    monkeypatch.setattr(probe.urllib.request, "urlopen", raise_403)
    status, body, _ = probe.fetch("https://x/CFDocuments")
    assert status == 403
    assert "Invalid credentials" in body, (
        "the refusal's body was discarded, so `bytes: 0` is the probe's own "
        "doing rather than a measurement")


def test_the_refusals_body_is_not_mistaken_for_case_json():
    """**Blockers 1 and 3 interact, which is why they land together.**
    Reading the 403 body without tightening the JSON test would have inverted
    route 1's conclusion: `{"message": "…"}` parses, so a bare `json.loads`
    would report the path as serving CASE JSON."""
    assert not probe.is_case_json('{"message":"Invalid credentials provided 1"}')


def test_case_json_means_a_case_payload_not_merely_parseable(monkeypatch):
    """`serves_case_json` and `reachable_as_data` used to flip True on ANY
    parseable JSON — so "0 paths serve CASE JSON" was a claim about the
    absence of a body, not about its shape."""
    for not_case in ('{"anything": 1}', "[]", '"a string"', "42",
                     '{"error": "nope"}'):
        assert not probe.is_case_json(not_case), not_case
    # A container has to be NON-EMPTY: see
    # `test_an_empty_case_container_is_not_a_case_payload`.
    for case in ('{"CFDocuments": [{"identifier": "x"}]}',
                 '{"CFDocument": {"identifier": "x"}}',
                 '{"CFItems": [{"identifier": "y"}], "extra": 1}'):
        assert probe.is_case_json(case), case


def test_the_spec_spelling_of_the_licence_field_is_among_those_checked():
    """**Blocker 2, and the same defect twice.** CASE v1p0 spells it
    `licenseURI`. The first version of this probe looked for `licenceUri`
    (British, in no version of the model); the correction looked for
    `licenseUri` and called it "the CASE v1p0 spelling". It is not.

    A zero beside a key that no version of the model defines is guaranteed
    before a document is read. The conclusion held both times because
    `keys_observed` records what the documents actually carry — the dump
    caught it, the detector never did.

    The wrong spellings stay as negative controls: finding one on a live
    document would say something worth knowing about the publisher.
    """
    assert "licenseURI" in probe.LICENCE_FIELDS, (
        "the spelling the specification uses is not among those checked")
    for control in ("licenseUri", "licenceUri", "licenceURI"):
        assert control in probe.LICENCE_FIELDS, control


def test_the_report_prints_a_licence_figure_that_exists(monkeypatch, capsys):
    """`report()` read `salt.get('documents_with_a_licence_uri', 0)` — a key
    the probe stopped producing — so it printed a LITERAL 0 and would keep
    printing 0 if OpenSALT started publishing licences.

    Nothing drove the reporting path, which is how a stale key survives on the
    one output a human actually reads.
    """
    found = {
        "case_network": {"base": "https://x", "root_status": 200,
                         "root_bytes": 10, "paths": {},
                         "serves_case_json": [], "reachable_as_data": False},
        "opensalt": {"base": "https://y", "status": 200, "documents": 95,
                     "distinct_creators": 39, "top_creators": [],
                     "keys_observed": ["identifier"],
                     "documents_by_licence_field": {"licenseURI": 3}},
        "cpalms": {"base": "https://z", "answered": 0, "pages": [],
                   "standard_links": 0, "standard_codes": 0,
                   "distinct_documents": 0},
    }
    probe.report(found)
    printed = capsys.readouterr().out
    assert "3 carrying a licence field" in printed, printed


def test_an_empty_case_container_is_not_a_case_payload():
    """**Blocker 3.** `{"CFDocuments": null}` and `{"CFDocuments": []}` both
    returned True, so OpenSALT answering
    `{"error":"maintenance","CFDocuments":null}` took the "server answered
    CASE" branch and reported `documents: 0`."""
    for empty in ('{"CFDocuments": null}', '{"CFDocuments": []}',
                  '{"CFItems": [], "CFDocuments": []}',
                  '{"error":"maintenance","CFDocuments":null}'):
        assert not probe.is_case_json(empty), empty
    assert probe.is_case_json('{"CFDocuments": [{"identifier": "x"}]}')


def test_record_refuses_to_overwrite_a_count_with_zero(monkeypatch, tmp_path,
                                                       capsys):
    """The emptiness guard asks whether anything ANSWERED; it does not ask
    whether the answer was smaller than the one on disk. A 200 with an error
    page overwrote 95 documents with 0, and the doc test catches that only
    after the record is already gone."""
    record = tmp_path / "case-measured.json"
    record.write_text(json.dumps({"opensalt": {"documents": 95}}),
                      encoding="utf-8")
    monkeypatch.setattr(probe, "RECORD", record)
    monkeypatch.setattr(probe, "measure", lambda: {
        "case_network": {"root_status": 200}, "cpalms": {"status": 200},
        "opensalt": {"status": 200, "documents": 0}})
    monkeypatch.setattr(probe, "report", lambda m: None)
    assert probe.main(["--record"]) == 3
    assert "0 documents where 95 are recorded" in capsys.readouterr().err
    assert json.loads(record.read_text())["opensalt"]["documents"] == 95


def test_the_refusals_content_type_and_body_are_recorded(monkeypatch):
    """**Blocker 2.** The record gained `bytes: 44`, and the page then printed
    the literal payload and asserted "44 bytes of application/json" as prose —
    so editing that cell to `{"ok":true}` left every test green. The over-read
    moved from an artefact of a discard to an unchecked assertion.
    """
    class Refused(urllib.error.HTTPError):
        def __init__(self):
            super().__init__(
                "https://x/CFDocuments", 403, "Forbidden",
                {"Content-Type": "application/json"},
                io.BytesIO(b'{"message":"Invalid credentials provided 1"}'))

    monkeypatch.setattr(probe.urllib.request, "urlopen",
                        lambda request, timeout=None: (_ for _ in ()).throw(
                            Refused()))
    status, body, content_type = probe.fetch("https://x/CFDocuments")
    assert status == 403
    assert content_type == "application/json"
    assert "Invalid credentials" in body


def test_a_recorded_body_is_bounded():
    """The page prints these verbatim. An unbounded field would put a whole
    SPA shell into a table."""
    assert probe.BODY_HEAD <= 512

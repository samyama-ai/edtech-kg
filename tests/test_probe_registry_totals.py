"""The Registry's two totals count two different things — #59.

Split from the course-sampling tests when the single file passed the
500-line limit the reviewer works to. One subject per file.
"""

import io
import urllib.error

from etl import probe_registry as probe
from tests.registry_stubs import headers_stub

def test_a_gated_community_reads_as_secured_not_as_empty(monkeypatch):
    """chaffeycollege returns 401. Printing that as a blank alongside
    mytxlibrary's real zero would state that it publishes nothing."""
    headers_stub(monkeypatch, {"/chaffeycollege/search": 401, "/search": 5})
    r = probe.registry_totals()
    assert r["communities"]["chaffeycollege"] == "secured"
    # Answered without a count is a third fact, distinct from both.
    assert r["communities"]["mytxlibrary"] == "no x-total header"

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

def test_a_status_is_read_from_the_error_not_from_its_text(monkeypatch):
    """"secured" used to be decided by searching the exception text for "401".
    A URL containing those digits satisfied that search."""
    url = "https://credentialengineregistry.org/401-not-a-status/search"
    monkeypatch.setattr(probe.urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(
                            urllib.error.HTTPError(url, 500, "boom", {}, io.BytesIO(b""))))
    assert probe.total("/401-not-a-status/search") == "error 500"   # not "secured"

def test_a_real_401_is_still_secured(monkeypatch):
    monkeypatch.setattr(probe.urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(
                            urllib.error.HTTPError("u", 401, "no", {}, io.BytesIO(b""))))
    assert probe.total("/chaffeycollege/search") == "secured"

def test_the_header_lookup_is_case_insensitive(monkeypatch):
    """The live service sends `X-Total`. dict(response.headers) threw the
    case-insensitive lookup away and left a fragile two-key fallback."""
    import email.message
    msg = email.message.Message()
    msg["X-Total"] = "4242"
    class R:
        headers = msg
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(probe.urllib.request, "urlopen", lambda *a, **k: R())
    assert probe.total("/ce-registry/search") == 4242


def test_a_response_without_a_count_is_not_silently_unknown(monkeypatch):
    """A 200 that carries no `x-total` used to degrade to None, which reads as
    "population unknown" and quietly widens the sampling caveat rather than
    saying the source answered wrongly."""
    headers_stub(monkeypatch, {"/ce-registry/search": None})
    assert probe.total("/ce-registry/search") == "no x-total header"


def test_the_gated_claim_is_only_made_when_it_is_true(monkeypatch):
    """`print_registry` labelled the remainder "(the gated community)" whenever
    exactly one community failed — for any reason, including a transport error."""
    headers_stub(monkeypatch, {"/search": 100, "/ce-registry/search": 99,
                               "/fdoe/search": 0, "/mytxlibrary/search": 0,
                               "/learning-registry/search": 0,
                               "/chaffeycollege/search": 401})
    r = probe.registry_totals()
    assert r["secured_communities"] == ["chaffeycollege"]
    assert r["failed_communities"] == []


REGISTRY_SHAPE = {
    "source": "https://x", "envelopes_root": 406431,
    "resources_all_communities": 682259,
    "communities": {"ce-registry": 671681, "chaffeycollege": "secured"},
    "ce_registry_by_type": {"course": 47861},
    "deleted_resources": 0, "provisional_resources": 0, "unattributed": 1,
}


def test_the_printed_remainder_is_only_called_gated_when_it_is(capsys):
    """The claim in the output, not just in the dict. This is what a reader
    sees, and it was asserting "the gated community" whenever exactly one
    community failed — for any reason."""
    probe.print_registry({**REGISTRY_SHAPE,
                          "secured_communities": ["chaffeycollege"],
                          "failed_communities": []})
    assert "the gated community: chaffeycollege" in capsys.readouterr().out


def test_a_failed_community_is_not_described_as_gated(capsys):
    probe.print_registry({**REGISTRY_SHAPE,
                          "secured_communities": [],
                          "failed_communities": ["fdoe"]})
    out = capsys.readouterr().out
    assert "did not answer" in out and "fdoe" in out
    assert "gated" not in out


def test_two_gated_communities_are_not_attributed_to_one(capsys):
    probe.print_registry({**REGISTRY_SHAPE,
                          "secured_communities": ["chaffeycollege", "another"],
                          "failed_communities": []})
    assert "not attributable to one" in capsys.readouterr().out

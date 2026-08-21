"""What the server serves, which release is published, and what the page says.

Three claims that have each been wrong at least once, which is why each is now
measured as a matrix rather than asserted:

  * what separates 200 from 403 — a contact URL in the User-Agent, not
    identification and not automation
  * which OEWS release is current — searched for, because `www.bls.gov` answers
    a request for a missing file with 200 and an HTML page, not a 404
  * that the document says what the probe measured, and not more

Parsing and coverage are in `tests/test_probe_bls.py`.
"""

from __future__ import annotations

import re

from etl import bls_access as access
from etl import probe_bls as probe
from tests.bls_fixtures import page, row, serve


# --------------------------------------------------------------------------
# access
# --------------------------------------------------------------------------

def test_a_refused_download_is_recorded_not_dropped(monkeypatch):
    serve(monkeypatch, page(row("13-2011")))
    monkeypatch.setattr(probe, "crosswalk_soc", lambda: set())
    monkeypatch.setattr(access, "attempt",
                        lambda url, agent=None: {"status": 200 if agent else 403})
    monkeypatch.setattr(access, "head", lambda url: {
        "status": 403, "is_file": False, "reason": "Forbidden"})
    result = probe.probe(quiet=True)
    assert result["oews"]["release"] is None
    assert result["oews"]["years_tried"], "the years tried are not recorded"


def test_the_head_request_reads_size_without_downloading(monkeypatch):
    seen = []
    class R:
        status = 200
        headers = {"content-length": "39224418",
                   "content-type": "application/x-zip-compressed"}
        def __enter__(self): return self
        def __exit__(self, *a): return False
        # `read()` even though HEAD does not use it: the GET fallback path
        # would hit `AttributeError` here rather than failing with a message
        # about the thing under test.
        def read(self): return b""
    monkeypatch.setattr(access.urllib.request, "urlopen",
                        lambda rq, *a, **k: (seen.append(rq.get_method()), R())[1])
    got = access.head("https://x/big.zip")
    assert seen == ["HEAD"], "downloaded the file to find its size"
    assert got["bytes"] == 39224418
    assert got["is_file"] is True


# --------------------------------------------------------------------------
# the OEWS release — searched for, because 200 does not mean "it is there"
# --------------------------------------------------------------------------

def serve_releases(monkeypatch, published: set[str]) -> list[str]:
    """bls.gov as it actually behaves: 200 + text/html for a file it lacks."""
    asked = []
    def fake_head(url):
        asked.append(url)
        yy = url.split("oesm")[1][:2]
        if yy in published:
            return {"status": 200, "content_type": "application/x-zip-compressed",
                    "bytes": 1234, "is_file": True}
        return {"status": 200, "content_type": "text/html",
                "bytes": None, "is_file": False}
    monkeypatch.setattr(access, "head", fake_head)
    return asked


def test_a_soft_404_is_not_reported_as_a_published_release(monkeypatch):
    """The defect this section exists for. `www.bls.gov` answers a request for
    a file it does not have with 200 and an HTML page, so a status check alone
    reports next year's unpublished release as available — with a blank size
    column that reads as a formatting glitch rather than as absence."""
    serve_releases(monkeypatch, published={"25"})
    got = access.oews_latest(2026)
    assert got["release"] == "May 2025", "the 200 + text/html year was accepted"
    assert "26" in got["years_tried"], "2026 was never tried"


def test_content_type_is_what_decides_not_status(monkeypatch):
    """Run through `head` itself against a response shaped like the real
    soft-404: 200, `text/html`, no content-length.

    The previous version built the dict it then asserted on and never called
    any code under test — a tautology dressed as a guard, which is the same
    defect class as the claims this file exists to keep honest.
    """
    class Response:
        status = 200
        headers = {"content-type": "text/html"}
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b""
    monkeypatch.setattr(access.urllib.request, "urlopen", lambda *a, **k: Response())

    got = access.head("https://www.bls.gov/oes/special-requests/oesm26nat.zip")
    assert got["status"] == 200, "the server did answer 200"
    assert got["is_file"] is False, "200 + text/html is not a published file"
    assert got["bytes"] is None


def test_a_half_published_release_is_not_reported_as_current(monkeypatch):
    """A year with the national file up and the metro file not yet would
    otherwise be reported as the current release with a geography missing."""
    def fake_head(url):
        complete = "oesm24" in url or url.endswith("oesm25nat.zip")
        return {"status": 200, "bytes": 1, "is_file": complete,
                "content_type": "application/x-zip-compressed" if complete else "text/html"}
    monkeypatch.setattr(access, "head", fake_head)
    got = access.oews_latest(2026)
    assert got["release"] == "May 2024"
    assert set(got["geographies"]) == set(access.GEOGRAPHY_NAMES.values())


def test_the_search_gives_up_rather_than_walking_back_forever(monkeypatch):
    asked = serve_releases(monkeypatch, published=set())
    got = access.oews_latest(2026)
    assert got["release"] is None
    assert len(got["years_tried"]) == access.OEWS_LOOKBACK + 1
    assert len(asked) == len(got["years_tried"]) * len(access.OEWS_GEOGRAPHIES)


def strings_in(value, seen=None):
    """Every string reachable from a module-level value, at any nesting.

    Scanning only module-level `str` values missed a year baked into a list,
    a dict, a tuple or an f-string that had already been evaluated — all of
    which are how a URL constant is usually written.

    `seen` holds the id of each CONTAINER entered, and holds a reference to it
    for as long as the walk runs. Recording ids alone is unsound: a temporary
    freed during the walk lets its address be reused, and the next object at
    that address is then skipped as "already seen" — silently, and only
    sometimes. Keeping the object alive makes the id stable for the walk.
    Strings are not recorded at all; a repeated string is worth yielding twice
    and cheaper than tracking.
    """
    seen = seen if seen is not None else {}
    if isinstance(value, str):
        yield value
        return
    if id(value) in seen:
        return
    seen[id(value)] = value
    if isinstance(value, dict):
        for key, item in value.items():
            yield from strings_in(key, seen)
            yield from strings_in(item, seen)
    elif isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            yield from strings_in(item, seen)


def test_the_release_year_is_not_written_down_anywhere():
    """The previous version hard-coded `oesm23*` and was two releases stale
    while looking measured, because the sizes beside it were real.

    Checked against the module's VALUES, not its source text: the comment
    explaining why `oesm23` was wrong is not itself a hard-coded year. And
    reached through containers, because `OEWS = {"national": ".../oesm23nat.zip"}`
    — the shape this constant actually had — is a dict, not a module-level
    string, and a scan of `str` values alone would have passed on it.
    """
    # EVERY module that could hold one, not just `probe_bls`. Splitting the
    # access layer out moved `OEWS_URL` to `etl/bls_access.py` while this guard
    # went on scanning `vars(probe_bls)` — where the constant no longer was. It
    # found nothing and passed on an empty set: the exact vacuous pass it exists
    # to prevent, introduced by a refactor that did not follow the constant.
    #
    # `__builtins__` is a module-sized dict that no constant of ours lives in,
    # and walking it is the bulk of this test's work. Dunders are skipped.
    constants = {f"{owner.__name__}.{name}": value
                 for owner in (probe, access)
                 for name, value in vars(owner).items()
                 if not name.startswith("__")}
    baked = sorted({name for name, value in constants.items()
                    for text in strings_in(value)
                    if re.search(r"oesm\d\d", text)})
    assert not baked, f"a release year is hard-coded in {baked} — it will go stale"
    assert "{yy}" in access.OEWS_URL, "the release year is not a parameter"
    # The scan must actually SEE the URL constant. Without this, moving
    # `OEWS_URL` to a third module turns the check above into a scan of two
    # modules that no longer contain it — which is exactly how it broke when
    # the access layer was split out.
    assert any(name.endswith(".OEWS_URL") for name in constants), (
        "OEWS_URL is in neither scanned module, so this guard is looking at "
        "nothing — follow the constant or add its module here")


def test_a_year_hidden_in_a_container_is_found():
    """The guard above, tested on the shape that defeated its first version:
    `OEWS = {"national": ".../oesm23nat.zip"}` is a dict, not a module-level
    string, and a scan of `str` values alone passed on it.

    The first assertion used to be `list(strings_in(...)) and any(...)`, which
    says nothing the `any` does not — a non-empty list is implied by a match.
    """
    assert any(re.search(r"oesm\d\d", s)
               for s in strings_in({"national": "https://x/oesm23nat.zip"}))
    assert any(re.search(r"oesm\d\d", s)
               for s in strings_in([("a", ["https://x/oesm24st.zip"])]))
    # A cycle must terminate rather than recurse forever.
    cycle = {"a": ["https://x/oesm25nat.zip"]}
    cycle["self"] = cycle
    assert any(re.search(r"oesm\d\d", s) for s in strings_in(cycle))


# --------------------------------------------------------------------------
# the User-Agent claim — measured, not asserted
# --------------------------------------------------------------------------

def test_the_two_requests_differ_in_the_header_not_the_host(monkeypatch):
    """A field called `unidentified_request` used to send the identifying
    header and vary the host instead — so the claim the document credits to the
    probe was never made by it. Same URL, two headers."""
    seen = []

    class R:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b""

    def urlopen(request, *a, **k):
        seen.append((request.full_url, request.get_header("User-agent")))
        return R()

    monkeypatch.setattr(access.urllib.request, "urlopen", urlopen)
    access.attempt(access.IDENTITY_TEST_FALLBACK, access.USER_AGENT)
    access.attempt(access.IDENTITY_TEST_FALLBACK, None)

    assert seen[0][0] == seen[1][0], "the two requests went to different URLs"
    assert seen[0][1] == access.USER_AGENT
    assert seen[1][1] is None, "the anonymous request still sent a User-Agent"


def test_every_agent_variant_is_reported(monkeypatch):
    """A matrix, not a yes/no. The claim has been wrong twice — once sending
    the identifying header from a field called `unidentified_request`, once
    calling urllib's default `Python-urllib/3.x` anonymous."""
    serve(monkeypatch, page(row("13-2011")))
    monkeypatch.setattr(probe, "crosswalk_soc", lambda: set())
    monkeypatch.setattr(access, "head", lambda url: {"status": 200, "bytes": 1, "is_file": True})
    monkeypatch.setattr(access, "attempt",
                        lambda url, agent=None: {"status": 200 if agent and "+http" in agent else 403})
    got = probe.probe(quiet=True)["user_agent_test"]["results"]
    assert set(got) == set(access.AGENTS)
    served = {label for label, r in got.items() if r["status"] == 200}
    carries_url = {label for label, agent in access.AGENTS.items()
                   if agent and "+http" in agent}
    assert served == carries_url


def test_the_matrix_can_tell_a_contact_url_from_an_allowlisted_string():
    """The claim is that a **contact URL** decides it. Five agents — ours served,
    four others refused — is equally consistent with "this exact string is
    allowlisted"; one served sample cannot separate the two.

    So the matrix must hold the contact URL constant and vary everything around
    it. Without all of these, the document's claim outruns its evidence again,
    which is the failure this section has already had twice.
    """
    with_url = [a for a in access.AGENTS.values() if a and "+http" in a]
    assert len(with_url) >= 2, \
        "only one agent carries a contact URL — cannot distinguish it from an allowlist"

    names = {a.split("(+http")[0].strip() for a in with_url}
    assert len(names) >= 3, \
        "every contact-URL agent uses the same product name — the name is not varied"
    assert "" in names, "no bare contact URL with no product name at all"
    assert any(access.BROWSER in a for a in with_url), \
        "the refused browser string is never retried with a contact URL appended"
    assert access.BROWSER in access.AGENTS.values(), \
        "the browser string without a contact URL is the control, and it is gone"


def test_every_request_goes_to_the_same_url(monkeypatch):
    """Asserted through `probe()`, not by calling `attempt()` by hand — the
    defect being guarded is in how the set is *constructed*, and a test that
    builds it itself cannot see it."""
    serve(monkeypatch, page(row("13-2011")))
    monkeypatch.setattr(probe, "crosswalk_soc", lambda: set())
    monkeypatch.setattr(access, "head", lambda url: {"status": 200, "bytes": 1, "is_file": True})
    called = []
    monkeypatch.setattr(access, "attempt",
                        lambda url, agent=None: (called.append((url, agent)),
                                                 {"status": 200})[1])
    probe.probe(quiet=True)
    urls = {url for url, _ in called}
    assert len(urls) == 1, f"the requests went to different URLs: {urls}"
    assert {agent for _, agent in called} == set(access.AGENTS.values())
    assert urls.pop().startswith("https://www.bls.gov"), "not the host the claim is about"


def test_the_default_agent_is_not_called_anonymous():
    """`attempt(url, None)` sends `Python-urllib/3.x`, not nothing. Labelling
    that arm "anonymous" is what made the previous version's claim untrue."""
    assert access.AGENTS["library default"] is None
    assert "anonymous" not in " ".join(access.AGENTS).lower()
    assert "" in access.AGENTS.values(), "no empty-string arm — the closest to absent"


def test_the_identity_test_page_is_verified_by_content_not_by_status(monkeypatch):
    """bls.gov answers a request for a missing file with 200 and text/html —
    the behaviour `head()` exists to see through. A URL pinned to one release
    year becomes a probe of an error page the year that release is retired,
    and every row of the header matrix still reads "served": the claim goes on
    being confirmed by a page that is not the page.

    The previous fix checked `status == 200`, which is the exact question this
    module says you must not ask on this host. It is a CONTENT check now, and
    this test proves it by serving a 200 that is not the page.
    """
    asked = []

    def fetch(url):
        asked.append(url)
        if "2031" in url:
            return "<title>Page not found</title>"      # 200, and not the page
        return "<title>May 2030 National Occupational Employment and Wage Estimates</title>"

    monkeypatch.setattr(access, "fetch", fetch)

    # A 200 that is not the OEWS page must NOT be accepted.
    url, verified = access.identity_test_url({"release": "May 2031"})
    assert url == access.IDENTITY_TEST_FALLBACK
    # BOTH are checked: the derived URL, and then the fallback it lands on.
    # The fallback is a pinned year, so it is the same hazard one step later —
    # substituting it unchecked would put the whole matrix on an error body.
    assert asked == ["https://www.bls.gov/oes/2031/may/oes_nat.htm",
                     access.IDENTITY_TEST_FALLBACK], asked
    assert verified is True, "the fallback answered with the marker, so it is verified"

    # The real page is.
    asked.clear()
    assert access.identity_test_url({"release": "May 2030"})[0] == \
        "https://www.bls.gov/oes/2030/may/oes_nat.htm"


def test_the_identity_test_falls_back_when_the_page_cannot_be_read(monkeypatch):
    """An offline run, or a release whose www page has not appeared, still has
    something to report rather than probing a URL nothing answers."""
    def unreachable(url):
        raise RuntimeError("unreachable")

    monkeypatch.setattr(access, "fetch", unreachable)
    assert access.identity_test_url({"release": "May 2031"})[0] == access.IDENTITY_TEST_FALLBACK
    assert access.identity_test_url({})[0] == access.IDENTITY_TEST_FALLBACK
    assert access.identity_test_url({"release": None})[0] == access.IDENTITY_TEST_FALLBACK


def test_head_falling_back_to_get_when_the_server_refuses_head(monkeypatch):
    """A 405 is the server's opinion about a METHOD. Recorded as
    `is_file: False` it becomes a fact about the DATA — a published release
    read as unpublished, and `oews_latest` then walks back a year looking for
    something that was there all along."""
    seen = []

    class Response:
        status = 200
        headers = {"content-type": "application/zip", "content-length": "10"}
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b"0123456789"

    def urlopen(request, timeout=None):
        seen.append(request.get_method())
        if request.get_method() == "HEAD":
            raise access.urllib.error.HTTPError(
                request.full_url, 405, "Method Not Allowed", {}, None)
        return Response()

    monkeypatch.setattr(access.urllib.request, "urlopen", urlopen)
    got = access.head("https://www.bls.gov/oes/special-requests/oesm24nat.zip")
    assert seen == ["HEAD", "GET"], seen
    assert got["is_file"] is True, got
    assert got["method"] == "GET", got


def test_the_fallback_url_is_verified_too_and_reported_when_it_is_not(monkeypatch):
    """The fallback is a pinned 2023 URL — exactly the thing this function
    exists to stop trusting. The year that release is retired it becomes a soft
    404, every row of the matrix reads "served" against an error body, and the
    User-Agent finding is confirmed by a page that is not the page.

    Falling back is still right; an offline run needs something to report. What
    cannot happen is falling back SILENTLY.
    """
    monkeypatch.setattr(access, "fetch", lambda url: "<title>Page not found</title>")
    url, verified = access.identity_test_url({"release": "May 2031"})
    assert url == access.IDENTITY_TEST_FALLBACK
    assert verified is False, "the fallback was substituted without being checked"

    marker = "May 2023 National Occupational Employment and Wage Estimates"
    monkeypatch.setattr(access, "fetch", lambda url: f"<title>{marker}</title>")
    url, verified = access.identity_test_url({})
    assert url == access.IDENTITY_TEST_FALLBACK
    assert verified is True, "a verified fallback should say so"


def test_an_unverified_page_is_flagged_in_the_output(monkeypatch, capsys):
    """The flag has to reach the reader. The JSON carries `url_verified` and
    the printed matrix carries a warning above the rows it qualifies."""
    serve(monkeypatch, page(row("13-2011")))
    monkeypatch.setattr(access, "oews_latest",
                        lambda year: {"release": "May 2030", "years_tried": ["30"],
                                      "geographies": {}})
    monkeypatch.setattr(access, "identity_test_url",
                        lambda oews: ("https://www.bls.gov/oes/2023/may/oes_nat.htm",
                                      False))
    monkeypatch.setattr(access, "attempt", lambda url, agent=None: {"status": 200})
    monkeypatch.setattr(probe, "crosswalk_soc", lambda: set())

    result = probe.probe()
    assert result["user_agent_test"]["url_verified"] is False, result
    printed = capsys.readouterr().out
    assert "could NOT be confirmed" in printed, printed

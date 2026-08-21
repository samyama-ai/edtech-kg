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

import json
import pathlib
import re

import pytest

from etl import probe_bls as probe
from tests.bls_fixtures import HEADER, page, row, serve

DOCUMENT = (pathlib.Path(__file__).resolve().parents[1]
            / "docs" / "sources" / "bls-occupation.md")


# --------------------------------------------------------------------------
# access
# --------------------------------------------------------------------------

def test_a_blocked_geography_is_recorded_not_dropped(monkeypatch):
    serve(monkeypatch, page(row("13-2011")))
    monkeypatch.setattr(probe, "crosswalk_soc", lambda: set())
    monkeypatch.setattr(probe, "attempt",
                        lambda url, agent=None: {"status": 200 if agent else 403})
    monkeypatch.setattr(probe, "head", lambda url: {
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
    monkeypatch.setattr(probe.urllib.request, "urlopen",
                        lambda rq, *a, **k: (seen.append(rq.get_method()), R())[1])
    got = probe.head("https://x/big.zip")
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
    monkeypatch.setattr(probe, "head", fake_head)
    return asked


def test_a_soft_404_is_not_reported_as_a_published_release(monkeypatch):
    """The defect this section exists for. `www.bls.gov` answers a request for
    a file it does not have with 200 and an HTML page, so a status check alone
    reports next year's unpublished release as available — with a blank size
    column that reads as a formatting glitch rather than as absence."""
    serve_releases(monkeypatch, published={"25"})
    got = probe.oews_latest(2026)
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
    monkeypatch.setattr(probe.urllib.request, "urlopen", lambda *a, **k: Response())

    got = probe.head("https://www.bls.gov/oes/special-requests/oesm26nat.zip")
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
    monkeypatch.setattr(probe, "head", fake_head)
    got = probe.oews_latest(2026)
    assert got["release"] == "May 2024"
    assert set(got["geographies"]) == set(probe.GEOGRAPHY_NAMES.values())


def test_the_search_gives_up_rather_than_walking_back_forever(monkeypatch):
    asked = serve_releases(monkeypatch, published=set())
    got = probe.oews_latest(2026)
    assert got["release"] is None
    assert len(got["years_tried"]) == probe.OEWS_LOOKBACK + 1
    assert len(asked) == len(got["years_tried"]) * len(probe.OEWS_GEOGRAPHIES)


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
    # `__builtins__` is a module-sized dict that no constant of ours lives in,
    # and walking it is the bulk of this test's work. Dunders are skipped.
    constants = {name: value for name, value in vars(probe).items()
                 if not name.startswith("__")}
    baked = sorted({name for name, value in constants.items()
                    for text in strings_in(value)
                    if re.search(r"oesm\d\d", text)})
    assert not baked, f"a release year is hard-coded in {baked} — it will go stale"
    assert "{yy}" in probe.OEWS_URL, "the release year is not a parameter"


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
# the document says what the probe measured
# --------------------------------------------------------------------------

def test_the_absent_codes_are_named_on_the_page_not_only_in_json():
    r"""The page used to say the thirteen were "named in the probe's --json
    output" — a reference a reader cannot check without a network and a
    crosswalk file. The codes belong on the page.

    The page's own two statements are compared against each other: the count
    in the table, and the codes in the block below it. A literal set of
    thirteen codes in this file would be a third copy of a measurement that
    changes with every projections release — the exact staleness this file
    guards against elsewhere, reintroduced by its own test.

    `\b\d{2}-\d{4}\b` matches any NN-NNNN, so the codes are read from the
    fenced block rather than from anywhere on the page: a phone fragment or a
    page range elsewhere would otherwise make the count agree by accident.
    """
    text = DOCUMENT.read_text()
    stated = re.search(r"\*\*Absent outright\*\*\s*\|\s*\*\*(\d+)\*\*", text)
    assert stated, "the page no longer states an absent-outright count"

    block = re.search(r"```\n((?:\s*\d{2}-\d{4}\s*)+)```", text)
    assert block, (
        "the page states a count of absent occupations but does not list them; "
        "a reader cannot see which occupations we cannot answer for")
    listed = set(re.findall(r"\b\d{2}-\d{4}\b", block.group(1)))
    assert len(listed) == int(stated.group(1)), (
        f"the page says {stated.group(1)} occupations are absent outright and "
        f"lists {len(listed)}. Re-run the probe and update both.")


def test_the_probe_prints_the_absent_codes_and_does_not_only_count_them(monkeypatch, capsys):
    serve(monkeypatch, page(row("13-2011")))
    monkeypatch.setattr(probe, "crosswalk_soc", lambda: {"13-2011", "21-1011"})
    monkeypatch.setattr(probe, "head",
                        lambda url: {"status": 200, "bytes": 1, "is_file": True})
    monkeypatch.setattr(probe, "attempt", lambda url, agent=None: {"status": 200})
    probe.probe()
    printed = capsys.readouterr().out
    assert "21-1011" in printed, "the absent code was counted but never named"


def test_the_agent_table_in_the_document_has_a_row_per_agent():
    """A matrix that grows in the probe and not on the page is how the claim
    got ahead of the evidence the last two times."""
    text = DOCUMENT.read_text()
    heading = "| User-Agent |"
    # Split blindly and a renamed heading raises IndexError with nothing in it
    # to say which table moved.
    assert heading in text, f"no {heading!r} table in {DOCUMENT.name}"
    block = text.split(heading)[1].split("\n\n")[0]
    rows = [line for line in block.splitlines()
            if line.startswith("|") and not set(line) <= set("|-: ")]
    assert len(rows) == len(probe.AGENTS), \
        f"the document shows {len(rows)} agents; the probe sends {len(probe.AGENTS)}"


def test_the_document_states_the_release_it_was_generated_against():
    text = DOCUMENT.read_text()
    assert re.search(r"\*\*May 20\d\d release\*\*", text), "no OEWS release vintage stated"
    # Whitespace-collapsed: the document is hard-wrapped, so a phrase test that
    # matches the raw text is really testing where the line breaks fall.
    flat = " ".join(text.split()).lower()
    # The CLAIM, not one phrasing of it. "found by the probe rather than
    # written down" is one sentence a rewrite would innocently change while
    # saying exactly the same thing, and a test that fails on that teaches
    # people to edit the test rather than read it.
    assert "probe" in flat and any(
        phrase in flat for phrase in
        ("rather than written down", "rather than remembered",
         "found rather than", "not written down", "not hard-coded")), \
        "the vintage reads as remembered rather than measured"
    # The reason a status check is not enough has to survive on the page, or
    # the next person restores the cheaper check.
    assert "text/html" in flat and "404" in flat, \
        "the soft-404 behaviour that makes status insufficient is not recorded"


def test_an_unreachable_source_exits_two(monkeypatch):
    monkeypatch.setattr(probe, "projections",
                        lambda: (_ for _ in ()).throw(RuntimeError("dns")))
    assert probe.main([]) == 2


def test_a_malformed_source_exits_three(monkeypatch):
    monkeypatch.setattr(probe, "projections",
                        lambda: (_ for _ in ()).throw(probe.MalformedSource("layout")))
    assert probe.main([]) == 3


def test_json_output_carries_a_timestamp(monkeypatch, capsys):
    serve(monkeypatch, page(row("13-2011")))
    monkeypatch.setattr(probe, "crosswalk_soc", lambda: set())
    monkeypatch.setattr(probe, "head", lambda url: {"status": 200, "bytes": 1, "is_file": True})
    monkeypatch.setattr(probe, "attempt",
                        lambda url, agent=None: {"status": 200 if agent else 403})
    assert probe.main(["--json"]) == 0
    assert "retrieved_at" in json.loads(capsys.readouterr().out)


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

    monkeypatch.setattr(probe.urllib.request, "urlopen", urlopen)
    probe.attempt(probe.IDENTITY_TEST_FALLBACK, probe.USER_AGENT)
    probe.attempt(probe.IDENTITY_TEST_FALLBACK, None)

    assert seen[0][0] == seen[1][0], "the two requests went to different URLs"
    assert seen[0][1] == probe.USER_AGENT
    assert seen[1][1] is None, "the anonymous request still sent a User-Agent"


def test_every_agent_variant_is_reported(monkeypatch):
    """A matrix, not a yes/no. The claim has been wrong twice — once sending
    the identifying header from a field called `unidentified_request`, once
    calling urllib's default `Python-urllib/3.x` anonymous."""
    serve(monkeypatch, page(row("13-2011")))
    monkeypatch.setattr(probe, "crosswalk_soc", lambda: set())
    monkeypatch.setattr(probe, "head", lambda url: {"status": 200, "bytes": 1, "is_file": True})
    monkeypatch.setattr(probe, "attempt",
                        lambda url, agent=None: {"status": 200 if agent and "+http" in agent else 403})
    got = probe.probe(quiet=True)["user_agent_test"]["results"]
    assert set(got) == set(probe.AGENTS)
    served = {label for label, r in got.items() if r["status"] == 200}
    carries_url = {label for label, agent in probe.AGENTS.items()
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
    with_url = [a for a in probe.AGENTS.values() if a and "+http" in a]
    assert len(with_url) >= 2, \
        "only one agent carries a contact URL — cannot distinguish it from an allowlist"

    names = {a.split("(+http")[0].strip() for a in with_url}
    assert len(names) >= 3, \
        "every contact-URL agent uses the same product name — the name is not varied"
    assert "" in names, "no bare contact URL with no product name at all"
    assert any(probe.BROWSER in a for a in with_url), \
        "the refused browser string is never retried with a contact URL appended"
    assert probe.BROWSER in probe.AGENTS.values(), \
        "the browser string without a contact URL is the control, and it is gone"


def test_every_request_goes_to_the_same_url(monkeypatch):
    """Asserted through `probe()`, not by calling `attempt()` by hand — the
    defect being guarded is in how the set is *constructed*, and a test that
    builds it itself cannot see it."""
    serve(monkeypatch, page(row("13-2011")))
    monkeypatch.setattr(probe, "crosswalk_soc", lambda: set())
    monkeypatch.setattr(probe, "head", lambda url: {"status": 200, "bytes": 1, "is_file": True})
    called = []
    monkeypatch.setattr(probe, "attempt",
                        lambda url, agent=None: (called.append((url, agent)),
                                                 {"status": 200})[1])
    probe.probe(quiet=True)
    urls = {url for url, _ in called}
    assert len(urls) == 1, f"the requests went to different URLs: {urls}"
    assert {agent for _, agent in called} == set(probe.AGENTS.values())
    assert urls.pop().startswith("https://www.bls.gov"), "not the host the claim is about"


def test_the_default_agent_is_not_called_anonymous():
    """`attempt(url, None)` sends `Python-urllib/3.x`, not nothing. Labelling
    that arm "anonymous" is what made the previous version's claim untrue."""
    assert probe.AGENTS["library default"] is None
    assert "anonymous" not in " ".join(probe.AGENTS).lower()
    assert "" in probe.AGENTS.values(), "no empty-string arm — the closest to absent"


def test_a_wanted_field_matching_no_column_is_a_layout_change(monkeypatch):
    """Reporting 0 of 832 for a renamed column reads as BLS having stopped
    publishing it."""
    serve(monkeypatch, page(row("13-2011")).replace("Median Annual Wage 2024",
                                                    "Typical Pay 2024"))
    with pytest.raises(probe.MalformedSource, match="no column matches"):
        probe.projections()


def test_a_repeated_code_cannot_push_coverage_above_the_count(monkeypatch):
    """Fields were counted per row while occupations were deduped, so a
    repeated code printed over 100%."""
    serve(monkeypatch, page(row("13-2011"), row("13-2011")))
    result = probe.projections()
    assert result["occupations"] == 1
    assert all(v <= result["occupations"] for v in result["field_present"].values())


def test_two_columns_matching_one_field_are_counted_once(monkeypatch):
    """A second published column containing a WANTED substring — a "Median
    Annual Wage 2023" beside the 2024 one — counted twice and pushed that
    field's coverage above the occupation count."""
    header = HEADER.replace("<TH>Median Annual Wage 2024</TH>",
                            "<TH>Median Annual Wage 2024</TH>"
                            "<TH>Median Annual Wage 2023</TH>")
    body = row("13-2011").replace("<TD>$50,000</TD>",
                                  "<TD>$50,000</TD><TD>$48,000</TD>")
    serve(monkeypatch, "<html>" + header + body + "</html>")
    result = probe.projections()
    assert result["occupations"] == 1
    assert result["field_present"]["Median Annual Wage"] == 1, "counted per column"


def test_the_identity_test_page_follows_the_release_rather_than_a_pinned_year():
    """bls.gov answers a request for a missing file with 200 and text/html —
    the behaviour `head()` exists to see through. A URL pinned to one release
    year therefore becomes a probe of an error page the year that release is
    retired, and every row of the header matrix still reads "served": the
    claim goes on being confirmed by a page that is not the page.
    """
    asked = []

    def head(url):
        asked.append(url)
        return {"status": 200, "bytes": 1000, "is_file": False}

    original = probe.head
    probe.head = head
    try:
        got = probe.identity_test_url({"release": "May 2031"})
    finally:
        probe.head = original
    assert got == "https://www.bls.gov/oes/2031/may/oes_nat.htm", got
    assert asked == [got], asked


def test_the_identity_test_falls_back_when_the_derived_page_is_not_served():
    """An offline run, or a release whose www page has not appeared, still has
    something to report rather than probing a URL nothing answers."""
    original = probe.head
    probe.head = lambda url: {"status": 404, "bytes": 0, "is_file": False}
    try:
        assert probe.identity_test_url({"release": "May 2031"}) == \
            probe.IDENTITY_TEST_FALLBACK
        assert probe.identity_test_url({}) == probe.IDENTITY_TEST_FALLBACK
        assert probe.identity_test_url({"release": None}) == probe.IDENTITY_TEST_FALLBACK
    finally:
        probe.head = original

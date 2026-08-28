"""Which departments answer a machine, and how that is classified — #50.

No test reaches a department. `reach` takes an opener, so every branch is
exercised by handing it a callable that raises what a real site raises.
"""

from __future__ import annotations

import json
import pathlib
import re
import ssl
import urllib.error

import pytest

from etl import state_access as access

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs" / "sources" / "state-access.md"
RECORD = ROOT / "docs" / "sources" / "state-access-measured.json"


@pytest.fixture(scope="module")
def record() -> dict:
    return json.loads(RECORD.read_text())


class Response:
    def __init__(self, status=200): self.status = status
    def __enter__(self): return self
    def __exit__(self, *a): return False


def raiser(exc):
    def opener(url, timeout=25): raise exc
    return opener


def test_a_served_page_is_served():
    assert access.reach("https://x", lambda u, timeout=25: Response()) == {
        "outcome": "served", "detail": "HTTP 200"}


def test_a_403_is_a_refusal():
    got = access.reach("https://x", raiser(
        urllib.error.HTTPError("https://x", 403, "Forbidden", {}, None)))
    assert got == {"outcome": "refused", "detail": "HTTP 403"}


def test_a_redirect_that_never_settles_is_not_a_refusal():
    """California answers 303 indefinitely.

    urllib raises HTTPError for it, so the first version filed California
    beside Florida and Virginia — a different problem with a different
    remedy, reported as the same one.
    """
    got = access.reach("https://x", raiser(
        urllib.error.HTTPError("https://x", 303, "See Other", {}, None)))
    assert got["outcome"] == "redirect_loop"


def test_a_certificate_failure_is_named_as_one():
    """New York. Fixed by the department, not negotiated with."""
    got = access.reach("https://x", raiser(urllib.error.URLError(
        ssl.SSLCertVerificationError("CERTIFICATE_VERIFY_FAILED"))))
    assert got["outcome"] == "tls_failure"


def test_an_unexpected_failure_is_not_filed_as_a_refusal():
    """A local network problem must not put a department in the blocked column.

    `refused` means somebody configured a refusal. Anything this code does not
    recognise says so instead of borrowing that meaning.
    """
    got = access.reach("https://x", raiser(RuntimeError("boom")))
    assert got == {"outcome": "unreachable", "detail": "RuntimeError"}


def test_robots_txt_is_fetched_for_every_department():
    """The load-bearing half of the finding.

    A site that serves its homepage and refuses robots.txt is refusing before
    any policy is consulted. Surveying only homepages could not see that, and
    the issue's question cannot be answered without it.
    """
    asked = []

    def opener(url, timeout=25):
        asked.append(url)
        return Response()

    access.survey(opener)
    assert len(asked) == 2 * len(access.DEPARTMENTS)
    assert all(f"{root}/robots.txt" in asked
               for root in access.DEPARTMENTS.values())


@pytest.mark.parametrize("home,robots,verdict", [
    ("served", "served", "automatable"),
    ("served", "refused", "request-based"),
    ("refused", "refused", "manual-only"),
    ("redirect_loop", "redirect_loop", "manual-only"),
    ("tls_failure", "tls_failure", "manual-only"),
])
def test_the_verdict_follows_from_both_halves(home, robots, verdict):
    """Serving a homepage is not enough to be called automatable.

    A department that declines to publish a policy to a machine has declined.
    Reading its files anyway is a decision this repo should not make silently,
    so that case is `request-based` and not `automatable`.
    """
    assert access.recommendation(
        {"homepage": {"outcome": home}, "robots_txt": {"outcome": robots}}) == verdict


def test_the_page_and_the_record_agree_on_every_department(record):
    """Both directions.

    Every department in the record appears in the page's table with the
    verdict the record holds, and the page names no department the record
    does not.
    """
    page = PAGE.read_text()
    rows = dict(re.findall(r"^\| ([A-Za-z ]+) — \S+ \|.*\| \*\*([a-z-]+)\*\* \|$",
                           page, re.M))
    assert rows, "the page no longer carries a department table"
    for name, one in record["departments"].items():
        state = name.split(" — ")[0]
        assert state in rows, f"{state} is measured but not on the page"
        assert rows[state] == one["recommendation"], f"{state} verdict differs"
    assert set(rows) == {n.split(" — ")[0] for n in record["departments"]}


def test_the_page_states_the_date_the_record_holds(record):
    claimed = re.search(r"Measured \*\*(\d{4}-\d{2}-\d{2})\*\*", PAGE.read_text())
    assert claimed and claimed.group(1) == record["retrieved_at"]


def test_the_page_says_robots_txt_is_what_answers_the_question():
    """The conclusion, not just the table.

    #50 asks whether a request could resolve the 403. The answer rests
    entirely on robots.txt being refused too, so the page has to say it.
    """
    # Whitespace-normalised. The page is hard-wrapped, so a phrase long enough
    # to be worth asserting on almost always spans a line break — and a
    # substring test against the raw text then fails for a reason that has
    # nothing to do with what the page says.
    page = re.sub(r"\s+", " ", PAGE.read_text().lower())
    assert "refusing it is not applying a crawler policy" in page
    assert "there is no user-agent to negotiate with" in page

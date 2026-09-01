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
    ("served", "absent", "automatable"),
    ("served", "refused", "request-based"),
    ("absent", "absent", "manual-only"),
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


def test_a_robots_txt_that_was_never_published_is_absent_not_refused():
    """404 is "there is no policy", which is the opposite of a refusal.

    This page's entire argument is that a 403 on `robots.txt` is a deliberate
    refusal. The reader could not tell that from "the file is not there":
    every non-3xx HTTPError became `refused`, so a department that simply
    never published one would be written up as "refusing before any policy is
    consulted" — and an optional file's absence would read as a block.

    Today's numbers do not move: Florida and Virginia both answered 403. This
    is about the next run.
    """
    for code in (404, 410):
        got = access.reach("https://x/robots.txt", raiser(
            urllib.error.HTTPError("https://x/robots.txt", code, "Not Found",
                                   {}, None)))
        assert got == {"outcome": "absent", "detail": f"HTTP {code}"}


def test_a_department_that_publishes_no_robots_txt_stays_automatable():
    """The failure this guards is a verdict flipping on a deletion.

    If Texas removed an empty `robots.txt`, the verdict would have gone from
    `automatable` to `request-based` and the page would have said Texas
    refuses it. Nothing was refused.
    """
    assert access.recommendation({"homepage": {"outcome": "served"},
                                  "robots_txt": {"outcome": "absent"}}) == "automatable"


def test_a_truncated_detail_says_it_is_truncated():
    """`unable to get local ` reads as the message, not as an excerpt."""
    assert access.brief("short") == "short"
    long_reason = "x" * 200
    assert access.brief(long_reason).endswith("…")
    assert len(access.brief(long_reason)) == 81


def test_the_page_counts_the_departments_the_record_counts(record):
    """The prose counts, not just the table rows.

    The page opened by saying automation is impossible for "three of five"
    departments while its own table and its own refresh section both said
    four. A reader takes the number from the sentence, and nothing checked it.
    """
    page = re.sub(r"\s+", " ", PAGE.read_text().lower())
    verdicts = [one["recommendation"] for one in record["departments"].values()]
    manual = sum(1 for v in verdicts if v != "automatable")
    spelled = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}
    total = spelled[len(verdicts)]

    assert f"for {spelled[manual]} of {total} departments it is not" in page
    assert f"{spelled[len(verdicts) - manual]} of {total} states is automatable" in page


def test_the_page_names_the_departments_that_actually_refuse(record):
    """"Refuses robots.txt" is a narrower claim than "cannot be automated".

    Four departments are manual-only; only two refuse anything. California
    answers a redirect loop and New York fails TLS — neither is refusing —
    so a page that named four here would be making an accusation the record
    does not support.
    """
    refusing = {name.split(" — ")[0].lower()
                for name, one in record["departments"].items()
                if one["robots_txt"]["outcome"] == "refused"}
    page = re.sub(r"\s+", " ", PAGE.read_text().lower())
    claimed = re.search(r"([a-z ]+?) refuse \*\*`robots.txt`\*\*", page)
    assert claimed, "the page no longer names who refuses robots.txt"
    named = {w.strip() for w in claimed.group(1).split(" and ") if w.strip()}
    assert named == refusing, f"page names {named}; the record refuses {refusing}"

"""Reading the Credential Engine Registry — fetching, paging, and sampling.

Split out of `etl/probe_registry.py` for #86: that file sat at 514 lines, over
the 500-line review limit, so every review touching it skipped it whole — and
the file it skipped was the one asserting the findings the Registry pages rest
on.

Split by SUBJECT rather than by length. This module is *how the Registry is
read*: the transport, the two exception types that separate a refusal from a
corrupt body, the total the API reports for a query, and how a sample of pages
is drawn from a population and described honestly. `probe_registry.py` is *what
the Registry holds* — the counts, what a resolvable prerequisite is, and the
tables.

The seam is worth stating because it is the one that keeps being crossed: the
sampling functions belong here, with fetching, because they decide which pages
are READ. What is found on those pages is the other module's subject.

`etl/probe_ctdl.py` reads the vocabulary rather than the Registry, but it
borrows this transport so that one place carries the User-Agent.

No third-party dependency, as with the other probes.
"""

from __future__ import annotations

import email.message
import json
import urllib.error
import urllib.parse
import urllib.request

from etl.identity import USER_AGENT

REGISTRY = "https://credentialengineregistry.org"

# The Registry serves 50 records a page and ignores a larger ask, so this is
# the source's number, not a tuning choice.
PER_PAGE = 50


class HttpStatus(RuntimeError):
    """A failed request that knows its own status code.

    The code used to be recovered by searching the exception text for "401",
    which a URL containing those digits would satisfy.
    """

    def __init__(self, code: int | None, url: str, detail: str = ""):
        super().__init__(f"{code or 'unreachable'} from {url}{detail}")
        self.code = code


class MalformedSource(Exception):
    """Reachable, but the body did not parse.

    `json.JSONDecodeError` subclasses `ValueError`, so a corrupt body used to
    exit under "refused" — the category reserved for figures we decline to
    report — rather than being flagged as a broken source.
    """


def _request(url: str, method: str, extract):
    """The request both callers share, and the one place a failure becomes
    `HttpStatus` so a status code survives as a number rather than as text in
    an exception message.

    `extract` is applied INSIDE the try, not by the caller. Reading the body is
    itself a network operation and can fail the same ways the connection can;
    doing it outside would let a mid-read error escape as a bare `URLError`
    while every other failure on this path arrives as `HttpStatus`.
    """
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT},
                                     method=method)
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return extract(response)
    except urllib.error.HTTPError as exc:
        raise HttpStatus(exc.code, url) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise HttpStatus(None, url, f" ({exc})") from exc


def get(url: str) -> bytes:
    """The body."""
    return _request(url, "GET", lambda response: response.read())


def head(url: str) -> email.message.Message:
    """The headers, without pulling the body.

    Split from `get()` rather than selected by a boolean, because a function
    whose return TYPE depends on an argument cannot be annotated honestly —
    `get(url, headers_only=True)` returned a header object and `get(url)`
    returned bytes, and the signature could say neither. One caller wanted
    headers; every other wanted bytes.
    """
    return _request(url, "HEAD", lambda response: response.headers)


def total(path: str, **params) -> int | str:
    """The `x-total` header for a search path.

    Returns the int, or the string `"secured"` when the community refuses an
    unauthenticated request. A gated community and an empty one are different
    facts and must not both print as a blank.
    """
    query = urllib.parse.urlencode({"per_page": 1, **params})
    try:
        headers = head(f"{REGISTRY}{path}?{query}")
    except HttpStatus as exc:
        # Three different facts, three different answers. "secured" is a claim
        # about the community; anything else is a claim about the request, and
        # print_registry must not label the remainder "the gated community"
        # when a community merely failed.
        if exc.code in (401, 403):
            return "secured"
        return f"error {exc.code}" if exc.code else "unreachable"
    # HTTPMessage looks up case-insensitively; dict() threw that away.
    raw = headers.get("x-total")
    if raw and str(raw).isdigit():
        return int(raw)
    # Answered, but not with a count. Degrading this to None reads as "unknown
    # population" and silently widens the sampling caveat instead of saying the
    # source is broken.
    return "no x-total header"


def parse(payload: bytes, what: str):
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise MalformedSource(f"{what} did not parse as JSON ({exc})") from exc


def describe(read: list[int], size: int, population: int | None) -> str:
    """How the sample was actually taken.

    Takes the pages that were *read*, never the pages that were planned. The
    two differ whenever the per-course cap ends the walk early, and describing
    the plan let the documents quote a reach the run did not have.
    """
    if not read:
        return "nothing was read"
    if not isinstance(population, int) or population <= 0:
        return (f"{len(read)} page(s) of {size} — population unknown, so the pages "
                f"could not be spread; biased toward whatever sorts first")

    total_pages = max(1, -(-population // PER_PAGE))
    # Coverage is pages x SIZE, not page count. `total_pages` is derived from
    # PER_PAGE, so reading that many SHORT pages does not reach the population:
    # at population=10 with a size of 5, one page is "every page" by count and
    # half the records by content, and this said "the whole population, not a
    # sample" about a 50% sample.
    covered = len(read) * size
    if len(read) >= total_pages and covered >= population:
        return f"every page — {population:,} records is the whole population, not a sample"
    if len(read) >= total_pages:
        return (f"{len(read)} page(s) of {size} — {covered:,} of {population:,} records. "
                f"Every page was read, but at {size} per page rather than {PER_PAGE}, so "
                f"this is not the whole population")
    if len(read) == 1:
        return (f"the first {size} of {population:,} records — a single page, so nothing "
                f"is spread; biased toward whatever sorts first")

    stride = read[1] - read[0]
    tail = total_pages - read[-1]
    return (f"{len(read)} pages of {size} at a stride of {stride}, reaching pages "
            f"{read[0]}-{read[-1]} of {total_pages:,} ({population:,} records); "
            f"the last {tail:,} pages are not sampled — deterministic, not random")


def sample_pages(wanted: int, population: int | None) -> tuple[list[int], int]:
    """Which pages to read, and how many records to ask for on each.

    Reading pages 1..N consecutively is not a sample of the Registry — it is a
    sample of whatever sorts first, which one publisher's bulk upload can
    dominate. Instead the pages are spread at a fixed stride across the whole
    result set, which is deterministic (so the figure is reproducible) and not
    concentrated at the head.

    **This function does not describe the sample.** It used to return a
    description as well, and that string went on being built and tested after
    `describe()` took over the live one — so the guards against claiming
    randomness, and against claiming a reach the walk did not have, were
    pointed at a string nobody printed. Selecting pages and describing a
    completed walk are different jobs, and only `describe()` does the second.
    """
    # Ceiling, not floor: --courses 130 asked for three pages' worth and got
    # two, silently sampling 100. The per-course cap trims the overshoot.
    pages_wanted = max(1, -(-wanted // PER_PAGE))
    # A request below one page reads one short page, not a full one. This is the
    # only place the size is decided; the fetch loop uses what it returns.
    size = min(PER_PAGE, wanted) if pages_wanted == 1 else PER_PAGE

    if not isinstance(population, int) or population <= 0:
        return list(range(1, pages_wanted + 1)), size

    total_pages = max(1, -(-population // PER_PAGE))
    if total_pages <= pages_wanted:
        return list(range(1, total_pages + 1)), size
    if pages_wanted == 1:
        return [1], size

    stride = total_pages // pages_wanted
    return [1 + i * stride for i in range(pages_wanted)], size

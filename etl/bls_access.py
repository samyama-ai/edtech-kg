"""Getting at bls.gov at all — the access layer, split from the measurement.

`etl/probe_bls.py` reached 534 lines, over the limit review will read, so the
file that carries the findings would have gone unexamined. Split by SUBJECT,
which is the standard this repo set when `test_schema_cypher.py` was split:
this module is how a request is made and whether a thing is published, and
`probe_bls` is what the published table says.

Two measured facts shape everything here, and both are the reason this is not
one line of `urllib`:

  * **What `www.bls.gov` serves turns on a contact URL in the User-Agent.**
    Not identification, and not automation — a full browser string is refused,
    a bare `(+https://…)` with no product name is served. `AGENTS` is the
    matrix that separates "a contact URL is the discriminator" from "this
    exact string is allowlisted".
  * **`www.bls.gov` answers a request for a file it does not have with 200 and
    an HTML page.** So status never answers "is it there". `head()` carries the
    content type back and `is_file` is what callers ask; for an HTML page,
    where `is_file` cannot help, `is_the_oews_page` checks the content.
"""

from __future__ import annotations

import re
import urllib.error
import urllib.request

USER_AGENT = "edtech-kg research (+https://git.samyama.ai/Samyama.ai/edtech-kg)"

OEWS_GEOGRAPHIES = ("nat", "st", "ma")
OEWS_URL = "https://www.bls.gov/oes/special-requests/oesm{yy}{geography}.zip"
GEOGRAPHY_NAMES = {"nat": "national", "st": "state", "ma": "metropolitan"}

# How many releases back to look before giving up. OEWS is annual, so three is
# already more slack than a published series needs.
OEWS_LOOKBACK = 3

BROWSER = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
CONTACT = "(+https://git.samyama.ai/Samyama.ai/edtech-kg)"

# One www.bls.gov page, fetched with several User-Agents. www, not data,
# because that is the host the claim is about.
#
# bls.gov serves 200 with a "page not found" body for a missing file — this
# module documents that behaviour a few lines down — so a URL pinned to one
# release year quietly becomes a probe of an error page the year that release
# is retired, and every row still reads "served". `identity_test_url` finds a
# year that is actually published rather than remembering one.
IDENTITY_TEST_FALLBACK = "https://www.bls.gov/oes/2023/may/oes_nat.htm"

# The claim has been wrong twice, so it is measured as a matrix rather than as
# a yes/no. `attempt(url, None)` does NOT send an anonymous request — urllib
# supplies `Python-urllib/3.x` — so "no User-Agent" was never tested either.
#
# Five agents showed our string served and four others refused, which is
# consistent with "a contact URL is the discriminator" but equally consistent
# with "this exact string is allowlisted" — one served sample cannot separate
# them. The last three rows are here to do that: they hold the contact URL
# constant and vary everything around it.
AGENTS = {
    "ours — name and contact URL": USER_AGENT,
    "library default": None,
    "empty": "",
    "descriptive, no contact URL": "edtech-kg research",
    "browser-like, no contact URL": BROWSER,
    "a different name, with a contact URL": f"kg-source-survey {CONTACT}",
    "the browser string, contact URL appended": f"{BROWSER} {CONTACT}",
    "the contact URL alone, no product name": CONTACT,
}


def fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{exc.code} from {url}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"unreachable: {url} ({exc})") from exc


def attempt(url: str, agent: str | None = USER_AGENT) -> dict:
    """What the server says today, not what it said when this was written.

    `agent` is a parameter because the claim this probe makes is *about* the
    User-Agent: that BLS refuses an anonymous request and serves an identified
    one. An earlier version named a field `unidentified_request` and sent the
    identifying header anyway — it varied the host instead, so the claim in the
    document was never measured by the probe that the document credits.
    """
    # `None` means "send whatever urllib sends by default" — which is
    # `Python-urllib/3.x`, not nothing. An empty string is the closest this can
    # get to absent, and the difference is recorded rather than glossed.
    headers = {} if agent is None else {"User-Agent": agent}
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return {"status": response.status, "bytes": len(response.read())}
    except urllib.error.HTTPError as exc:
        return {"status": exc.code, "reason": str(exc.reason).splitlines()[0]}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"status": None, "reason": str(exc)}


def head(url: str) -> dict:
    """Is it there, and how big — without downloading it.

    `status` alone does not answer "is it there". `www.bls.gov` serves a
    request for a file it does not have with **200 and `text/html`**, so a
    status check reports an unpublished release as available. The content type
    is carried back with it, and `is_file` is what callers should ask.
    """
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT},
                                     method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            size = response.headers.get("content-length")
            kind = (response.headers.get("content-type") or "").split(";")[0].strip()
            return {"status": response.status, "content_type": kind,
                    "bytes": int(size) if size and size.isdigit() else None,
                    "is_file": response.status == 200 and "html" not in kind}
    except urllib.error.HTTPError as exc:
        if exc.code in (405, 501):
            # HEAD refused, not file absent. Reporting this as `is_file:
            # False` makes a published release read as unpublished — the
            # server's opinion about a METHOD, recorded as a fact about the
            # data. Ask again with GET and throw the body away.
            return get_headers(url)
        return {"status": exc.code, "is_file": False,
                "reason": str(exc.reason).splitlines()[0]}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"status": None, "is_file": False, "reason": str(exc)}


def get_headers(url: str) -> dict:
    """`head()` for a server that refuses HEAD. Same answer, one wasted body."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read()
            kind = (response.headers.get("content-type") or "").split(";")[0].strip()
            return {"status": response.status, "content_type": kind,
                    "bytes": len(body), "method": "GET",
                    "is_file": response.status == 200 and "html" not in kind}
    except urllib.error.HTTPError as exc:
        return {"status": exc.code, "is_file": False, "method": "GET",
                "reason": str(exc.reason).splitlines()[0]}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"status": None, "is_file": False, "method": "GET", "reason": str(exc)}


def oews_release(yy: str) -> dict:
    """One OEWS release, by geography — or `{}` if it is not published."""
    got = {GEOGRAPHY_NAMES[g]: head(OEWS_URL.format(yy=yy, geography=g))
           for g in OEWS_GEOGRAPHIES}
    return got if all(g["is_file"] for g in got.values()) else {}


def identity_test_url(oews: dict) -> str:
    """A www.bls.gov page that is actually published, for the header matrix.

    bls.gov answers a request for a missing file with **200 and text/html**,
    which this module documents and `head()` exists to see through. A URL
    pinned to one release year therefore becomes a probe of an error page the
    year that release is retired — and every row of the matrix still reads
    "served", so the claim would go on being confirmed by a page that is not
    the page.

    Verified by CONTENT, never by status. `is_file` cannot help here — it is
    false for any HTML page, and this page is HTML — and a status check is
    vacuous on the one host whose documented behaviour is to answer 200 for a
    file it does not have. That was the previous version of this function: it
    asked the question this module exists to say you must not ask.

    The marker is the page's own subject line, which the not-found body does
    not carry.

    **The fallback is checked too, and reported when it fails.** It is a pinned
    2023 URL, so it is exactly the thing this function exists to stop trusting:
    the year that release is retired it becomes a soft 404, every row of the
    matrix reads "served" against an error page, and the User-Agent finding is
    confirmed by a page that is not the page. Falling back is still right — an
    offline run needs something to report — but it has to be visible that the
    page was not verified, not silently substituted.

    Returns `(url, verified)`. `verified` is False when the URL is being used
    without the content check having passed, for any reason including the
    network being down.
    """
    release = (oews or {}).get("release") or ""
    match = re.search(r"(\d{4})", release)
    if match:
        candidate = f"https://www.bls.gov/oes/{match.group(1)}/may/oes_nat.htm"
        if is_the_oews_page(candidate):
            return candidate, True
    return IDENTITY_TEST_FALLBACK, is_the_oews_page(IDENTITY_TEST_FALLBACK)


OEWS_PAGE_MARKER = "occupational employment and wage estimates"


def is_the_oews_page(url: str) -> bool:
    """Does this URL serve the OEWS national page, or a 200 that is not it?"""
    try:
        return OEWS_PAGE_MARKER in fetch(url).lower()
    except RuntimeError:
        return False


def oews_latest(this_year: int) -> dict:
    """The newest published OEWS release, found rather than remembered.

    Counts back from the current year. A release is only accepted when every
    geography in it is served as a zip — a half-published year would otherwise
    be reported as current with a geography silently missing.
    """
    tried = []
    for year in range(this_year, this_year - OEWS_LOOKBACK - 1, -1):
        yy = f"{year % 100:02d}"
        tried.append(yy)
        found = oews_release(yy)
        if found:
            return {"release": f"May 20{yy}", "years_tried": tried,
                    "geographies": found}
    return {"release": None, "years_tried": tried, "geographies": {}}

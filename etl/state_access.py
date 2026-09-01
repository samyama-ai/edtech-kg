"""Which state education departments answer an automated request — #50.

Found while doing #40 and raised so the cost is a known quantity rather than a
surprise mid-build. The answer there was no regardless, but anything that later
wants state data pays this, and #44's "near me" and the refresh requirement
both assume automation is possible.

The question the issue asks is whether the 403 is **a bot rule that a request
could resolve, or a blanket block**. It is neither of the friendly options, and
the evidence is `robots.txt`: a file that exists to be read by automated
clients, refused with the same 403 as everything else. There is no user-agent
to negotiate with, because nothing is reading the agent.

`reach` takes an opener rather than making its own request, so the suite
exercises every branch without a network and no test touches a department.

**Not `etl/http_reach.py`, deliberately.** That module answers "did this
address answer, and can its silence be asserted", and `attempt` returns a
status STRING for a HEAD request. This one answers a different question — the
issue asks whether a 403 is negotiable — and that needs the four outcomes
below kept apart, because each has a different remedy: a refusal is
configured, a redirect loop is a site that will not settle, a TLS failure is
the department's to fix, and only `served` means a machine can read it.
Collapsing them into a status code loses the finding. It is also GET, not
HEAD, because `robots.txt` is a file to read rather than an address to ping.
"""

from __future__ import annotations

import urllib.error
import urllib.request

from etl.identity import USER_AGENT


# Homepage and robots.txt for each. BOTH, because they answer different
# questions: the homepage says whether a human-facing page is served, and
# robots.txt says whether the site is willing to state a policy to a machine
# at all. A department that serves one and refuses the other is telling us
# something a single probe would miss.
DEPARTMENTS = {
    "Florida — fldoe.org": "https://www.fldoe.org",
    "Virginia — doe.virginia.gov": "https://www.doe.virginia.gov",
    "California — cde.ca.gov": "https://www.cde.ca.gov",
    "Texas — tea.texas.gov": "https://tea.texas.gov",
    "New York — nysed.gov": "https://www.nysed.gov",
}


def brief(reason: str, limit: int = 80) -> str:
    """Truncation the reader can see.

    A message cut mid-word with nothing to mark it — `"unable to get local "`
    — reads as the message rather than as an excerpt of one.
    """
    return reason if len(reason) <= limit else reason[:limit].rstrip() + "…"


def open_url(url: str, timeout: int = 25):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return urllib.request.urlopen(request, timeout=timeout)


def reach(url: str, opener=open_url) -> dict:
    """What one address does, named rather than reduced to reachable or not.

    Four outcomes, and collapsing them loses the finding. A 403 is a refusal
    somebody configured. A redirect loop is a site that will not settle. A
    TLS failure is a certificate problem, which is a different remedy from a
    block and is fixed by the department rather than negotiated with. Only
    `served` means a machine can read it.
    """
    try:
        response = opener(url)
    except urllib.error.HTTPError as exc:
        # A 3xx reaching here is urllib giving up on a redirect that never
        # settles, NOT a refusal. California answers 303 forever, and calling
        # that "refused" would put it beside Florida and Virginia — which are
        # a different problem with a different remedy.
        if 300 <= exc.code < 400:
            return {"outcome": "redirect_loop", "detail": f"HTTP {exc.code}"}
        # A file that is not there is not a file being withheld. `robots.txt`
        # is optional, and a site that never published one has stated no
        # restriction — the opposite of the 403 this page argues from. Mapped
        # to `refused`, a department that simply has no robots.txt would be
        # written up as "refusing before any policy is consulted".
        if exc.code in (404, 410):
            return {"outcome": "absent", "detail": f"HTTP {exc.code}"}
        return {"outcome": "refused", "detail": f"HTTP {exc.code}"}
    except urllib.error.URLError as exc:
        reason = str(getattr(exc, "reason", exc))
        if "CERTIFICATE" in reason.upper() or "SSL" in reason.upper():
            return {"outcome": "tls_failure", "detail": brief(reason)}
        if "redirect" in reason.lower():
            return {"outcome": "redirect_loop", "detail": brief(reason)}
        return {"outcome": "unreachable", "detail": brief(reason)}
    except Exception as exc:                                  # noqa: BLE001
        # Named, never swallowed. An unexpected failure recorded as "refused"
        # would put a department in the blocked column on the strength of a
        # local network problem.
        return {"outcome": "unreachable", "detail": f"{type(exc).__name__}"}
    with response:
        return {"outcome": "served", "detail": f"HTTP {response.status}"}


def survey(opener=open_url) -> dict:
    """Every department, homepage and robots.txt.

    `robots.txt` is the load-bearing half. A site that refuses it is not
    applying a crawler policy — it is refusing before any policy is consulted,
    which is what makes "a request could resolve this" the wrong description.
    """
    results = {}
    for name, root in DEPARTMENTS.items():
        results[name] = {
            "root": root,
            "homepage": reach(root, opener),
            "robots_txt": reach(f"{root}/robots.txt", opener),
        }
    return results


def recommendation(one: dict) -> str:
    """`automatable`, `request-based` or `manual-only`, per the issue.

    A department that serves its homepage but REFUSES robots.txt is
    deliberately not called automatable: it has declined to publish a policy
    to a machine, and reading its files anyway is a decision this repo should
    not make silently.

    A department with no robots.txt at all is a different case and is
    automatable. It has withheld nothing; there is simply no policy to
    consult. Treating `absent` as a refusal would flip a department to
    `request-based` the day it deletes an empty file, and the page would then
    say it "refuses `robots.txt`" — which is the opposite of what happened.
    """
    home = one["homepage"]["outcome"]
    robots = one["robots_txt"]["outcome"]
    if home == "served" and robots in ("served", "absent"):
        return "automatable"
    if home == "served":
        return "request-based"
    return "manual-only"

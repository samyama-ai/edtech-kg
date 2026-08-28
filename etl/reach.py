"""Whether a source answers, and what its silence is allowed to mean.

Split from `etl/probe_apprenticeship.py` when that file passed the 500-line
review limit, on the same line its tests were already split along.

One distinction runs through all of it. A name that resolves NOWHERE is broken
at the publisher's end and can be asserted. A name that resolves and then will
not answer cannot be told apart, from one network, from an outbound
restriction on that address — so `docs/sources/careeronestop.md` asserts the
first and declines the second, and every guard here exists to keep that line
where it is.
"""

from __future__ import annotations

import ipaddress
import socket
import subprocess
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "edtech-kg research probe (+https://git.samyama.ai/Samyama.ai/edtech-kg)"


def is_address(text: str) -> bool:
    """Is this an A or AAAA answer, as `dig +short` prints one?

    PARSED, not pattern-matched. `[0-9a-fA-F:]{3,}` also matches `abc`,
    `deadbeef` and any hex-ish token in that output, and whatever it matched
    went onto the page as the address a resolver returned. Anything else `dig`
    prints is a CNAME, a message, or part of a chain.
    """
    try:
        ipaddress.ip_address(text)
    except ValueError:
        return False
    return True

#: Asked as well as the system resolver, because "does not resolve" is a claim
#: about DNS and not about this network.
PUBLIC_RESOLVERS = (("Google", "8.8.8.8"), ("Cloudflare", "1.1.1.1"))

# What edtech-kg#38 asks about, and what this probe can say about it. Each is
# attempted rather than remembered — a source recorded as blocked on a date is
# a claim that goes stale, and the whole argument of these pages is that a
# figure comes from a run.
REACH = [
    ("careeronestop.org (web)", "https://www.careeronestop.org/"),
    ("careeronestop API", "https://api.careeronestop.org/v1/license/"),
    ("apprenticeship.gov (web)", "https://www.apprenticeship.gov/"),
    ("apprenticeship.gov API", "https://api.apprenticeship.gov/"),
    # Named individually rather than summarised. The page said "404 on every
    # standard CKAN endpoint" while one endpoint was probed.
    ("data.gov CKAN package_list",
     "https://catalog.data.gov/api/3/action/package_list"),
    ("data.gov CKAN package_search",
     "https://catalog.data.gov/api/3/action/package_search?q=apprenticeship"),
    # CONTROL hosts. Both pages argue that the failures above are not a general
    # egress problem, and cite these as reached in the same session — so they
    # have to be in the same run rather than in a sentence.
    ("control: onetcenter.org", "https://www.onetcenter.org/"),
    ("control: nces.ed.gov", "https://nces.ed.gov/"),
    ("control: careertech.org", "https://careertech.org/"),
    # The crosswalk URL is passed in by the caller: importing it back from
    # `probe_apprenticeship` would make these two modules import each other.
    ("O*NET RAPIDS crosswalk", None),
]


def resolves_anywhere(host: str) -> dict:
    """Ask the system resolver AND two public ones.

    The pages distinguish "this network cannot reach it" from "it resolves
    nowhere", and only the second can be asserted without qualification. One
    `gethostbyname()` call cannot tell those apart — it was the system resolver
    once, while the page claimed "no A record from any resolver".

    Answered without a DNS library: `dig` is asked directly, so this stays
    dependency-free like every other probe here. A resolver that cannot be
    reached is recorded as unknown rather than as a negative, because "we could
    not ask" is not "there is no record".
    """
    answers = {}
    try:
        answers["system"] = socket.gethostbyname(host)
    except OSError:
        answers["system"] = None

    for name, server in PUBLIC_RESOLVERS:
        try:
            out = subprocess.run(["dig", "+short", f"@{server}", host],
                                 capture_output=True, text=True, timeout=20)
        except (OSError, subprocess.SubprocessError):
            answers[name] = "unknown"
            continue
        if out.returncode != 0:
            answers[name] = "unknown"
            continue
        # VALIDATED as an address. `dig +short` prints a CNAME chain, and on
        # some failures a message, so the first line that is not a name was
        # taken as an answer whatever it said — and that string then appears
        # on the page as the address a resolver returned.
        found = [line for line in out.stdout.split()
                 if is_address(line)]
        answers[name] = found[0] if found else None

    # The strong claim needs a PUBLIC resolver to have answered. A local
    # failure with both public resolvers unreachable is "we could not ask" —
    # and reading that as "there is no record" turns a machine with no `dig`,
    # or no route to 8.8.8.8, into evidence about a publisher.
    public = [answers[name] for name, _ in PUBLIC_RESOLVERS
              if answers.get(name) != "unknown"]
    answered = [v for v in answers.values() if v != "unknown"]
    return {"by_resolver": answers,
            "resolves_nowhere": bool(public) and all(v is None for v in answered)}


def reachable(rapids_url: str | None = None) -> list[dict]:
    """What answers a request, and what does not — attempted, not remembered.

    DNS is resolved separately from the connection, because they fail
    differently and the difference is the whole finding. A host that resolves
    and refuses TCP is a source that will not talk to this network; a host
    whose name resolves NOWHERE is a broken chain at the publisher's end, and
    only the second can be asserted without qualification.
    """
    # Resolved once per HOST, not per row: each resolution shells out to `dig`
    # twice at up to 20s, and `REACH` repeats hosts. Scoped to this call, not
    # the module — a cache outliving the run answers a later question with an
    # earlier network.
    resolved: dict[str, dict] = {}
    out = []
    for name, url in ((n, u or rapids_url) for n, u in REACH):
        if url is None:
            continue
        host = urllib.parse.urlparse(url).hostname or ""
        if host not in resolved:
            resolved[host] = resolves_anywhere(host)
        dns = resolved[host]
        record = {"source": name, "url": url,
                  "dns": dns["by_resolver"].get("system"),
                  "by_resolver": dns["by_resolver"],
                  "status": None, "status_anonymous": None}

        if dns["resolves_nowhere"]:
            record["status"] = "name does not resolve (no resolver has a record)"
            out.append(record)
            continue
        if record["dns"] is None:
            # THREE states, not two. "the system resolver failed" splits into
            # "a public resolver answered, so this is local" and "no public
            # resolver could be ASKED, so we know nothing" — and both fell
            # into the first message. On a machine with no `dig`, or no route
            # to 8.8.8.8, the page would have claimed another resolver
            # answered when none was reached.
            asked = [v for k, v in dns["by_resolver"].items()
                     if k != "system" and v != "unknown"]
            record["status"] = (
                "name does not resolve here (another resolver does, so this "
                "is local)" if any(v for v in asked) else
                "name does not resolve here, and no public resolver could be "
                "asked — this measures the network, not the publisher")
            out.append(record)
            continue

        # BOTH requests, because the pages turn on the difference. `bls.gov`
        # returned 403 to a short or absent User-Agent and 200 to the
        # identifying one — a block on anonymity. A source that returns 403 to
        # both is blocking automation instead, and that is a different claim
        # which the pages make and this used to not measure.
        record["status"] = attempt(url, USER_AGENT)
        record["status_anonymous"] = attempt(url, None)
        out.append(record)
    return out


def attempt(url: str, agent: str | None) -> str:
    """One HEAD, with or without an identifying User-Agent.

    HEAD rather than GET, and the pages say so: a 405 or 403 to HEAD is not
    evidence about GET, and this whole probe is about telling failure modes
    apart.
    """
    headers = {"User-Agent": agent} if agent else {}
    request = urllib.request.Request(url, headers=headers, method="HEAD")
    if agent is None:
        # urllib inserts `Python-urllib/3.x` unless it is removed outright, so
        # "anonymous" would otherwise measure a DEFAULT agent and not an
        # absent one — the same trap edtech-kg#37 recorded on bls.gov.
        request.add_unredirected_header("User-Agent", "")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return str(response.status)
    except urllib.error.HTTPError as exc:
        if exc.code == 405:
            # About the METHOD. A bare "405" sits beside 403 and 404.
            return "405 (HEAD not allowed — says nothing about GET)"
        return str(exc.code)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return f"no connection ({getattr(exc, 'reason', exc)})"

"""How this repo identifies itself to a publisher. One string, one place.

Seventeen modules each defined their own `USER_AGENT` and three distinct
values were in flight. That is not only untidy: a publisher who blocks one of
them is not blocking the others, so a refusal shows up in one probe and not
its neighbour, and the difference reads as a fact about the publisher rather
than about which constant that file happened to copy.

Two of the seventeen advertised `github.com/samyama-ai/edtech-kg`, which is
not where this repo lives. The contact URL is the part that has to be right —
`docs/sources/bls-occupation.md` measured BLS answering **403** to the same
name with the URL removed, and 200 with it. An address nobody can reach is
closer to the 403 case than to the 200 one.

The value here is the one 14 of the 17 already used, the one that document
quotes, and the one BLS answered 200 to.

**Not a default to be varied.** `http_reach` deliberately compares this
against sending no agent at all, which is a different question — whether
identifying ourselves changes the answer. That comparison passes `None`, not
a second string.
"""

from __future__ import annotations

#: Name and a reachable contact URL. Both halves are load-bearing: the name so
#: a publisher's logs say who this was, the URL so they can find out why.
USER_AGENT = "edtech-kg research (+https://git.samyama.ai/Samyama.ai/edtech-kg)"


#: Every environment variable a probe will read a Gitea token from, in the
#: order they are tried.
#:
#: **One place, for the same reason `USER_AGENT` is.** Two probes read the
#: private forge and each grew its own resolver: `etl/probe_review_cost.py`
#: raises when neither is set, `etl/probe_ci_history.py` returned None and
#: printed its own message. That is survivable. What was not is that
#: `etl/durations.py` stripped the token before shelling out to pytest and
#: named ONE of the two — the one the readers try second — so the ordinary
#: path handed the credential to a subprocess that has no use for it.
#:
#: A list a caller can iterate, so a stripper and a reader cannot disagree
#: about what a token is called.
TOKEN_NAMES = ("GITEA_TOKEN", "SAMYAMA_GITEA_TOKEN")


def gitea_token() -> str | None:
    """The token from the environment, or None. **Never from argv.**

    A `--token` flag puts the secret in `/proc/<pid>/cmdline`, where any
    process on the machine can read it, and in shell history. The caller
    decides what to do about a missing one — one probe raises and one prints
    a named message, and those are different situations.
    """
    import os
    for name in TOKEN_NAMES:
        if os.environ.get(name):
            return os.environ[name]
    return None

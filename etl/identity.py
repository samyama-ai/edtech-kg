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

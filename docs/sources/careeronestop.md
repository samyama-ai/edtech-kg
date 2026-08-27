# CareerOneStop — not cleared, and not for a licence reason

Every figure on this page is printed by
`python -m etl.probe_apprenticeship --reach`. None is typed.

**edtech-kg#38** asks whether CareerOneStop can answer Q23, which
`docs/questions.md` marks unanswerable on the grounds that licensure
requirements are "state-by-state and not centrally published". The issue is
right that this is worth an hour: a question marked unanswerable that turns out
to be answerable is the cheapest win available.

**It is still unanswered.** Not because the claim was tested and held, but
because the API does not accept a connection from here.

## What was measured

| Source | Identified UA | No UA |
|---|---|---|
| `www.careeronestop.org` (web) | **403** | **403** |
| `api.careeronestop.org` | **no connection** | **no connection** |

Both columns are measured. The probe issues each request twice — once with the
identifying User-Agent this repo sends and once with the header removed
outright, because `urllib` inserts `Python-invoke/3.x` unless it is cleared, and
an "anonymous" request that actually carries a default agent measures the wrong
thing.

**403 to both** is what separates this from `docs/sources/bls-occupation.md`,
where `www.bls.gov` returns 403 to a short or absent User-Agent and 200 to the
identifying one — a block on anonymity. This is a block on automated access.

The same run shows the contrast is real rather than theoretical:
`www.apprenticeship.gov` answers **200 identified and 403 anonymous**, so an
anonymity block does exist on a neighbouring host and CareerOneStop is not
behaving that way.

## What this does and does not establish

This is the distinction `docs/sources/bls-occupation.md` had to make and it
applies here with more force, so it is stated before anyone leans on the page.

**Established.** The API host resolves to a real address and does not complete a
TLS connection from this network, and the web host returns 403 to an automated
request regardless of User-Agent. Control hosts reached successfully in the same
session — `onetcenter.org`, `nces.ed.gov`, `careertech.org` — so this is not a
general egress failure.

**Not established.** That CareerOneStop is unreachable *in general*. A refused
TCP connection to a single address cannot be told apart, from one network, from
an outbound restriction on that address. It may well answer from elsewhere.

The neighbouring finding on the same run is a useful contrast, because it can be
asserted without that qualification: `api.apprenticeship.gov` returns no A
record from the system resolver, `8.8.8.8` **or** `1.1.1.1`. A name that
resolves nowhere is broken at the publisher's end. A refused connection is not
the same claim, and this page does not make it.

That asymmetry is the argument of this page, so the probe asks all three
resolvers rather than one — it used to ask the system resolver once while the
page claimed "any resolver". `api.careeronestop.org` answers `155.204.131.84`
from all three, which is why its row is a refused connection and not a missing
name.

**One caveat the whole page rests on:** these are `HEAD` requests. A 403 or 405
to HEAD is **not evidence about GET**, and a page about telling failure modes
apart should say so rather than let the reader assume.

## The part nobody measured

edtech-kg#38 says "terms first" — a free API key is not a licence to
redistribute, the same trap edtech-kg#13 flags for the Urban Institute wrapper.

**That check was never reached.** The terms live behind the developer pages that
return 403, and the API requires a registered key, which is a person filling in
a form rather than something a probe can do. So the licence question is not
answered here either, and nothing on this page should be read as clearing it.

## Verdict

**Not cleared, and Q23 stands as it is.** The claim in `docs/questions.md` —
that licensure is state-by-state and not centrally published — is neither
confirmed nor refuted by this run. It should keep its current status rather
than being softened on the strength of a source nobody could read.

Reopening this needs two things a probe cannot do: a **registered API key**, and
a **reading of the terms** to establish whether measured coverage may be
published at all. Both are human steps, and both should happen before anything
is loaded rather than after — which is the whole point edtech-kg#38 makes.

## Re-run

```bash
python -m etl.probe_apprenticeship --reach
```

The check is attempted on every run rather than remembered, so the day
CareerOneStop starts answering, this page is wrong and the run says so. A
source recorded as blocked on a date is a claim that goes stale quietly.

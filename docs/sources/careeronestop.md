# CareerOneStop — not cleared, and the licence was never reached

Every figure on this page is printed by
`python -m etl.probe_apprenticeship --reach`. None is typed.

**edtech-kg#38** asks whether CareerOneStop can answer Q23, quoting it as
marked unanswerable "state-by-state and not centrally published".

**That quote is not in `docs/questions.md`, and Q23 is not that question.**
Checked: line 93 reads **Q23.** *Which colleges near me offer this programme?*
— marked ✅, answered. No question in the file is about licensure being
unpublished; the only licence question is **Q47** — *This occupation now
requires a licence. Which programmes lead to it?* — also ✅. The phrase appears
nowhere in `docs/`.

This page previously repeated the issue's wording as a citation. It was a
citation to a line that does not exist, on a page whose first sentence is that
nothing on it is typed — so it is recorded here rather than quietly corrected.

The issue's underlying instinct still holds: a question marked unanswerable
that turns out to be answerable is the cheapest win available. It just is not
Q23, and the run below could not settle it either way.

**It is still unanswered**, on two counts. The API does not accept a
connection from here, so the coverage question was never asked — and the terms
sit behind the same block, so the licence question was never reached either.
Neither is ruled out; both are simply unmeasured.

## What was measured

| Source | Identified UA | No UA |
|---|---|---|
| `www.careeronestop.org` (web) | **403** | **403** |
| `api.careeronestop.org` | **no connection** | **no connection** |

Both columns are measured. The probe issues each request twice — once with the
identifying User-Agent this repo sends and once with the header removed
outright, because `urllib` inserts `Python-urllib/3.x` unless it is cleared, and
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

**Established.** The API host resolves to a real address — the **same one from
the system resolver, Google and Cloudflare** — and the connection then **times
out**. The address itself is in the probe output rather than on this page: it
is a fact about DNS on the day of the run, and typing it here would go stale
without anything saying so. The web host returns 403 to an automated request regardless
of User-Agent.

The probe records `no connection (timed out)` and nothing finer. It cannot tell
a TLS handshake that never completes from a connection dropped or filtered, so
this page does not say which. Control hosts reached successfully in the same
session — `onetcenter.org`, `nces.ed.gov`, `careertech.org` — so this is not a
general egress failure.

**Not established.** That CareerOneStop is unreachable *in general*. A
connection to a single address that times out cannot be told apart, from one
network, from an outbound restriction on that address. It may well answer from
elsewhere.

The neighbouring finding on the same run is a useful contrast, because it can be
asserted without that qualification: `api.apprenticeship.gov` returns no A
record from the system resolver, `8.8.8.8` **or** `1.1.1.1`. A name that
resolves nowhere is broken at the publisher's end. A connection that times out
is not the same claim, and this page does not make it.

That asymmetry is the argument of this page, so the probe asks all three
resolvers rather than one. `api.careeronestop.org` answers with the **same
address from all three**, which is why its row is a connection that times out
and not a missing name.

**One caveat the whole page rests on:** these are `HEAD` requests, and a
response to HEAD is **not evidence about GET**. No 405 was observed here — it
is named only as the shape a HEAD-specific refusal would take, which is exactly
why the distinction is drawn rather than assumed.

## The part nobody measured

edtech-kg#38 says "terms first" — a free API key is not a licence to
redistribute, the same trap edtech-kg#13 flags for the Urban Institute wrapper.

**That check was never reached.** The terms live behind the developer pages that
return 403, and the API requires a registered key, which is a person filling in
a form rather than something a probe can do. So the licence question is not
answered here either, and nothing on this page should be read as clearing it.

## Verdict

**Not cleared, and nothing about a question's status changes on this run.**
The claim edtech-kg#38 attributes to `docs/questions.md` is not in that file,
and the run could not read CareerOneStop either way — so there is nothing here
to move a question with. Q47 keeps its ✅ and Q23 keeps its ✅; neither was in question, and
neither should be softened on the strength of a source nobody could read.

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

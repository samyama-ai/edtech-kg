# What it costs to read a state education department

Answering edtech-kg#50, raised while doing #40 so that the cost is a known
quantity rather than a surprise mid-build. #40's answer was no regardless, but
#44's *"near me"* and the refresh requirement both assume automation is
possible, and for three of five departments it is not.

Measured **2026-08-28** by `python -m etl.probe_state_access`, which writes
[`state-access-measured.json`](state-access-measured.json). Ten requests: a
homepage and a `robots.txt` for each department.

| department | homepage | `robots.txt` | verdict |
|---|---|---|---|
| Florida — fldoe.org | refused (403) | refused (403) | **manual-only** |
| Virginia — doe.virginia.gov | refused (403) | refused (403) | **manual-only** |
| California — cde.ca.gov | redirect loop (303) | redirect loop (303) | **manual-only** |
| Texas — tea.texas.gov | served | served | **automatable** |
| New York — nysed.gov | TLS failure | TLS failure | **manual-only** |

## The question #50 asks, and the answer

> Whether the 403 is a blanket bot rule or a rate/agent policy that a request
> could resolve

**Neither.** Florida and Virginia refuse **`robots.txt`** with the same 403.

That file exists for one purpose: to be fetched by an automated client so a
site can state its crawling policy. Refusing it is not applying a crawler
policy — it is refusing *before any policy is consulted*. There is no
user-agent to negotiate with, because nothing is reading the agent.

Confirmed directly: a browser user-agent gets the same 403 as this repo's
plainly-identified one. That single check was made to answer the issue's
question, and **impersonating a browser is not something this repo will do to
obtain data** — the finding is that it would not work anyway.

## Two things the issue did not predict

**California is a redirect loop, not a block.** It answers 303 indefinitely to
a plain client. That is a different problem with a different remedy, and
collapsing it into "blocked" would lose that.

**New York now fails TLS certificate verification.** #50 recorded on
2026-08-18 that *"Texas and New York served their files without complaint."*
Ten days later New York does not verify. A certificate problem is fixed by the
department rather than negotiated with, and it may be temporary — which is
precisely why this page is regenerated rather than typed.

## What periodic refresh costs

The issue asks what a yearly refresh would cost if every year needs a human.

**One of five states is automatable.** For the other four the options are, in
order of preference:

1. **An open-data portal or mirror.** Not established here — a per-department
   search is its own piece of work, and it is not this issue.
2. **A documented request process.** Also not established.
3. **A human download.** Four departments, once per revision, indefinitely.

That third row is the honest planning assumption until one of the first two is
established. It is not a reason to abandon state data; it is a reason not to
design a pipeline that assumes a machine can fetch it.

## What this does not say

- **It does not say the data is unavailable.** All five publish for people.
  The finding is about machines.
- **It does not establish licences.** Reachability and permission are separate
  questions, and a served file is not a cleared one — see
  [`../scope.md`](../scope.md).
- **It is five departments, not fifty.** These are the five #40 and #48
  touched. Nothing here supports a rate for the country.

## Re-measuring

```bash
python -m etl.probe_state_access            # the table
python -m etl.probe_state_access --record   # refresh the committed record
```

Deliberately uncached. The point is what the sites do today, and a block that
has been lifted is exactly what a stale copy would hide. No test makes these
requests: `reach` takes an opener, so the suite exercises every branch with
nothing on the network.

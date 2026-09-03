# Pathway identity across two publishers — measured 2026-09-03

Every figure here is printed by `python -m etl.probe_pathway_identity`, which
reads all 98 published pathways from the Credential Engine Registry. The record
it writes is `docs/sources/pathway-identity-measured.json`, and
`tests/test_probe_pathway_identity.py` holds this page to it.

This settles #85: **one label keyed on one property cannot hold both
publishers.** The interesting part is that it does not fail the way the issue
expected.

## The question

`Pathway` was declared keyed on `ctid` when the Registry was the only publisher
in view. #82 moved it to `url` when PWCS turned out to publish pathways as
pages — 42 of them, none carrying a ctid, so the declared key would have been
null on every node. The engine accepts that in silence: a constraint here
declares the key and does not enforce it.

So the district's key does not fit the Registry, and the Registry's does not fit
the district. #85 asked which key survives contact with both, and reasoned that
a Registry pathway "**may** have no stable public URL". A key chosen on a *may*
is a key chosen on a guess, so it was measured instead.

## What the census found

Not a sample — the whole population fits in two pages, so every figure is a
census and the sampling caveat the other Registry probes carry does not apply.

| candidate | present | distinct | lost to a merge | usable as a key |
|---|---|---|---|---|
| `ceterms:ctid` | **98 / 98** | 98 | 0 | **yes** |
| `ceterms:subjectWebpage` | **78 / 98** | 71 | **7** | no |

The issue's guess was right, and it was the smaller half of the problem.

**Twenty pathways publish no webpage at all.** Keying on `url` would give them
the same null key that keying on `ctid` gave the district's 42 — the same
failure, in the other direction.

**Seven more would be silently merged.** **Four pages are each published as
several distinct pathways**, and none of it is a publishing error — the shared
page is a *department or category landing page*, and the pathways under it are
genuinely different programmes:

| page | pathways published against it |
|---|---|
| `ce.pima.edu/trades/` | Carpentry · Electrician · HVAC Technician · Plumbing |
| `hccs.edu/…/human-service-technology/` | Chemical Dependency Counselor · Community Health Worker · Certified Prevention Specialist |
| `hccs.edu/…/medical-assistant/` | Medical Scribe Certificate · Medical Assistant |
| `catalog.forsythtech.edu/…/Welding_Technology_AAS` | Welding Technology AAS · Welding Technology Diploma |

Pima's is the clearest: four separate trades behind one generic `/trades/`
landing page. Keying on the page would fuse four programmes into one node and
report three of them as never having existed.

That second row is the one that matters for how this repo works. **A key that
is absent is visible; a key that merges is not.** Twenty nulls would show up
the first time anything counted them. Seven records quietly becoming four would
show up as a total that looks plausible — 94 pathways instead of 98 — and there
is no query that reports it as wrong.

`ceterms:ctid` is present and distinct on all 98, so it is a sound key **for the
Registry**. It remains unusable for the district, which publishes none.

## The verdict: a composite carrying the identifier space

```
Pathway.id = "<space>|<identifier>"        space is "url" or "ctid"
```

A district pathway is `"url|https://catalog.pwcs.edu/…"`; a Registry pathway is
`"ctid|ce-2ddb2dfc-8aca-4760-9fca-868ca8d36b45"`. This is the shape `AwardingBody`, `Level` and `Competency`
already use, and for the same reason — one concept, several publishers, no
shared identifier. It is the repo's existing answer, not a new one.

**Two labels were the alternative, and were rejected.** A district pathway and a
Registry pathway are the same concept differently published. Splitting the label
would make every pathway question a union of two labels, permanently, in order
to record a distinction that belongs in a property. The cost lands on every
future query; the benefit is a key collision that a prefix already prevents.

### The separator is parsed from the LEFT — the opposite of `Level`

`Level` splits from the **right** (`body, _, code = id.rpartition("|")`) because
its *trailing* component, the level code, is the one guaranteed free of the
separator, while the awarding-body id has its own internal structure.

Here it is exactly reversed. The *leading* component is guaranteed free of the
separator — the space is drawn from a two-value vocabulary — and a URL carries
whatever a publisher put in it. So:

```python
space, _, identifier = id.partition("|")
```

Copying `Level`'s rule here recovers the wrong parts on any identifier
containing a `|`, and it recovers them **without erroring**, which is why this
is written down rather than left to be inferred from the sibling label.

## The two guarantees #85 asked for

**Cannot collide** — yes, by construction. A district pathway's id begins
`url|` and a Registry pathway's begins `ctid|`, so two things from different
publishers cannot occupy one node whatever their identifiers say.

**Not duplicated when they describe the same thing** — **no, and deliberately
so.** The same pathway published both ways gets two nodes, because the property
that makes them non-colliding also makes them non-merging.

That is the correct default here rather than a gap being excused. An equivalence
between two publishers' identifiers is a claim with a source, which is precisely
what this schema already decided for `Level`: `EQUIVALENT_TO` carries
`asserted_by` and `source_url` because asserting an unpublished equivalence is
the error this repo refused with `Submission -> MarketedDevice` in
`regulatory-affairs-kg`. Inferring that two pathways are one because they share
a URL would be that error again — and the seven merged records above are the
measurement showing a shared URL does not even mean one pathway *within* a
single publisher.

**It does not arise today.** The 78 webpages are published across 21 hosts, none
of them a district this repo loads:

| host | pathways |
|---|---|
| `www.hccs.edu` | 22 |
| `chaffey.badgr.com` | 17 |
| `ce.pima.edu` | 7 |
| `catalog.forsythtech.edu` | 6 |
| `www.wgu.edu` | 3 |

These are colleges and badge platforms. It will arise the moment a loaded
district also publishes to the Registry, and the edge that records it is
follow-up work, not something to invent before there is a case to test it on.

## What this does not do

- **It does not load anything.** Registry data is read here, not loaded; #56
  decides whether it may be loaded at all. Reading published identifiers in
  order to choose a schema key does not wait on that answer.
- **The constraint still names `url`.** It moves to `id` when a loader first
  writes one, which is Registry work. Declaring `id` now would declare a key no
  loader writes — the failure this schema warns about, and the one #82 was
  raised to undo.
- **The figures are of one day's Registry.** 98 is the population on
  2026-09-03; the probe re-reads it rather than trusting this page, and the
  record carries the date.

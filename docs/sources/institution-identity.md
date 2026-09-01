# Institution identity — which number names a college

**edtech-kg#45.** IPEDS `UNITID`, `OPEID`, and anything ROR, Wikidata or a
state publishes all name the same institution differently, and institutions
merge, close and reopen under new numbers. This settles which identifier this
graph keys on, what bridges to it, and what a query should return for a college
that no longer exists.

Every figure is printed by `python -m etl.probe_institution_identity --bridges`
and committed as
[`institution-identity-measured.json`](institution-identity-measured.json).

## The canonical identifier is `UNITID`

Measured over 6,256 institutions in one year of IPEDS
institutional characteristics:

| | |
|---|---:|
| institutions | 6,256 |
| distinct `UNITID` | 6,256 |
| **`UNITID` unique per institution** | **yes** |
| distinct real `OPEID` | 6,174 |
| `OPEID`s covering more than one institution | 42 |
| institutions sharing an `OPEID` | 86 |

`UNITID` is one per institution. `OPEID` is not: 42
of them cover 86 institutions between them,
which is the campus-sharing case the issue expected. The spread of real
`OPEID`s is `{'1': 6132, '2': 40, '3': 2}` — read as "this many `OPEID`s cover that many
institutions".

So the answer is **`UNITID`**, and `OPEID` is a crosswalk key rather than an
identity. That matters for a `Programme` offered at three campuses of one
system: keyed on `OPEID` they collapse into one node.

## `-2` is a sentinel, and it is everywhere

**38 institutions carry `-2` where an `OPEID` would go.**
It is not an identifier and not missing data — IPEDS writes it where a value
does not apply.

A join that treats it as a key silently merges those 38
into one institution. This repo has paid for this exact shape once already:
`99-9999 NO MATCH` was counted as an occupation until #70.

And it is not confined to one column: **`-2` appears in
29 of the 73 columns** in this
file. Any loader reading IPEDS has to know it before it reads anything, not
after it finds a strange number.

## Closure and merger are separate mechanisms, and they do not overlap

| | |
|---|---:|
| institutions with a close date | 46 |
| institutions with a successor pointer (`NEWID`) | 54 |
| **institutions with both** | **0** |
| not currently active | 73 |
| distinct successor institutions | 29 |

**Zero carry both.** A merged institution has a successor and no close date; a
closed one has a date and no successor. They are different facts and IPEDS
records them in different columns, so code that checks one will miss the other
entirely.

### The rule for an institution that no longer exists

The issue says it plainly: *"Nothing" is usually the wrong answer for a student
asking about a college they attended.* So:

1. **Has a `NEWID`** — resolve to the successor and say so. The institution's
   records did not stop existing; they belong to a different `UNITID` now.
2. **Has a close date** — answer, and state the date. Its completions are still
   real and a student who attended still attended.
3. **Neither, and not currently active** — answer, and say the status is
   unclear. 73 institutions are not currently active
   and only 46 have a close date, so most of that gap is
   not a closure anybody has recorded.

An `Institution` node therefore needs the successor pointer and the close date
as properties. Neither is derivable from the other, and neither is derivable
from the row being absent in a later year.

## The bridges: one works, one does not

**ROR does not carry an IPEDS identifier.** Sampled 60 US
organisations, and the external identifier types published are
`grid`, `isni`, `wikidata` — no IPEDS among them.
So ROR is not a bridge to the federal collections directly.

It does carry Wikidata for 21 of the
60 sampled, which makes ROR → Wikidata → IPEDS a two-hop route
rather than a join.

**Wikidata carries an IPEDS identifier on 3,856 items** (property `P1771`),
against 6,256 institutions in IPEDS — about **62%**
coverage if every one of those items is a current US institution, which is an
upper bound rather than a measurement of overlap.

That is enough to be useful and not enough to depend on. Wikidata is
**accepted as a bridge for enrichment, and refused as an identity** — an
institution missing from it is not a fact about the institution.

## Verdict

| Question | Answer |
|---|---|
| Canonical identifier | **`UNITID`** |
| `OPEID` | crosswalk key only — 42 cover several institutions |
| ROR | **not a bridge** — carries no IPEDS identifier |
| Wikidata | bridge for enrichment at ~62%, never an identity |
| Closed institution | answer with the close date, never nothing |
| Merged institution | resolve `NEWID`, and say which |

## What this does not establish

- **Overlap, not coverage.** The Wikidata figure counts items with an IPEDS
  identifier; it does not check they match institutions in this file. The real
  overlap is at most 62% and probably less.
- **One year.** Renames across years are not measured here — this reads a
  single directory, so an institution renamed between years looks unchanged.
- **ROR was sampled**, 60 organisations, not swept. A bridge
  appearing on nothing in that sample could still exist rarely; the finding is
  that it is not the norm.
- College Scorecard's own identifiers are not compared. It keys on `UNITID` and
  `OPEID` too, so the question is whether it agrees, and that is unmeasured.

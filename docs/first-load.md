# The first load — which slice, and why

Answering edtech-kg#23. The completions table is **9,026,310 rows for one year**
([`sources/education-data.md`](sources/education-data.md)), the engine has no
batch write form — `UNWIND` does not parse — and this repo's loader writes
every row with `MERGE`. That combination is a scope decision with a demo
attached, not a loader detail.

**The slice: Virginia only — `fips=51`, 190,770 rows, data year 2022.**

Everything below is measured against
`public.ecr.aws/f9f6l5u4/samyama-graph:1.1.0`. Row counts are the Urban
Institute API's own `count`, read live.

---

## The measurement that decides it

The issue estimated "roughly 100 statements/sec" and "about 25 hours" for a full
year. Both figures are wrong, and wrong in the direction that matters: **there is
no rate. `MERGE` slows down as the label it writes into grows.**

| nodes already in the label | `MERGE` | `MATCH … WHERE key = …` |
|---:|---:|---:|
| 1,500 | 692 /sec | — |
| 3,500 | 492 /sec | — |
| 6,500 | 284 /sec | — |
| 12,500 | 146 /sec | — |
| 20,500 | 65 /sec | 747 /sec |
| 29,101 | 48 /sec | 791 /sec |
| 37,141 | 35 /sec | 753 /sec |

`MATCH` on the same constrained property is **flat** across the same range, and
`CREATE` into the same label runs at 749/sec regardless. So the index exists and
works — **`MERGE` is not using it.** It is scanning, and the cost per write grows
with the label.

That is not a tuning problem. It changes the shape of the arithmetic from linear
to quadratic: loading *n* rows costs roughly `n² / 2k`, with *k* ≈ 1.34 million
from the table above.

| slice | rows | with `MERGE` | with `MATCH`-then-`CREATE` |
|---|---:|---:|---:|
| **Virginia, 2022** | **190,770** | ~3.8 hours | **~11 minutes** |
| every state, 2022 | 9,026,310 | ~350 days | ~8.4 hours |

The 25-hour estimate was optimistic by a factor of about 340.

## The workaround, measured

`MERGE` can be replaced by a lookup and a conditional create — two round trips
instead of one, both index-backed:

```
MATCH (c:L) WHERE c.id = <key> RETURN c.id     -- 775/sec, flat
CREATE (c:L {id: <key>})                        -- 749/sec, flat, only if absent
```

Measured end to end at **300/sec against a 20,700-node label, where `MERGE` on
the same label managed 63/sec** — nearly five times faster despite doubling the
requests, and it does not degrade. Correctness holds: re-running produced one
node per key, not two.

This is not proposed as a change to `load_pwcs.py` here. That loader writes
1,098 nodes, where `MERGE` costs nothing and its convergence argument
(`load_pwcs.py:64`) is worth more than the speed. It matters for the completions
load, which is 174 times larger, and it is recorded so the decision is made
rather than discovered.

## Why Virginia

**Because it is the only slice that joins the two halves of the graph.**

PWCS — Prince William County Public Schools — is the one district loaded, and it
is in Virginia. The product question is whether a high-school course plan reaches
a post-secondary programme and then an occupation. A completions slice from a
state the loaded district cannot feed into answers a different question.

- **190,770 rows, 2.1% of the year.** Large enough that the join is not a toy;
  small enough to load in the time a demo can wait for.
- **~11 minutes** with the lookup-and-create path, or ~3.8 hours with `MERGE` as
  the loader stands.
- It fits the precedent. Part 870 played this role in the device graph: one CFR
  part, chosen because it fit under the API cap and contained the worked example.

## What the slice makes unanswerable

Stated plainly, because a bounded load reads as a whole one otherwise.

- **Any national comparison.** "Which state produces most graduates in this
  programme" has no answer, and must not be given one from a Virginia-only base.
- **Any question about an institution outside Virginia**, including the
  out-of-state colleges a PWCS student is most likely to apply to.
- **Rankings of any kind.** A ranking over 2.1% of the data is not a ranking of
  the data, and the shape of the answer hides that.
- **Anything about a year other than 2022.** One year, matching the IPEDS and
  CCD figures already in [`../DATASET-CARD.md`](../DATASET-CARD.md).

The graph should refuse these rather than answer them narrowly. A count of zero
out-of-state institutions would read as a measurement; there has been none.

## What is not decided here

**The engine finding deserves its own issue** — `MERGE` ignoring a constraint's
index is a defect with consequences well beyond this load, and it is filed
separately rather than buried in a scope note.

**Nothing is loaded by this document.** It names the slice, records the
arithmetic and says what the slice costs in answers. The load itself is the next
issue, and it should not start before the `MERGE` question has an answer.

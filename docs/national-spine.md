# The national spine — what was loaded, and what it cost

Answering edtech-kg#7. [`first-load.md`](first-load.md) chose the slice; this
records the load that ran on it.

**Every figure here was printed by `python -m etl.load_education --record` and
substituted from
[`sources/national-spine-measured.json`](sources/national-spine-measured.json).
None was transcribed by hand.**

## The graph, read back after the load

| label | nodes |
|---|---:|
| `Institution` | 147 |
| `Programme` | 664 |
| `Completion` | 58,317 |

| edge | count |
|---|---:|
| `(:Completion)-[:AT]->(:Institution)` | 58,317 |
| `(:Completion)-[:IN]->(:Programme)` | 58,317 |

351,524 statements in 1689.0s against
`public.ecr.aws/f9f6l5u4/samyama-graph:1.1.0`, and **the issued count and the
held count agree on all five**. That agreement is the point of the report and
not a formality — see below.

---

## The load found a defect in the schema

`Completion` was keyed on five parts: institution, CIP, award level,
demographic, year.

IPEDS publishes a sixth, `majornum` — whether this was the student's first
major or their second. Two rows differing only by it are two real completions,
and under the five-part key they merged into one node and one award count was
lost. **Nothing would have failed.** The load would have reported fewer nodes
than rows, which is exactly what a `MERGE` is supposed to do.

Measured over the slice before the fix: 190,770 rows hold 16,800 groups
carrying more than one `majornum`, and **in 3,524 of those more than one has a
non-zero award count**. Those 3,524 are the ones that lose data.

`major_number`, `race` and `sex` are stored as properties as well as being
components of the key. Keyed-only, the fix would be invisible: two nodes with
equal `awards` and no readable difference between them, and no question could
ask how many finished as a second major.

## The writes are not `MERGE`, and the issue asked for `MERGE`

edtech-kg#7's definition of done says *"every write a MERGE"*. This load does
not do that, and the reason is a measurement that post-dates the issue.

[`first-load.md`](first-load.md) records `MERGE` ignoring the constraint's
index and scanning the label instead: **692 statements/sec at 1,500 nodes,
falling to 35/sec at 37,141.** That is not a slow constant, it is a curve, and
it is why the issue's own estimate of "roughly 100 statements/sec" was wrong in
the direction that matters.

So every write here is a lookup followed by a `CREATE` only if absent. Two
round trips instead of one, both index-backed.

**It still degrades — just far less.** An earlier draft of the loader claimed
"does not degrade" on the strength of a 2,000-row slice, which is precisely the
size at which `MERGE`'s problem is also invisible. Sampled once a minute **by
the load itself**, so the curve and the totals above describe one run:

| seconds elapsed | `Completion` nodes held | completions written /sec |
|---:|---:|---:|
| 63 | 3,367 | 53.7 |
| 303 | 14,017 | 39.8 |
| 543 | 23,104 | 29.2 |
| 783 | 30,906 | 33.1 |
| 1023 | 39,048 | 34.2 |
| 1263 | 46,688 | 30.5 |
| 1503 | 53,082 | 26.9 |
| 1689 | 58,317 | 25.4 |

It finishes at 25.4/sec holding
58,317. Each completion is six statements — three
lookups and three creates — so that is about 152
statements/sec.

Against `MERGE`'s twentyfold fall across a 25x growth, this is usable at this
scale — and worth re-measuring rather than assumed before running it at ten
times it.

## Idempotence is asserted against the graph, not against the code

**The first version was not idempotent, and its own report is what caught it.**
The node writes looked before creating; the edge writes did not. A second run
over the slice added 2,000 duplicate `AT` and `IN` edges — and the only
evidence was the gap column, because the loader's issued count was perfectly
happy.

Re-run over the full slice after the fix: **175,762 statements, zero created**
— exactly one lookup per object and no writes, with every count unchanged.

Two things follow, and both are written into the loader rather than remembered:

- **The counts are read back out of the graph.** A loader that reports what it
  issued has reported its own intentions. On this engine that is not a
  pedantic distinction: a unique constraint does not reject a duplicate, so a
  double-issued `CREATE` leaves two nodes and raises nothing.
  `tests/test_load_education_engine.py` asserts that behaviour directly, so an
  engine that starts enforcing the constraint fails a test rather than quietly
  changing what the loader's comments mean.
- **An edge `MERGE` would not have fixed it either.** #163 records edge `MERGE`
  ignoring its property map on 1.1.0.

Each endpoint of an edge is matched with its own `WHERE`, because a `MATCH`
whose endpoints are *both* already bound does not filter on this engine — it
is silently ignored ([`engine-behaviours.md`](engine-behaviours.md)).

## What the slice leaves out, deliberately

| dropped | rows | why |
|---|---:|---|
| completions recording zero awards | 132,284 | 69% of the volume, and *"nobody of this demographic finished this programme"* answers no question in [`questions.md`](questions.md). `--all-rows` loads them. |
| rows collapsing onto one key | 169 | Duplicates from the API. Skipped in the walk rather than left to the lookup, so the issued count stays honest. |

Both counts are printed by every load, so the slice cannot be mistaken for the
whole.

## What is still not loaded

`Occupation` and the CIP–SOC crosswalk — the join that turns *"what did people
finish"* into *"where does it lead"* — are **not** in this load, although #7's
scope names them. The crosswalk is measured
([`sources/cip-soc-crosswalk.md`](sources/cip-soc-crosswalk.md), 867
occupations) and has a probe; it has no loader. Neither do earnings.

That is a smaller graph than #7 describes, and saying so is cheaper than a
reader discovering it by writing a traversal that returns nothing.

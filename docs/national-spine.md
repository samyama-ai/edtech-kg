# The national spine — one state of it, and what it cost

Answering edtech-kg#7. [`first-load.md`](first-load.md) chose the slice; this
records the load that ran on it.

**THIS IS VIRGINIA, DATA YEAR 2022 — `fips=51`.** The tier is
called the national spine because that is what #7 calls the layer; the LOAD is
one state. IPEDS publishes 9,026,310 completion rows for a year and this took
190,770
of them. Every figure below describes Virginia and none of them generalises to
the country by multiplication.

**Every figure in the tables was printed by
`python -m etl.load_education --record` or
`python -m etl.probe_completion_key --record` and substituted from
[`sources/national-spine-measured.json`](sources/national-spine-measured.json)
and [`sources/completion-key-measured.json`](sources/completion-key-measured.json).
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

351,524 statements in 1442.8s against
`public.ecr.aws/f9f6l5u4/samyama-graph:1.1.0`. **Read back out of the graph,
never inferred from the input rows** — and the two agree on all five, which is
the point of the report rather than a formality.

---

## The load found a defect in the schema

`Completion` was keyed on five parts: institution, CIP, award level,
demographic, year.

IPEDS publishes a sixth, `majornum` — whether this was the student's first
major or their second. Two rows differing only by it are two real completions,
and under the five-part key they merged into one node and one award count was
lost. **Nothing would have failed.** The load would have reported fewer nodes
than rows, which is exactly what a `MERGE` is supposed to do.

Measured over this slice by `etl/probe_completion_key.py`:

| | |
|---|---:|
| rows | 190,770 |
| distinct six-part keys | 189,450 |
| distinct five-part keys | 172,650 |
| **completions that disappear** | **16,800** |
| of those, merges that also lose an award count | 3,524 |
| award counts those carry | 23,126 |

**Three quantities, and two of them were conflated here.** An earlier version
of this page led with 23,126 and called it "completions that
disappear". It is a SUM OF AWARD COUNTS across the
3,524 merges where more than one row carries a
non-zero award — not a count of nodes, and not comparable to one.

The completions lost is **16,800**: six-part keys minus
five-part. `majornum` takes exactly two values in this slice
(1, 2), so a merging group holds
two six-part keys and loses one node — **every second-major row is a
completion that disappears.** That is why this figure and the count of groups
carrying two majornums are the same number.

Most merged groups lose a node and no award count: only
3,524 of the 16,800 had more than
one non-zero award.

`major_number`, `race` and `sex` are stored as properties as well as being
components of the key. Keyed-only, the fix would be invisible: two nodes with
equal `awards` and no readable difference between them, and no question could
ask how many finished as a second major.

## The writes are not `MERGE`, and the issue asked for `MERGE`

edtech-kg#7's definition of done says *"every write a MERGE"*. This load does
not, and the reason is a measurement that post-dates the issue.

[`first-load.md`](first-load.md) records `MERGE` ignoring the constraint's
index and scanning the label instead: **692 statements/sec at 1,500 nodes,
falling to 35/sec at 37,141.** That is not a slow constant, it is a curve, and
it is why the issue's own estimate of "roughly 100 statements/sec" was wrong in
the direction that matters.

So every write is a lookup followed by a `CREATE` only if absent — and the
constraint cannot substitute for the lookup. 1.1.0 validates a unique
constraint against existing rows when you DECLARE it and never applies it to a
write, so a double-issued `CREATE` leaves two nodes and raises nothing.
`tests/test_load_education_engine.py` asserts both halves of that.

**It still degrades — just far less.** An earlier draft of the loader claimed
"does not degrade" on the strength of a 2,000-row slice, which is precisely
the size at which `MERGE`'s problem is also invisible. Sampled once a minute
**by the load itself**, so the curve and the totals above describe one run:

| seconds elapsed | `Completion` nodes held | completions written /sec |
|---:|---:|---:|
| 63 | 3,374 | 53.2 |
| 243 | 11,069 | 36.8 |
| 424 | 18,115 | 39.8 |
| 604 | 25,491 | 44.9 |
| 784 | 33,121 | 40.6 |
| 964 | 40,234 | 41.4 |
| 1144 | 47,307 | 36.6 |
| 1324 | 53,746 | 35.6 |
| 1443 | 58,317 | 38.6 |

It finishes at 38.6/sec holding 58,317. Each completion is six statements — three
lookups and three creates — so that is about
232 statements/sec as it finishes, and
244 statements/sec averaged over the whole run.

## Idempotence, measured by the recorded run itself

The same load, run again against the graph it had just made:

| | |
|---|---:|
| statements issued | 175,762 |
| **nodes and edges created** | **0** |
| already present | 175,762 |
| seconds | 856.1 |

Exactly one lookup per object and no writes, with every count unchanged.

**The first version was not idempotent, and its own report is what caught
it.** The node writes looked before creating; the edge writes did not. A
second run added 2,000 duplicate `AT` and `IN` edges — and the only evidence
was the gap column, because the loader's issued count was perfectly happy.

Two things follow, and both are written into the loader rather than
remembered:

- **The counts are read back out of the graph**, and compared against what it
  held BEFORE plus what this run created. A whole-graph count against this
  run's issued count reports another year's data as a gap this run caused.
- **An edge `MERGE` would not have fixed it either.** #163 records edge
  `MERGE` ignoring its property map on 1.1.0.

Each endpoint of an edge is matched with its own `WHERE`, because a `MATCH`
whose endpoints are *both* already bound does not filter on this engine — it
is silently ignored ([`engine-behaviours.md`](engine-behaviours.md)).

## What the slice leaves out, deliberately

| dropped | rows | why |
|---|---:|---|
| completions recording zero awards | 132,284 | 69% of the volume, and *"nobody of this demographic finished this programme"* answers no question in [`questions.md`](questions.md). `--all-rows` loads them. |
| rows collapsing onto one key | 169 | Duplicates from the API. Skipped in the walk rather than left to the lookup, so the issued count stays honest. **Not** the `majornum` defect above: these lose nothing. |

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

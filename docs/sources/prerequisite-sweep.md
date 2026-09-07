# Every published Registry course, asked the same question

Answering edtech-kg#58. #28 found that CTDL defines a direct Course→Course
prerequisite property and recommended adopting it. #54's probe then measured
**600** published courses and found it used **zero** times — but 600 is the head
of the result set, not a random sample, and an absence in 1.3% is consistent
with a few hundred uses.

This is the census. **All 47,862 courses, all 958 pages, one walk.**

| | |
|---|---:|
| courses read | **47,862** — the population the Registry reports |
| pages read | **958 of 958** |
| elapsed | **62.6 minutes** |
| stating a prerequisite | **10,055** |
| — as the typed `ceterms:prerequisite` edge | **0** |
| — as free text in a `ConditionProfile` | **10,055** |
| stated but empty | 11 |
| publishers using the typed edge | **none** |

Every figure is printed by `python -m etl.sweep_prerequisites` and committed as
[`prerequisite-sweep-measured.json`](prerequisite-sweep-measured.json).

---

## The answer

**Nobody uses it. Not one course of 47,862.**

The issue set out both outcomes in advance, which is why this was worth an hour:

> *zero in 47,862* — we adopt the term knowing we would be its first user, and
> that is a gap in the ecosystem rather than a gap in us
> *some uses* — those publishers are a worked example and a source of real
> resolved prerequisites

It is the first. The recommendation in #28 stands, and #33 can record that
adopting `ceterms:prerequisite` makes this repo its first publisher.

## What the census changed, and what it did not

**It did not change the verdict.** The sample said zero; the census says zero.

**It did change the scale of the thing being missed.** The sample found 83 of
600 courses stating a prerequisite — 13.8%. Across the whole Registry it is
**10,055 of 47,862, or 21.0%**. Half as many again, proportionally, and a
hundred and twenty times as many in absolute terms.

So this is not a case of nobody recording prerequisites. **Ten thousand courses
record one.** They record it where a machine cannot follow it:

```
"PSYC101"
"PHOT 109"
"Prerequisite: PHOT109, PHOT110, and PHOT205"
"MATH 113, MATH 114 (Grade of C or better) (MATH 114 may be taken concurrently)"
"PSYC101, PSYC111 or Permission of Instructor"
"PSYC 101 and Proficiency on Math Placement Test"
```

Same course, spelled `PSYC101` and `PSYC 101` by different publishers. A
condition carrying two courses and a grade rule in one string. A prerequisite
that may be taken concurrently, which is not a prerequisite. None of it resolves
to a course without knowing the catalogue it came from — and the Registry does
not publish that catalogue.

That is the same shape as the FDA predicate device: the relationship exists, and
the target must be guessed from a string.

## Why the walk had to be resumable

It was not resumable politeness in theory. The run **died at page 75**, twenty
minutes in, on a body the Registry stopped sending mid-read:

```
http.client.IncompleteRead(36665 bytes read, 191520 more expected)
```

`IncompleteRead` is an `http.client.HTTPException`, which was not in
`registry_read`'s caught tuple — so it escaped as a bare exception while every
other transport failure on that path arrived as `HttpStatus`. The docstring
directly above that code says the read sits inside the `with` block *for exactly
that reason*. The guard did not cover the case it was written for.

That is fixed here: transport failures retry three times with backoff, status
codes never retry — a 403 asked three times is three 403s — and the checkpoint
carried the first 75 pages so the rerun cost nothing.

## What this does not say

- **Nothing about the other 37,807 courses.** They state no prerequisite at all.
  Whether they have none, or have one their publisher did not record, is not
  something the Registry can answer.
- **Nothing about quality.** A course stating `"PSYC101"` may be stating it
  correctly. The finding is that it is not resolvable, not that it is wrong.
- **Nothing about the licence.** These records remain not-cleared for loading —
  [`registry-data-licence.md`](registry-data-licence.md) — and this walk read
  totals and one field, and stored no records.

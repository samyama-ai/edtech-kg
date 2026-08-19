# The Credential Registry — measured 2026-08-18

#28 established that CTDL has `ceterms:prerequisite`, a published `Course →
Course` edge. #53 asked the other half — **is it actually populated?** — and this page answers it.

**It is not.** Prerequisites are published, but as free text inside a
`ConditionProfile` rather than as the resolvable edge. That is the same shape as
the FDA predicate device — the relationship exists and the target must be
guessed from a string.

---

## Size

Endpoint: `credentialengineregistry.org/{community}/search`, and
`/{community}/{type}/search`. Totals from the `x-total` response header.

| Community | Records |
|---|---:|
| `ce-registry` | **671,681** |
| `fdoe` — Florida Department of Education | **10,577** |
| `mytxlibrary` — Texas | 0 |
| `learning-registry` | 0 |
| `chaffeycollege` | `secured` — refuses an unauthenticated search (401) |
| **all communities** | **682,259** — measured, not summed |
| *unattributed* | 1 — the measured total minus the four readable communities |

`ce-registry` by type:

| Type | Records |
|---|---:|
| `credential` | **133,346** |
| `course` | **47,861** |
| `learning_opportunity_profile` | 22,226 |
| `pathway` | **98** |
| `occupation` | 0 |

Two things stand out. **47,861 courses** is a serious corpus — far more than
one district. And **98 pathways** is almost nothing, which matters because the
Pathway vocabulary is the part of CTDL that impressed most in #28. The model is
rich; the published data is thin.

## The measurement that decides it

600 courses from `ce-registry` — **12 pages of 50 at a stride of 79, reaching
pages 1–870 of 958**, rather than the first 600:

| | Count | Share |
|---|---:|---:|
| Courses inspected | 600 | 1.25% of 47,861 |
| Distinct publishers in the sample | 13 | |
| **Courses** stating a prerequisite | **150** | **25%** |
| …whose prerequisite block carries nothing | 0 | not counted above |
| …pointing at a resolvable target | **0** | **0%** |
| …free text only | **150** | **100%** |

**`ceterms:prerequisite` — the `Course → Course` edge — is used zero times in
600 records.**

### The sampling, stated plainly — and why it was changed

The first version of this measurement read pages 1 to 12 consecutively. That is
not a sample of the Registry, it is a sample of whatever sorts first, which one
publisher's bulk upload can dominate. The review of this PR raised it and the
concern turned out to be real: spreading the pages across the full population
moved the rate from **83/600 to 150/600**. Courses stating a prerequisite are
almost twice as common as the head of the list suggested.

What did not move is the number that decides the question. **Zero resolvable, on
both samples.**

The spread sample is deterministic — a fixed stride, so the figure reproduces —
but it is still **not random**, and 13 distinct publishers across 600 records is
a narrow base.

**The 150 is courses, not condition profiles.** The review of this PR found the
count was per-condition, so a course carrying both "Prerequisites" and
"Prerequisite (recommended)" would have counted twice; and a profile named
"Prerequisites" whose description was absent, empty, or the word "None" counted
as stating one and then as free text. Both are fixed, and **re-measuring did not
move the figure** — no sampled course carries two matching profiles and none
carries an empty block. So the 83 → 150 rise is the sampling change, which is
what this page already claimed and can now say with the overcount ruled out
rather than assumed away.

**And it does not reach the end.** A fixed stride from page 1 stops at page 870,
so the last **88 pages — roughly 4,400 courses — are never read**. An earlier
draft of this page said "spread across all 958 pages", which claimed a reach the
method does not have. The probe now prints the range it actually covers. #58
sweeps all 47,861 and removes the caveat entirely.

What is published instead:

```json
{ "@type": "ceterms:ConditionProfile",
  "ceterms:name":        { "en-US": "Prerequisites" },
  "ceterms:description": { "en-US": "PSYC101" } }
```

Real examples from the sample:

```
PSYC101
PHOT 109
Prerequisite: PHOT109, PHOT110, and PHOT205
PSYC 101 and Proficiency on Math Placement Test
MATH 113, MATH 114 (Grade of C or better) (MATH 114 may be taken concurrently)
PSYC101, PSYC111 or Permission of Instructor
```

Not one uses `ceterms:targetLearningOpportunity` or `ceterms:targetCredential`,
which are the fields that would make the reference resolvable.

## Why this is the predicate device again

| | FDA predicate device | Registry prerequisite |
|---|---|---|
| The relationship is | published | published |
| Expressed as | free text in a PDF | free text in a JSON field |
| A resolvable form exists | no | **yes — `ceterms:prerequisite`, unused** |
| Target may not exist | yes | yes — "Permission of Instructor" |
| Machine-readable target present | 0% (measured) | 0% (measured) |
| Share of free text that *could* resolve | not measured | not measured |

Those last two rows are different claims and the earlier draft of this page ran
them together. **0% carry a machine-readable target** — that is measured, on
both sides. **What share of the free text could be resolved** against a
catalogue if we tried is a separate question, unmeasured on both sides, and the
harder one.

The difference is that here the resolvable form *exists in the standard* and
publishers are simply not using it. That is a better position than the FDA one,
and a worse one than #28 implied.

**Course codes are also local.** `PSYC101` means something inside one
institution's catalogue. Resolving it requires knowing which institution, and
whether that institution published its other courses too.

## What this does and does not change

**It does not move `docs/scope.md` §3.** Prerequisites remain unresolvable at
scale. A 25% free-text rate over 47,861 courses is not a prerequisite graph —
a quarter of courses saying *something* about prerequisites is no help when none
of it resolves.

**It does change the comparison with PWCS.** In #4, PWCS names a prerequisite on
45% of courses and **89% of those resolve** to a real course page, because both
ends come from the same catalogue. The Registry has far more courses and no
resolvability at all.

Those two PWCS figures come from #4, not from `probe_registry`, and are carried
here for comparison. They are the one thing on this page not printed by the
script — flagged rather than blended in.

**Florida published 10,577 records** into the Registry while returning 403 on its
own website (#40, #50). Whether those are courses with prerequisites was not
established — the first record sampled was a `ceterms:Collection`. That is worth
its own look, since Florida is a whole state.

## Licence

The **vocabulary** is CC BY 4.0 (#28). The **data** in the Registry is published
by many organisations under their own terms and was **not established here**.
Do not treat the CC BY 4.0 on CTDL as covering registry contents.

---

**The Registry moves.** Re-running the probe a day later already returns
133,345 credentials against the 133,346 recorded above. Figures on this page are
what the endpoints returned on the date stamped at the top; small drift on
re-run is the source changing, not the probe disagreeing with itself.

**Method.** Every figure on this page is printed by:

```bash
python -m etl.probe_registry                 # the tables above
python -m etl.probe_registry --json          # machine-readable, with timestamp
python -m etl.probe_registry --courses 2000  # widen the sample
```

The same standard as `probe_education.py`, `probe_cipsoc.py` and
`probe_state_courses.py`. **Every Registry figure on this page is printed by the
script**; the two PWCS percentages in the comparison above come from #4 and are
labelled where they appear.

It is a separate script from `probe_ctdl.py` on purpose: **the vocabulary and
the Registry are different sources with different licences**, and merging them
would blur the distinction #56 exists to protect. `probe_ctdl` imports from it,
so the Registry is measured in one place.

Totals come from `x-total` headers, which count *resources*; the API root's
`total_envelopes` counts *envelopes*. The two are reconciled in
[`ctdl.md`](ctdl.md#the-two-totals-count-two-different-things--59) against the
Registry's own source, not on this page. The
course sample parses `decoded_resource`, walks `@graph`, counts conditions by
`ceterms:name` and classifies each by whether it carries a target reference.
The probe refuses rather than reporting a rate over an empty sample.

# The Credential Registry — measured 2026-08-18

#28 established that CTDL has `ceterms:prerequisite`, a published `Course →
Course` edge. #53 asked the other half: **is it actually populated?**

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
| `chaffeycollege` | — |

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

600 courses sampled from `ce-registry`:

| | Count | Share |
|---|---:|---:|
| Courses inspected | 600 | |
| Carrying a `ceterms:requires` block | 84 | 14% |
| Whose condition is named "Prerequisites" | **83** | **14%** |
| …pointing at a resolvable target | **0** | **0%** |
| …free text only | **83** | **100%** |

**`ceterms:prerequisite` — the `Course → Course` edge — is used zero times in
600 records.**

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
| Resolution rate | unmeasured | **not yet measured** |

The difference is that here the resolvable form *exists in the standard* and
publishers are simply not using it. That is a better position than the FDA one,
and a worse one than #28 implied.

**Course codes are also local.** `PSYC101` means something inside one
institution's catalogue. Resolving it requires knowing which institution, and
whether that institution published its other courses too.

## What this does and does not change

**It does not move `docs/scope.md` §3.** Prerequisites remain unresolvable at
scale. A 14% free-text rate over 47,861 courses is not a prerequisite graph.

**It does change the comparison with PWCS.** Measured in #4: PWCS names a
prerequisite on 45% of courses and **89% of those resolve** to a real course
page, because both ends come from the same catalogue. The Registry has more
courses and worse resolvability.

**Florida published 10,577 records** into the Registry while returning 403 on its
own website (#40, #50). Whether those are courses with prerequisites was not
established — the first record sampled was a `ceterms:Collection`. That is worth
its own look, since Florida is a whole state.

## Licence

The **vocabulary** is CC BY 4.0 (#28). The **data** in the Registry is published
by many organisations under their own terms and was **not established here**.
Do not treat the CC BY 4.0 on CTDL as covering registry contents.

---

**Method.** Totals from `x-total` headers on
`credentialengineregistry.org/{community}/search` and
`/{community}/{type}/search`. Course sample: 600 records over 12 pages of 50,
`decoded_resource` parsed, `@graph` walked, conditions counted by
`ceterms:name` and classified by whether they carry a target reference. Every
figure is from that run.

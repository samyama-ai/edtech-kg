# CTDL — measured 2026-08-18

Issue #28 asked whether a pathway ontology already exists before #5 mints one.

Every figure below is produced by `python -m etl.probe_ctdl`. Nothing here is
hand-counted.

**It does — and separately, almost nobody publishes against it.** The
Credential Transparency Description Language publishes an openly licensed
vocabulary that already contains the two shapes this graph is built around,
including a direct prerequisite property. In 600 published courses that
property is used **zero times**. Both halves are the finding; the first alone
would be misleading.

---

## The vocabulary

Machine-readable JSON-LD at `credreg.net/ctdl/schema/encoding/json`, 1 MB.

| | Count |
|---|---:|
| Terms in the graph | **1,032** |
| `rdfs:Class` | **139** |
| `rdf:Property` | **411** |
| `skos:Concept` | 448 |
| `skos:ConceptScheme` | 34 |

## Licence

> *"Credential Transparency Description Language (CTDL) by Credential Engine is
> licensed under a **Creative Commons Attribution 4.0 International License**."*

Stated on both `credreg.net/page/termsofuse` and `credreg.net/registry/policy`.
The handbook adds that CTDL *"is explicitly designed to function as an openly
licensed, standalone set of schemas for use by anyone in any context in which it
is deemed useful."*

**Adoptable, with attribution.** This is the first source in the register whose
terms are unambiguous and permissive without a caveat.

## The pathway vocabulary — 17 classes

```
Pathway              PathwaySet           PathwayComponent
ComponentCondition   ConditionManifest    ConditionProfile
AssessmentComponent  BasicComponent       CocurricularComponent
CollectionComponent  CompetencyComponent  CourseComponent
CredentialComponent  ExtracurricularComponent
JobComponent         MultiComponent       WorkExperienceComponent
```

## The finding that matters: `ceterms:prerequisite`

```
ceterms:prerequisite
  domainIncludes : ceterms:Course
  rangeIncludes  : ceterms:Course
  "Course that is required as a prior condition to this course."
```

Those are the source's own property names, and the distinction is not
cosmetic. `schema:domainIncludes` is a *non-committal* list — unlike
`rdfs:domain` it carries no entailment, so a resource typed against it is not
inferred to be a Course. CTDL never says only a Course may hold this property;
it says a Course is the expected holder. Printing it as `domain` would state a
constraint the vocabulary declines to state.

**That is exactly the edge `docs/scope.md` §3 is about**, already published,
already openly licensed, already named. We were about to mint it.

And the conditional form is there too. `ComponentCondition` — *"Resource that
describes what must be done to complete a PathwayComponent"* — carries:

| property | what it does |
|---|---|
| `targetComponent` | the component the condition points at |
| `hasCondition` | a nested condition |
| `requiredNumber` | **how many of them must be satisfied** |

So *"any two of these four electives"* is expressible. Our own PWCS extract has
prose prerequisites of exactly that shape, which we planned to record as
unresolved.

## The second shape it already covers

```
ceterms:isPreparationFor / ceterms:preparationFrom
  domainIncludes : 54 types — Course, Credential, Degree, Certificate,
                   LearningProgram, AssessmentProfile, every named degree …
  rangeIncludes  : 58 types — the same, plus Occupation, Job, WorkRole,
                   ConditionProfile
```

The full lists are in `--json`; the counts are what matter here. Both are
`…Includes`, so both are expectations rather than constraints.

That is the CIP-SOC edge — *this programme prepares you for that occupation* —
expressed generically, and it reaches `Occupation`, `Job` **and** `WorkRole`,
which is finer than SOC alone.

## The Registry — now measured

`credentialengineregistry.org` publishes five metadata communities. The probe
reads each one's `x-total` header rather than paging:

| community | resources |
|---|---:|
| `ce-registry` | **671,681** |
| `fdoe` — Florida Department of Education | **10,577** |
| `mytxlibrary` — Texas | 0 |
| `learning-registry` | 0 |
| `chaffeycollege` | access-gated — 401 |
| *unattributed* | 1 |
| **all communities** | **682,259** |

Two of those are state education departments — **the same Florida and Texas
whose own websites returned 403 or carried no prerequisites in #40.** Florida
publishes 10,577 records here; Texas publishes none, so the Registry is not a
route past #40 for Texas.

`chaffeycollege` refuses an unauthenticated search, so its count is unknown;
the one resource unaccounted for between the readable communities and the global
total is presumably its. The probe prints `secured` rather than a blank, because
a gated community and an empty one are different facts and Texas's 0 is real.

### The two totals count two different things — #59

The API root reports `total_envelopes: 406,431`, *smaller* than the 682,259 that
search returns across the same communities. That looked like a contradiction. It
is not:

| | counts | value |
|---|---|---:|
| root `total_envelopes` | **envelopes** — the deposited documents | 406,431 |
| search `x-total` | **resources** — JSON-LD objects inside them | 682,259 |

From the Registry's own source, `app/api/v1/root.rb` computes the root figure as
`Envelope.not_deleted.count`, while search queries `EnvelopeResource`, which the
model file describes as *"A JSON-LD object stored in an envelope."* One envelope
can hold many: sampling across the result set found envelopes carrying up to
**49 resources**, though most carry one.

Two other explanations were plausible and were measured rather than argued away.
Both are zero — `include_deleted=only` returns 0 and `provisional=only` returns
0 — so neither deleted nor unpublished records account for the difference.

**Which figure to use: the resource count.** "How many courses are published" is
a question about resources. The envelope count answers "how many documents were
deposited", which is not a question this graph asks. The `course` and `pathway`
figures below are resource counts and are the right basis for the ratio.

Within `ce-registry`, by type — resource counts on the basis just established:

| type | resources |
|---|---:|
| `credential` | 133,346 |
| `course` | **47,861** |
| `learning_opportunity_profile` | 22,226 |
| `pathway` | **98** |

Ninety-eight pathways against 47,861 courses is the headline, and it survives
#59: both are resource counts on the same basis, so the ratio is a like-for-like
comparison rather than an artefact of counting documents against objects.

## The edge exists and nobody uses it

`python -m etl.probe_registry` samples 600 published courses and looks for a
stated prerequisite:

| | courses |
|---|---:|
| sampled | 600 — spread across all 47,861, not the first 600 |
| stating a prerequisite | **150** |
| by a resolvable reference | **0** |
| as free text only | **150** |

`ceterms:prerequisite` — the typed Course→Course edge this document opened by
celebrating — is used **zero times in 600 courses**. Every one of the 150 is a
`ConditionProfile` whose content is a description string:

```
PSYC101
PHOT 109
Prerequisite: PHOT109, PHOT110, and PHOT205
MATH 113, MATH 114 (Grade of C or better) (MATH 114 may be taken concurrently)
```

Resolving `"PSYC101"` means knowing which catalogue it belongs to, and the
record does not say. So the finding splits in two, and both halves are real:

- **as a schema**, CTDL gives us the edge and we should adopt it (#33);
- **as a data source**, it does not give us a single resolved prerequisite.

The 600 are spread at a fixed stride across all 958 pages rather than taken
from the head, after the review of #57 pointed out that a consecutive read
samples whatever sorts first. That correction nearly doubled the number of
courses *stating* a prerequisite — and left the resolvable count at zero. #58
sweeps all 47,861 to remove the caveat.

The Registry figures on this page come from `python -m etl.probe_registry`; the
vocabulary figures from `python -m etl.probe_ctdl`. Two sources, two licences,
two scripts.

## What this means for #33 and #5

The reuse decision has a strong candidate.

**The table below is a first reading, not the #33 decision.** It records which
CTDL term looks like the counterpart of each of our shapes, from the vocabulary
definitions alone. It has not been checked against how the terms are used in
published data — and the section above shows exactly why that gap matters:
`ceterms:prerequisite` reads as a perfect match and is used zero times. #33 owns
the decision, has to reconcile CTDL against CEDS (#29) and SCED (#34), and is
free to conclude differently.

| our shape | CTDL term | first reading |
|---|---|---|
| Course | `ceterms:Course` | adopt |
| Course requires Course | `ceterms:prerequisite` | **adopt** |
| "N of these" | `ceterms:ComponentCondition` + `requiredNumber` | adopt |
| Programme → Occupation | `ceterms:isPreparationFor` | align — ours is CIP-SOC specific |
| Occupation | `ceterms:Occupation` | adopt |
| Institution | `ceterms:CredentialOrganization` | align |

Minting a prerequisite edge under our own name would now require the sentence
#33 demands: *what the external term could not express.* On this evidence there
is no such sentence.

## What is still open

- **Whether any publisher anywhere uses the typed edge.** 600 courses found
  none. A full sweep of 47,861 is a different job and may find one
- Whether Florida's 10,577 records contain course data with prerequisites,
  which would be a direct route past #40's finding. Texas publishes nothing
  here, so that half is closed
- How CTDL relates to CEDS (#29) and SCED (#34) — three vocabularies that may
  overlap, and #33 has to reconcile them rather than adopt all three

---

**Method.** Every figure from `python -m etl.probe_ctdl`, measured
2026-08-18. Vocabulary counted from the JSON-LD at
`credreg.net/ctdl/schema/encoding/json`, parsed with the standard library — no
third-party dependency, as with the other probes. Property expectations read
from `schema:domainIncludes` and `schema:rangeIncludes` and printed under those
names. Registry totals from each community's `x-total` response header, which counts
resources; the root's `total_envelopes` counts envelopes, and the two are
reconciled above against `app/api/v1/root.rb` and `app/models/envelope_resource.rb`
in `github.com/CredentialEngine/CredentialRegistry`.
Prerequisite rate from a 600-course sample of `/ce-registry/course/search`.
Licence quoted from `credreg.net/page/termsofuse`.

The probe refuses rather than reports a zero it cannot vouch for: an empty
vocabulary graph, a response that is not JSON, or a sample containing no
courses each exit non-zero instead of printing a table. `tests/test_probe_ctdl.py`
covers those refusals and the parsing; both were mutation-tested.

**Licence caution.** CC BY 4.0 covers *the vocabulary*. Records in the Registry
are published by many organisations under their own terms and that licence does
not transfer — see #56. Nothing on this page loads Registry data.

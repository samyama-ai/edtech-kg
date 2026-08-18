# CTDL — measured 2026-08-18

Issue #28 asked whether a pathway ontology already exists before #5 mints one.

**It does, and it is closer than expected.** The Credential Transparency
Description Language publishes an openly licensed vocabulary that already
contains the two shapes this graph is built around — including a direct
prerequisite property.

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
  domain : ceterms:Course
  range  : ceterms:Course
  "Course that is required as a prior condition to this course."
```

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
  domain includes : Course, Credential, Degree, Certificate, LearningProgram …
  range includes  : Occupation, Job, WorkRole, Credential, Course …
```

That is the CIP-SOC edge — *this programme prepares you for that occupation* —
expressed generically, and it reaches `Occupation`, `Job` **and** `WorkRole`,
which is finer than SOC alone.

## The Registry — partially measured, and said so

`credentialengineregistry.org` reports **406,431 total envelopes** across five
metadata communities:

| community | |
|---|---|
| `ce_registry` | the main one |
| `learning_registry` | |
| **`fdoe`** | **Florida Department of Education** |
| **`mytxlibrary`** | **Texas** |
| `chaffeycollege` | a single college |

Two of those are state education departments — **the same Florida and Texas
whose own websites returned 403 or carried no prerequisites in #40.**

**What is in them was not measured.** `/ce-registry/assistant/search` responds
200, so the path shape is right, but the query form was not worked out inside
this session. The documented entry points are the Swagger at
`credentialengineregistry.org/swagger/index.html` and the repository at
`github.com/CredentialEngine/CredentialRegistry`. Recording that as unfinished
rather than guessing at a count.

**Until it is measured, CTDL is a schema we can adopt, not a data source we can
load.** The distinction matters and should not blur.

## What this means for #33 and #5

The reuse decision has a strong candidate. On a first reading:

| our shape | CTDL term | likely verdict |
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

- **What the Registry actually holds**, by type — the unfinished half above
- Whether the `fdoe` and `mytxlibrary` communities contain course data with
  prerequisites, which would be a direct route past #40's finding
- How CTDL relates to CEDS (#29) and SCED (#34) — three vocabularies that may
  overlap, and #33 has to reconcile them rather than adopt all three

---

**Method.** Vocabulary counted from the JSON-LD at
`credreg.net/ctdl/schema/encoding/json`, parsed with the standard library.
Property domains and ranges read from `schema:domainIncludes` and
`schema:rangeIncludes`. Licence quoted from `credreg.net/page/termsofuse`.
Registry envelope count from `credentialengineregistry.org/` root. Every figure
is from that run; nothing is estimated.

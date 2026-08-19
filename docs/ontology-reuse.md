# Ontology reuse decision — measured 2026-08-18

Issue #33 exists to prevent one specific failure: five separate investigations
that each conclude "interesting", followed by an ontology that quietly reinvents
all of them under different names.

**This document is a partial verdict, and says so where it is not one.** #33
depends on five investigations. Two have reported — CTDL (#28, #53) and
schema.org (#30, measured here). Three have not: CEDS (#29), Ed-Fi (#31) and
CASE (#32). Every row below carries its status, and the rows those three would
change are marked **provisional** rather than decided.

Issuing the decided rows now rather than holding the whole table is deliberate.
The alternative is that #5 waits on all five, and the schema — the thing this
repo exists to produce — stays a placeholder. `docs/schema.md` is still the
unedited repo template.

---

## The rules, from #33

- **adopt** — we use their name verbatim
- **align** — ours differs, and a documented mapping exists
- **mint** — requires a sentence naming the external term that was rejected and
  what it could not express

Every external term is linked to its definition so a reader can check the
mapping rather than trust it.

---

## The decision

### Nodes

| our name | external term | verdict | why |
|---|---|---|---|
| `Course` | [`schema:Course`](https://schema.org/Course) · [`ceterms:Course`](https://credreg.net/ctdl/terms/Course) | **adopt** | Both define it identically. schema.org is the wider-published name |
| `Programme` | [`schema:EducationalOccupationalProgram`](https://schema.org/EducationalOccupationalProgram) | **align** | Ours is CIP-coded and US-specific; theirs is generic. Mapping is 1:1 on identity, ours adds `cip_code` |
| `Occupation` | [`schema:Occupation`](https://schema.org/Occupation) · [`ceterms:Occupation`](https://credreg.net/ctdl/terms/Occupation) | **adopt** | |
| `Institution` | [`schema:CollegeOrUniversity`](https://schema.org/CollegeOrUniversity) | **align** | Ours is keyed on IPEDS UNITID and covers non-degree providers too — see #45 |
| `Credential` | [`schema:EducationalOccupationalCredential`](https://schema.org/EducationalOccupationalCredential) | **adopt** | |
| `Standard` / competency | [`CASE`](https://www.imsglobal.org/spec/case/v1p0) | **provisional — blocked on #32** | Not decided. #32 has not reported |
| `School`, `District` | Ed-Fi | **provisional — blocked on #31** | Not decided. #31 has not reported |

### Edges

| our name | external term | verdict | why |
|---|---|---|---|
| `Course REQUIRES Course` | [`schema:coursePrerequisites`](https://schema.org/coursePrerequisites) | **adopt** | See below — this is the one that changed |
| `Programme PREPARES_FOR Occupation` | [`ceterms:isPreparationFor`](https://credreg.net/ctdl/terms/isPreparationFor) | **align** | Ours is the CIP-SOC crosswalk specifically, a narrower and government-published claim. Theirs reaches `Occupation`, `Job` and `WorkRole`; ours only the first |
| `Programme HAS_COURSE Course` | [`schema:hasCourse`](https://schema.org/hasCourse) | **adopt** | |
| `Institution OFFERS Programme` | [`schema:provider`](https://schema.org/provider) | **align** | `provider` spans 20+ domains across schema.org and ranges over `Organization`/`Person`; ours is institution-to-programme only |
| `Programme AWARDS Credential` | [`schema:educationalCredentialAwarded`](https://schema.org/educationalCredentialAwarded) | **adopt** | |
| `Occupation` → SOC code | [`schema:occupationalCategory`](https://schema.org/occupationalCategory) | **adopt** | `rangeIncludes` `CategoryCode`, which is what a SOC code is |
| `Course ALIGNS_TO Standard` | CASE / CEDS | **provisional — blocked on #29, #32** | Not decided |

**Nothing is minted.** That is the finding, not a formality: every shape this
graph needs for its answerable questions already has a published name.

---

## The row that changed: prerequisites

This was going to be `ceterms:prerequisite`. #28 found it and recommended it —
a direct `Course → Course` property, openly licensed, exactly the edge
`docs/scope.md` §3 is about.

Then #53 measured whether anyone uses it. **Zero times in 600 published
courses.** All 150 courses that state a prerequisite state it as a
`ConditionProfile` description string — `"PSYC101"`, `"MATH 113, MATH 114 (Grade
of C or better)"`.

The reason is visible in the two definitions:

| | range | what it permits |
|---|---|---|
| [`ceterms:prerequisite`](https://credreg.net/ctdl/terms/prerequisite) | `ceterms:Course` | a course reference, and nothing else |
| [`schema:coursePrerequisites`](https://schema.org/coursePrerequisites) | `schema:Course`, `schema:Text`, `schema:AlignmentObject` | a course reference, **or free text**, or a competency |

schema.org's own definition says it outright: *"May be completion of another
Course or a textual description like 'permission of instructor'."*

CTDL modelled the prerequisite as publishers *should* record it. schema.org
modelled it as publishers *do* record it. The measured data says publishers
record free text, and a property that cannot hold free text is a property that
gets left empty — which is precisely what 47,861 courses and zero uses look
like.

**So: adopt `schema:coursePrerequisites`, with the target typed on our side.**
An edge to a resolved `Course` where we can resolve it; the original string
retained where we cannot. That is not a compromise, it is what the standard
already permits, and it means an unresolved prerequisite is recorded as data
rather than discarded.

`ceterms:prerequisite` remains the right term to *emit* if we ever publish back
to the Registry. It is the wrong term to model on.

---

## What is measured, and what is not

| investigation | issue | status | effect on this table |
|---|---|---|---|
| CTDL vocabulary | #28 | ✅ measured | 3 rows |
| Credential Registry usage | #53 | ✅ measured | decided the prerequisite row |
| schema.org | #30 | ✅ measured here — 14 of 14 terms present | 8 rows |
| CEDS v12 | #29 | ❌ not started | 1 provisional row |
| Ed-Fi | #31 | ❌ not started | 1 provisional row |
| CASE Network | #32 | ❌ not started | 2 provisional rows |

**Four rows are provisional.** They are the school-system side — districts,
schools, standards and competencies — which is also the side the answerable
questions lean on least (see `docs/questions.md`: everything in section A is
blocked on data we do not have). The decided rows cover programme → occupation
→ earnings, which is the demo that is defensible today.

#33 should not close until #29, #31 and #32 report. This document is the
half of it that can be decided now.

---

## Licences of the vocabularies adopted

| vocabulary | licence | effect |
|---|---|---|
| schema.org | [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/) | attribution; applies to the vocabulary, not to our data |
| CTDL | [CC BY 4.0](https://credreg.net/page/termsofuse) | attribution |

Adopting a term name is not the same as ingesting a vocabulary, and neither is
the same as loading the Registry's records — those are published by many
organisations under their own terms (#56). Three separate questions.

---

**Method.** schema.org figures from:

```bash
python -m etl.probe_schemaorg          # the table above
python -m etl.probe_schemaorg --json   # machine-readable, with timestamp
```

CTDL and Registry figures from `python -m etl.probe_ctdl` and
`python -m etl.probe_registry`. Property ranges are read from
`schema:rangeIncludes` and printed under that name — these are non-committal
lists carrying no entailment, not `rdfs:range`, and the distinction is the whole
argument of the prerequisite section above.

Nothing on this page is hand-typed. Each probe refuses rather than reporting a
figure it cannot vouch for: an error page served with a 200 would otherwise show
every schema.org term as absent, which reads as "schema.org does not define
these" rather than "the fetch broke".

**The citations are checkable, and checked.** #33 requires that a reader be able
to verify each mapping rather than trust it, which only holds while the links
resolve. All sixteen definition URLs on this page are verified by:

```bash
python -m etl.probe_schemaorg --check-urls   # 16 checked, 0 broken
```

It exits non-zero if any citation has rotted, so this page failing an audit is
a build signal rather than something a reader discovers.

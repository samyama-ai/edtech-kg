# Florida in the Credential Registry — measured 2026-09-03

Answering edtech-kg#55. Every figure is printed by `python -m etl.probe_florida`,
which writes [`florida-registry-measured.json`](florida-registry-measured.json).
Nothing here is hand-counted.

**The headline: Florida published no courses at all.** Not few, not
prerequisite-free — **zero**. So the question #55 was raised to settle, whether
these records are the state-level prerequisite source #40 concluded does not
exist, is answered no, and answered by a census rather than a sample.

The second finding was not asked for and is worth more than the first: **every
credential sampled carries a CIP code.**

## What is in `fdoe` — a census, not a sample

The Registry reports `x-total` per type, so fourteen HEAD requests count every
record without reading one.

| type | records |
|---|---|
| `credential` | **10,241** |
| `organization` | 336 |
| `collection` | 1 |
| **`course`** | **0** |
| `pathway` | 0 |
| `learning_opportunity_profile` | 0 |
| the other eight types asked about | 0 |
| **unattributed** | **0** |

10,241 + 336 + 1 = 10,578, which is the whole-community total. The remainder is
zero, so this is the whole community and not the part of it we happened to ask
about. The probe refuses to report the breakdown if it does not close.

#55 quoted **10,577**, measured 2026-08-18. It is 10,578 today. One record in
sixteen days; the community is not being actively loaded.

## No courses means no prerequisites, trivially

`docs/scope.md` §3 stands unchanged. There is nothing here to change it with.

This matters beyond Florida. §3's finding is that no state publishes
course-level prerequisites in machine-readable form, and Florida was the
strongest remaining candidate — a whole state, in a standard vocabulary, on an
endpoint that answers, from a department whose own site returns 403 to
everything (#40, #50). It publishes credentials, not courses.

## What the 10,241 credentials are

Sampled 400 across 8 of 205 pages, drawn at a stride. **This part is a sample
and the figures below are shares of it, not of the community.**

The stride matters here more than usual: `fdoe` has two publishers, and page 1
carries no `ceterms:requires` on any record while later pages carry it on
every one. Reading the first N pages would have produced a confidently wrong
coverage figure.

| type | of 400 |
|---|---|
| `ceterms:Certificate` | 165 |
| `ceterms:BachelorDegree` | 83 |
| `ceterms:AssociateDegree` | 62 |
| `ceterms:MasterDegree` | 50 |
| `ceterms:DoctoralDegree` | 35 |
| `ceterms:License` | 3 |
| `ceterms:ApprenticeshipCertificate` | 2 |

## The finding that was not asked for

| field | of 400 | |
|---|---|---|
| `ceterms:instructionalProgramType` | **400** | **100%** |
| `ceterms:availableAt` | 400 | 100% |
| `ceterms:subjectWebpage` | 400 | 100% |
| `ceterms:requires` | 350 | 88% |
| `ceterms:identifier` | 350 | 88% |
| `ceterms:occupationType` | 50 | 12% |
| `ceterms:estimatedCost` | 50 | 12% |

`instructionalProgramType` is **CIP**, carried properly rather than as a name:

```json
{ "@type": "ceterms:CredentialAlignmentObject",
  "ceterms:framework": "https://nces.ed.gov/ipeds/cipcode/Default.aspx?y=56",
  "ceterms:targetNode": ".../cipdetail.aspx?y=56&cip=51.0904",
  "ceterms:codedNotation": "51.0904",
  "ceterms:frameworkName": { "en-US": "Classification of Instructional Programs" } }
```

`occupationType` is O\*NET-SOC in the same shape — `29-2042.00`, framework
`onetcenter.org/taxonomy.html`.

**So a Florida credential reaches an occupation without any course data at
all.** The CIP is on effectively every record, and the repo already holds the
CIP-SOC crosswalk (#12). The direct SOC alignment is on 12%, so the crosswalk
is the path that covers the set, not the 12%.

That is a weaker claim than the one this graph is for. A credential is not a
course, and "this programme leads to that occupation" is not "take this course
next semester". But it is statewide, machine-readable, and it exists today —
the same argument #49 makes for the Texas cluster data, from a different
direction.

## What `ceterms:requires` holds, and why it is not a prerequisite

88% carry it, and **none of it is a prerequisite**. The conditions are
**unnamed** and hold an admissions link and a credit total:

```json
{ "@type": "ceterms:ConditionProfile",
  "ceterms:condition": { "en-US": ["https://fiuonline.fiu.edu/admissions/graduate.php"] },
  "ceterms:creditValue": [ { "schema:value": 42.0, "creditUnitType": "DegreeCredit" } ] }
```

An admission requirement and a programme size. Neither points at a course.

**One thing this exposes about our own tooling.** `registry_courses.classify`
only reads a condition whose *name* mentions "prereq". Every condition here is
unnamed, so the classifier scores all 10,241 as stating nothing — which is the
right answer for the wrong reason. It is right here because the content is an
admissions URL; it would be wrong for a publisher who states a real
prerequisite in an unnamed condition. Recorded rather than fixed, because
changing that test moves the figure `ctdl.md` quotes and belongs with #58.

## Does it join to Florida's own course codes?

**No.** The only `ceterms:identifier` is an FLVC publication status:

```json
{ "@type": "ceterms:IdentifierValue",
  "ceterms:identifierTypeName": { "en-US": "FLVC Public Status" },
  "ceterms:identifierValueCode": "Public" }
```

Not a course code, not a programme code, nothing that joins to the state course
directory measured in #40.

## Licence

Unchanged by this page, and already answered: **the Registry's records are not
openly licensed** — see [`registry-data-licence.md`](registry-data-licence.md),
which settles #56. CC BY 4.0 covers CTDL the vocabulary, not the contents, and
`fdoe`'s records carry no separate grant. Reading them to establish what exists
is not the same as redistributing them, and nothing here is loaded.

## Verdict

- **`docs/scope.md` §3 does not move.** Florida publishes no courses.
- **#55 is answered no**, and the no is a census.
- **A credential-to-CIP link exists statewide** and is worth its own issue if
  credentials ever enter scope; it does not belong to this one.
- The gap between "Florida's own site 403s" and "Florida publishes ten thousand
  records here" is real but is not a prerequisite gap. They are publishing
  their *credential inventory*, not their curriculum.

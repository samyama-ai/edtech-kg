# Scope decision

What this knowledge graph covers, what it deliberately does not, and why. Made
before the ontology exists, so the schema inherits a decision rather than a
drift.

The reasoning matters more than the boundary. Anyone can move a boundary; the
cost of moving it is only visible if the argument is written down.

---

## In scope

**US education-to-occupation pathways.** A programme of study, the occupations
it leads to, what those occupations pay, which institutions award it, and how
many people actually complete it.

| | What it contributes |
|---|---|
| **Programme** (CIP code) | The unit a student chooses and an institution awards |
| **Occupation** (SOC code) | Where a programme leads |
| **Institution** | Who awards it, and whether they actually graduate anyone |
| **Award level** | Certificate, associate, bachelor's — the cost-of-entry question |
| **Completions** | Awards conferred, by demographic |
| **Earnings & outlook** | What the destination is worth |

The spine is the **NCES–BLS CIP-SOC crosswalk**: a government-published, exact
mapping from degree programme to occupation. Everything answerable in
[`questions.md`](questions.md) traverses it. It plays the same structural role
`regulation_number` plays in `regulatory-affairs-kg` — one exact join, not a
name match.

**Course-level prerequisites for a single district**, as a second tier — see
the boundary below.

## Out of scope, and why

### 1. Individual student records — permanently

No enrolment records, transcripts, test scores or anything else about a named
person. Not "not yet": **not ever**.

The questions this graph answers are about programmes, occupations and
institutions. None of them needs a student. Holding student data would add
FERPA obligations, consent machinery and breach exposure to a graph built
entirely from public aggregates — a change of category, not of scale.

The schema must make this impossible to add casually, not merely absent.

### 2. Non-US education systems — for now

IPEDS, CCD, CIP-SOC, O\*NET and College Scorecard are US federal collections.
Nothing equivalent exists cross-nationally at this granularity: there is no
international CIP-SOC, and qualification frameworks are not comparable across
borders without judgement we are not qualified to make.

A second country is a second graph, not more rows in this one. Saying so now
prevents a schema that pretends to be universal and is quietly US-shaped.

### 3. National course-level prerequisites — because they do not exist

Measured 2026-08-17. There is no national machine-readable source of school
course prerequisites:

- Federal open data (`data.ed.gov`, NCES EDGE) stops above the course
- The Urban Institute API — our own source — stops at the institution
- **Ed-Fi** models course data and is widely adopted, but it is how districts
  exchange data with their own vendors, not a public feed
- State course directories publish titles and descriptions; prerequisites
  appear in prose if at all
- **SCED**, the national course taxonomy, defines a `Sequence of Course`
  element — and it means "part *n* of *m* parts", one course split across
  terms, not a prerequisite between two courses. Neither the master file nor
  the one SCED-keyed state directory publishes it anyway. See
  [`sources/sced.md`](sources/sced.md)

What does exist: individual districts publishing a program of studies. **Prince
William County Public Schools** publishes 982 course pages with an explicit
prerequisites field, and **89% of the named prerequisites resolve** to a real
course page (sample of 40, `random.seed(7)`).

**So prerequisites are in scope for one named district and out of scope
nationally.** Any answer derived from them must say whose catalogue it came
from. A national claim would be false, and the graph must not make one easy to
state by accident.

### 4. Predicting outcomes

The graph records what is published: how many completed, what the occupation
pays, what the crosswalk maps. It does not forecast whether a particular
student will get a job, and no edge should imply that it might.

Where two public series are compared — graduates against hiring — the answer
carries the caveat that they were collected independently. Directional, not a
labour-market forecast.

---

## Sources and licences

Per the review of 2026-08-17, the licence of every source is checked before
anything is published from it.

| Source | Publisher | Licence position |
|---|---|---|
| IPEDS (completions, directory) | NCES | US-government public domain |
| CCD (schools, districts) | NCES | US-government public domain |
| CIP-SOC crosswalk | NCES + BLS | US-government public domain |
| O\*NET crosswalk workbooks | US Dept of Labor | CC BY 4.0 by the crosswalks page's own notice, checked 2026-08-31 — **not** the Database licence, which excludes that page. Attribution wording and the version rule in [`sources/licences.md`](sources/licences.md) |
| College Scorecard | US Dept of Education | US-government public domain |
| Urban Institute Education Data API | Urban Institute | Republishes the federal data above under Open Data Commons Attribution (ODC-By) v1.0, checked 2026-08-31. Reuse and re-sharing permitted; citation requested — [`sources/licences.md`](sources/licences.md) |
| PWCS course catalogue | Prince William County Public Schools | **A public catalogue, but reuse permission is a human decision — not settled.** See #4 |

One of those is still an open question, and it is open in this document rather
than discovered later. **The PWCS catalogue should not be treated as cleared
until someone has cleared it** — its reuse permission is a human decision, not
a published licence.

The Urban Institute wrapper and O\*NET were the other two, and both were
cleared on 2026-08-31 by reading the terms rather than assuming them; see
[`sources/licences.md`](sources/licences.md). O\*NET did not clear the way the
question assumed: the Database content licence names the pages it applies to
and the crosswalks page is not among them, so the workbooks this repo reads
are covered by a separate notice that happens to say the same thing.

Raw data is never committed. The repo ships downloaders, loaders, schema and a
bounded demo, and cites its sources — the convention across every `*-kg` repo.

---

## What a reader must not conclude from this graph

Written now, before anyone can be misled by it.

- **That a programme causes an outcome.** The crosswalk is expert judgment
  about what a programme prepares you for. NCES says so themselves. It is not
  measured employment.
- **That the prerequisite chains describe US schooling.** They describe one
  district's catalogue at one point in time.
- **That completion counts are enrolment.** They count awards conferred, which
  is why "does this college actually graduate anyone in this?" is answerable —
  and why "how many are studying it?" is not.
- **That earnings figures cover all graduates.** College Scorecard earnings
  cover federal-aid recipients only. That cohort is not everyone, and the
  caveat travels with every answer derived from it.
- **That an absent edge means no relationship.** Partial coverage is recorded
  as partial. An unresolved prerequisite is modelled explicitly rather than
  dropped — a truncated chain that looks complete is worse than no chain.

---

## What would change this decision

- **A second district resolving as cleanly as PWCS** would move prerequisites
  from "one named district" toward something generalisable — and would change
  the product from a per-district integration into a national one. That test is
  in #4 and has not been run.
- **A public national prerequisite source appearing** would make §3 obsolete.
- **A partner supplying student data under proper consent** would not change
  §1. That would be a different system with different obligations, not this
  graph with more nodes.

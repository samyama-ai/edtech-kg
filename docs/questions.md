# The questions this graph must answer

Written before any ontology, in the language the asker uses — not in the shape
of the data. Every node and edge in the schema has to earn its place by turning
one of these into a single traversal. Anything serving none of them stays out.

This mirrors how `regulatory-affairs-kg` was built: questions first, schema
second. It is also how the honest limits surface early — a good number of the
questions below cannot be answered from public data, and saying so now is
cheaper than discovering it after a loader exists.

**102 questions, tiered by the kind of query each needs.**

---

## Why they are tiered

The tiers run from what a spreadsheet does well to what only a graph does at
all. That progression is the demo: same data, same graph, and the relational
answer gets worse as the tier climbs.

| Tier | Needs | Honest verdict on a relational database |
|---|---|---|
| **1** | Lookup, key-value | Does this perfectly. Baseline |
| **2** | One relation, one hop | A join. Does this fine |
| **3** | Change impact — what moves when a code set or record is revised | Possible, but every new hop is another join written by hand |
| **4** | **Unknown-depth traversal, shortest path, reachability** | Badly or not at all — recursive CTEs, and you must know the depth |
| **5** | Multi-domain: prerequisites × programmes × occupations × geography | Query becomes unmaintainable |
| **6** | Whole-graph structure — centrality, components, bottlenecks | Not a database question at all |

**Tiers 1 and 2 are not filler.** A demo that opens at tier 4 invites *"couldn't
you have done that in Postgres?"* The earlier tiers are what make the answer
credible.

## Status key

| | |
|---|---|
| ✅ | answerable from a source measured by a probe in `etl/` |
| ⚠️ | answerable, with a caveat that must travel with the answer |
| ❌ | needs data we do not have and may not be able to get |

**Statuses were re-checked on 2026-08-19, not carried over.** Two changed:

- **Section A came off ❌.** Course prerequisites were listed as unpublished.
  `docs/sources/course-prerequisites.md` measures 240 resolvable prerequisite
  edges across 960 PWCS courses, every link resolving. Those questions are now
  the tier-4 showcase.
- **Pay and outlook came off ✅.** `docs/sources/education-data.md` lists BLS,
  O\*NET and College Scorecard as *"named but not counted"* — no probe measures
  them. They are ⚠️ until one does (#37, #21).

**On prerequisites, the scope is one district.** PWCS, 960 courses. Questions
that traverse prerequisites are written district-scoped and say so; #40 showed
statewide directories publish none, and whether a second district resolves as
cleanly is #19, still open. The caveat travels with the answer rather than being
hidden behind a national phrasing.

---

## Tier 1 — lookup

*A table does this well. These prove the data loaded and the keys are right.*

**Q1.** What is this programme called, and what is its CIP code? ✅
**Q2.** What occupation does this SOC code name? ✅
**Q3.** How many institutions are in the directory? ✅ — 6,256 measured
**Q4.** How many schools and districts are there? ✅ — 102,268 and 19,714
**Q5.** How many CIP-SOC mappings exist? ✅ — 6,097 measured
**Q6.** How many distinct programmes appear in the crosswalk? ✅ — 2,143
**Q7.** How many distinct occupations? ✅ — 868
**Q8.** How many courses does this district publish? ✅ — 960
**Q9.** What are this course's grade levels and length? ✅
**Q10.** Which schools teach this course? ✅
**Q11.** What award levels does this institution grant? ✅
**Q12.** Where is this institution, and is it public or private? ✅
**Q13.** How many people completed this programme at this institution? ✅
**Q14.** What is this course's description, as the district publishes it? ✅
**Q15.** Which courses are flagged as career-and-technical education? ✅
**Q16.** How many courses carry a free-text requirement rather than a linked
prerequisite? ✅ — 138 measured, and they are not edges
**Q17.** What does this occupation pay? ⚠️ — source named, not yet measured
**Q18.** Is this occupation growing or shrinking? ⚠️ — same
**Q19.** What does this programme cost? ⚠️ — College Scorecard, unmeasured
**Q20.** What is this student's record? ❌ — permanently out of scope (`scope.md` §1)

## Tier 2 — one hop

*A join does this. Still not a graph argument.*

**Q21.** This degree programme — what jobs does it lead to? ✅
**Q22.** I want this job. Which programmes lead to it? ✅
**Q23.** Which colleges near me offer this programme? ✅
**Q24.** Of those, which actually graduate people in it, rather than listing it? ✅
**Q25.** Which institutions award this programme at certificate level? ✅
**Q26.** Which courses in this district list a prerequisite at all? ✅ — 229 of 960
**Q27.** What is the immediate prerequisite of this course? ✅ — district-scoped
**Q28.** Which courses name this one as their prerequisite? ✅ — the reverse edge
**Q29.** How many people graduated in this programme nationally last year? ✅
**Q30.** Which districts contain this school? ✅
**Q31.** Which programmes does this institution offer that map to healthcare
occupations? ✅
**Q32.** Which occupations does this programme lead to that need only a
certificate? ⚠️ — award level is measured, entry requirement is not
**Q33.** What do graduates of this programme earn? ⚠️ — federal-aid recipients
only; the cohort is not all graduates
**Q34.** Which courses at this school have no prerequisite — the entry points? ✅
**Q35.** Which occupations are reachable from programmes this institution
offers? ✅
**Q36.** Which programmes here are dead ends, mapping to only one occupation? ✅
**Q37.** Which occupations can be reached from the most different programmes? ✅
**Q38.** Which high schools feed this district's students into this programme? ❌
— needs student-level movement data we will not hold
**Q39.** Which courses satisfy this programme's entry requirement? ❌ — no public
source links a district course to a college programme's entry rules
**Q40.** Which employers hire from this programme? ❌ — no public source
**Q41.** Which courses map to this competency? ❌ — see *the competency gap* below
**Q42.** How many pathways does the Credential Registry publish? ⚠️ — 98
measured, but the records are published under their publishers' own terms (#56)

## Tier 3 — change impact

*Where a graph starts to pay. Each of these is "something changed — what moves?"*

**Q43.** The CIP-SOC crosswalk is revised. Which programmes change what they
lead to? ✅ — the direct analogue of the FDA change-impact query
**Q44.** …and which students are affected? ❌ — student data, out of scope
**Q45.** An occupation's outlook is downgraded. Which programmes feed it? ✅
**Q46.** A programme is discontinued at an institution. What was it feeding? ✅
**Q47.** This occupation now requires a licence. Which programmes lead to it? ✅
**Q48.** A course is removed from the district catalogue. Which courses lose a
prerequisite? ✅ — district-scoped
**Q49.** A course's prerequisite changes. Which downstream courses are affected? ✅
**Q50.** A CIP code is retired between revisions. What breaks? ✅
**Q51.** A SOC code is split into two. Which programmes now point at both? ✅
**Q52.** An institution closes. Which occupations lose a route in this region? ✅
**Q53.** A school stops offering a course. Which pathways at that school break? ✅
**Q54.** A district adds a course. What does it newly make reachable? ✅
**Q55.** Earnings data is revised. Which programme rankings move? ⚠️ — unmeasured
source
**Q56.** A course is renamed. Do its inbound prerequisite links survive? ✅ — they
are URLs, not names, so yes; worth demonstrating
**Q57.** A state changes graduation requirements. Which courses become
mandatory? ❌ — #41, not researched
**Q58.** An accreditation lapses. What is affected? ❌ — no source
**Q59.** A competency framework is revised. Which courses change? ❌ — competency
gap
**Q60.** The crosswalk gains a mapping. Which occupations become newly reachable
from this institution? ✅

## Tier 4 — graph algorithms

*The reason to use a graph. Each names the operation it needs.*

**Q61. If I skip chemistry this year, what does that close off later?** ✅
*Blast radius — transitive closure over prerequisites, unknown depth.* District-
scoped. Structurally identical to the regulatory KG's *"this rule changed, which
devices are affected?"*
**Q62. What is the shortest route from where I am now to this programme?** ✅
*Shortest path.* District-scoped.
**Q63. I'm in year 11 and I've taken these five courses. What am I still
missing?** ✅ *Set difference over a reachability set.*
**Q64. I was heading for accounting, now I want data analysis. What carries
over?** ✅ *Intersection of two ancestor sets.*
**Q65. I want to be a nurse. What do I take next semester?** ✅ *Frontier of the
reachable set given what is completed.* The question the product exists for.
**Q66.** How deep does the deepest prerequisite chain run? ✅ *Longest path.*
The edges are measured and the depth is computed from them; the probe reports
edge counts, not path length, so the number itself is not in a document yet.
**Q67.** Which courses are unreachable from any entry point? ✅ *Reachability
from sources.* Orphans are a data-quality finding as much as a student one.
**Q68.** Which single course, if removed, disconnects the most others? ✅
*Articulation points.*
**Q69.** What is the full ancestor set of this course? ✅ *Transitive closure.*
**Q70.** What is its full descendant set — everything it unlocks? ✅
**Q71.** Are there cycles in the prerequisite graph? ✅ *Cycle detection.* A cycle
is a publishing error and finding one is worth reporting to the district.
**Q72.** Which two courses are furthest apart in the prerequisite graph? ✅
*Graph diameter.* Computable from the measured edges; like Q66, the value
itself has not been computed and put in a document yet.
**Q73.** How many distinct prerequisite chains lead to this course? ✅ *Path
enumeration.*
**Q74.** Which courses sit on the most paths between others? ✅ *Betweenness
centrality* — the real bottleneck courses.
**Q75.** Given a target occupation, what is the shortest course sequence in this
district that reaches a programme leading to it? ✅ *Shortest path across two
domains.*
**Q76.** Which entry-level courses open the most downstream options? ✅
*Descendant count.*
**Q77.** Is this programme reachable from this school's course offering at all? ✅
*Reachability.*
**Q78.** What is the minimum set of courses covering the most pathways? ✅ *Set
cover over paths.*
**Q79.** Which prerequisite chains cross subject boundaries? ✅ *Path
enumeration with a property filter on the nodes.*
**Q80.** Nationally, what is the shortest path from any course to any
occupation? ❌ — needs prerequisites beyond one district (#19)

## Tier 5 — multi-domain

*Prerequisites × programmes × occupations × geography, in one query.*

**Q81.** Which districts have no school offering a pathway into the
fastest-growing occupations? ⚠️ — geography and programmes measured, growth not
**Q82.** Are high-earning occupations reachable from programmes offered in
low-income districts? ⚠️ — the equity question; earnings unmeasured
**Q83.** For this student's district, which occupations are reachable and which
are structurally out of reach? ✅ — district-scoped
**Q84.** Which programmes have the widest gap between who enrols and who
completes? ✅ — IPEDS reports completions by demographic
**Q85.** Which occupations pay above median but need only a certificate? ⚠️
**Q86.** Is this programme oversupplied — more graduates than the occupation
absorbs? ⚠️ — completions measured, employment not
**Q87.** Which regions have programmes with no local employer demand? ❌
**Q88.** Compare two districts: which offers more reachable occupations? ❌ —
one district measured (#19)
**Q89.** Which courses in this district lead to occupations that are shrinking? ⚠️
**Q90.** Where is the largest gap between courses offered and occupations
reachable? ✅
**Q91.** Which institution offers the most efficient route to this occupation? ⚠️
**Q92.** For every occupation, what is the cheapest programme that reaches it? ⚠️
**Q93.** Which pathways cross from secondary into post-secondary? ❌ — #42, the
dual-enrolment join, not researched
**Q94.** Which competencies are common to the most occupations? ❌ — competency
gap

## Tier 6 — whole-graph structure

*Not database questions at all.*

**Q95.** What does the prerequisite graph look like — how many components? ✅
**Q96.** Which subject areas are most internally connected? ✅
**Q97.** Which occupations are hubs in the crosswalk? ✅ *Degree centrality.*
**Q98.** Are there communities of programmes that share occupations? ✅
*Community detection.*
**Q99.** Which nodes are most central to the whole graph? ✅
**Q100.** Where are the structural holes — occupations reachable by only one
route nationally? ✅
**Q101.** How does the graph's shape differ between CTE and academic subjects? ✅
**Q102.** If we added one course to this district, which would increase
reachability most? ✅ *Counterfactual over the graph.*

---

## The competency gap

Three questions above — Q41, Q59 and Q94 — are blocked on the same thing, and it
is worth naming because no source we have measured fills it.

Every awarding body and every learning platform defines its own levels, and
**none publishes what a level means in competency terms**. A pass mark of 30%
advances a student in one system and not in another. A grade is a label whose
meaning varies by who issued it, and there is no published crosswalk between
them.

That is the same shape as evidence grading in medicine — each body grades on its
own scale, the scales do not align, and asserting an equivalence nobody
published is exactly the error this repo has avoided elsewhere.

The modelling answer, if we take it on, is the one already used for CIP-SOC and
for CTDL: a level belongs to its issuing body, equivalences are recorded as
*claims with a source* rather than as facts, and where no crosswalk exists the
graph says so instead of guessing. Raising it as its own research issue rather
than assuming a shape.

---

## Counts

| Tier | Questions | ✅ | ⚠️ | ❌ |
|---|---:|---:|---:|---:|
| 1 — lookup | 20 | 16 | 3 | 1 |
| 2 — one hop | 22 | 15 | 3 | 4 |
| 3 — change impact | 18 | 13 | 1 | 4 |
| 4 — graph algorithms | 20 | 19 | 0 | 1 |
| 5 — multi-domain | 14 | 3 | 7 | 4 |
| 6 — whole-graph | 8 | 8 | 0 | 0 |
| **Total** | **102** | **74** | **14** | **14** |

This table is checked by `tests/test_questions.py`, which counts the questions
and their status marks and fails if it disagrees. It exists because the first
version of the table was written by hand and got three rows wrong.

**Seventy-four answerable, and nineteen of the twenty tier-4 questions among
them.** That is the argument for building this as a graph rather than a
database, and three days ago it was not true — every tier-4 question was blocked
on prerequisites that #63 has since measured.

**Fourteen blocked**, in five clusters:

| Cluster | Questions | Why |
|---|---|---|
| Student-level records | Q20, Q38, Q44 | out of scope by choice (`scope.md` §1) |
| Employer demand | Q40, Q87 | no public source |
| Competency definitions | Q41, Q59, Q94 | the gap above |
| Needs a second district | Q80, Q88 | #19 |
| **Rules joining the two tiers** | Q39, Q57, Q58, Q93 | nobody publishes them as data |

That last cluster is the interesting one, and it was missed on the first pass.
Course-to-programme entry rules, state graduation requirements, accreditation
and dual enrolment are four different questions with one shape: **the rule that
connects secondary to post-secondary exists, and is published as prose for
humans rather than as data.** Same shape as the competency gap, and as the FDA
predicate device. It is worth its own research issue.

---

## What this tells us before designing anything

The schema has to serve the 74. In particular it has to make tier 4 cheap, which
means the prerequisite edge is the load-bearing structure and everything else
hangs off the CIP-SOC join.

[`sources/course-prerequisites.md`](sources/course-prerequisites.md) already
names the shape:
[`schema:coursePrerequisites`](https://schema.org/coursePrerequisites), which
accepts a course reference **or** free text — so the 240 resolvable edges and the
138 free-text requirements both have a home, and neither is forced into the
other. (The reuse decision that picks it over CTDL's stricter
`ceterms:prerequisite` is #33, landing separately in #61 — named rather than
linked, because that file is not in this branch's tree.)

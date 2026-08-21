# EdTech KG — schema

An education-to-career pathways graph, designed so the questions in
[`questions.md`](questions.md) are first-class traversals rather than
multi-table joins.

The executable ontology is [`schema/edtech_kg.cypher`](../schema/edtech_kg.cypher),
and every statement in it is executed by `tests/test_schema_engine.py`. This
page is the reasoning; that file is the contract.

**Two tiers.** Tier 1 is populated from a source measured by a probe in `etl/`.
Tier 2 is modelled but empty — the source is identified and not yet ingested, or
the data provably does not exist yet. Nothing is declared without a reason to
believe it can be filled.

---

## Node labels — tier 1

Tier 1 means **a probe in `etl/` has measured the source**. It does not mean the
rows are loaded — nothing is loaded yet, and the Measured column says what the
source holds, not what any graph contains.

| Label | Key | Meaning | Measured in the source |
|---|---|---|---|
| `Course` | `url` | One published course page in one district's catalogue | **795** courses (960 sitemap pages − 127 subject − 38 pathway; #74) |
| `Programme` | `cip_code` | A field of study, 6-digit CIP | 2,143 in the crosswalk |
| `Occupation` | `soc_code` | An occupation, SOC code | 868 in the crosswalk |
| `Institution` | `unitid` | A college or university, IPEDS | 6,256 |
| `School` | `ncessch` | A school, CCD | 102,268 |
| `District` | `leaid` | A school district, CCD | 19,714 |
| `Subject` | `url` | The catalogue's own grouping of courses | **127** subject pages (the same depth split; #74) |
| `Requirement` | `id` (sha1) | A stated condition that is **not** a course reference | 138 nodes, one per course that states one |
| `Completion` | `id` (sha1) | Graduates: institution × programme × award level × demographic × year | 9,026,310 |

**Where the district's three figures come from.** `etl/probe_pwcs.py` reports
960 — every page in the sitemap — and calls them all courses. The catalogue has
three levels: 127 subject indexes, 795 courses, 38 CTE pathway pages.

**The 38 are deliberately not modelled on this branch.** They have no node
label here: `Pathway` is tier 2, keyed on the Credential Registry's `ctid`,
which a district pathway page does not have. So the split closes as
127 + 795 + 38 = 960 with one third of it declared and one third named and left
alone, rather than a third of the subtraction going unaccounted for. Loading
them is edtech-kg#80, and the key that would let them in is edtech-kg#85.

So none of
the three rows above is a number the probe prints as such today; each falls out
of the depth split, and **edtech-kg#74** is where the probe is corrected to
report them separately. The table carries the corrected figures because a
reader skimming it should not take away a number this page goes on to refute.

`Completion` is 9,026,310 because that is what IPEDS publishes. Whether a
bounded slice or all of it is loaded is **edtech-kg#23** — a question about the
loader, not about the source.

## Node labels — tier 2, modelled and empty

| Label | Key | Why it is here, and why it is empty |
|---|---|---|
| `Credential` | `ctid` | 133,346 published, but under each publisher's own terms rather than CTDL's CC BY 4.0 (edtech-kg#56) |
| `Pathway` | `ctid` | CTDL's pathway vocabulary is rich; the Registry publishes **98** pathways against 47,861 Registry *course records* — a different population from `Course` above, which is district catalogue pages |
| `AwardingBody` | `id` | The competency gap, below |
| `Level` | `id` = `body\|code` | Same |
| `Competency` | `id` | Same |
| `EarningsRecord` | `id` | BLS, O\*NET and College Scorecard are *named but not counted* (edtech-kg#37, edtech-kg#21) |
| `Place` | `id` | "Near me" needs geography to be true first (edtech-kg#44) |

## Edge types

| Edge | From → To | Meaning |
|---|---|---|
| `REQUIRES` | Course → Course | **The prerequisite edge.** 240 measured, all resolving |
| `HAS_REQUIREMENT` | Course → Requirement | A prose condition — not a course reference |
| `PREPARES_FOR` | Programme → Occupation | The CIP-SOC crosswalk. 6,097 mappings |
| `OFFERS` | Institution → Programme | What a college teaches |
| `AT` / `IN` | Completion → Institution / Programme | Who graduated, where, in what |
| `TEACHES` | School → Course | Which school offers a course |
| `IN_DISTRICT` | School → District | |
| `IN_SUBJECT` | Course → Subject | |
| `ISSUED_BY` | Level → AwardingBody | Tier 2 — a level belongs to its issuer |
| `EQUIVALENT_TO` | Level → Level | Tier 2 — **a claim with a source**, not a fact. Directed, not symmetric — traverse both ways |
| `DEVELOPS` / `EXPECTS` | Course / Level → Competency | Tier 2 |
| `FOR_OCCUPATION` / `FOR_PROGRAMME` | EarningsRecord → … | Tier 2 |
| `LOCATED_IN` | Institution / District → Place | Tier 2 |

---

## Why these shapes

**A course is keyed on its absolute URL, never its name.** This is the most
important decision here and it is measured, not assumed. The district publishes
prerequisites as *links*, so 240 of 240 resolve by URL
([`sources/course-prerequisites.md`](sources/course-prerequisites.md)). Names do
not resolve — and Texas and New York publish entirely different course
vocabularies ([`sources/state-course-directories.md`](sources/state-course-directories.md)),
so a name key would collide the moment a second district arrives. Identical
argument to `product_code` in `regulatory-affairs-kg`: the join hub is the
publisher's identifier, never the display label.

**The full URL, not the path.** `probe_pwcs` resolves prerequisites by
catalogue-relative path, which is right inside one catalogue and only inside
one — `/mathematics/algebra-1` is a path two districts can both publish. The
host is what separates them, so the key keeps it.

**Prerequisite chains are the reason this is a graph.** `REQUIRES` is what makes
nineteen of the twenty tier-4 questions answerable — blast radius, shortest
path, reachability, cycle detection. Direction is *course → what it requires*,
so "what does skipping this close off" is an inbound traversal and "what do I
need first" is outbound. Before `etl/probe_pwcs.py` measured this catalogue,
every one of those questions was blocked for want of a source.

**A prose condition is a node, not an edge.** 138 course pages say things like
*"Teacher recommendation"* — and that is 138 `Requirement` nodes, because the
key is `sha1("<course URL>|<normalised text>")`, so the relationship is one to
one by construction. The 138 conditions are only **62 distinct texts**: the same
wording on two courses is deliberately two nodes, since a condition belongs to
the course that states it. The adopted term `schema:coursePrerequisites` permits
a Course **or** free Text, so both are legitimate — but a Text is not
traversable, and asserting an edge to a course nobody named would invent a link.
Keeping `Requirement` addressable means an unresolved condition survives as data
instead of being thrown away. Same shape as `PredicateClaim` in
`regulatory-affairs-kg`: model the unresolved citation, so a truncated chain
does not look complete.

**CIP-SOC is the only exact join between education and work**, and it is
government-published. It plays the role `regulation_number` plays in the
regulatory graph — the one join that is an identifier match rather than a name
match. Its edition sits on the edge, because the crosswalk revises and Q43 asks
what moves when it does.

**Completions are a node, not edge properties.** 9,026,310 rows of institution ×
programme × award level × demographic have to MERGE on re-load, and an edge
property cannot be keyed.

## The competency gap

Three questions — Q41, Q59 and Q94 — are blocked on one thing: **every awarding
body and every learning platform defines its own levels, and none publishes what a level means in
competency terms.** A pass mark advances a student in one system and not in
another. No crosswalk exists.

The modelling answer is the one this repo has already used twice, not a new
invention:

- a `Level` **belongs to** its issuing body — there is no free-floating "grade 8"
- an equivalence between two bodies' levels is a **claim carrying who asserted
  it**, so a reader can disagree with it
- where no crosswalk exists, the graph says nothing rather than inferring one
  from names that happen to match

This is why `Level` is keyed on `body|code` and why `EQUIVALENT_TO` carries
`asserted_by` and `source_url`. It is also why that edge is **directed and not
symmetric**: body A publishing *"our level 4 equals their level 3"* is a
different fact from body B publishing the converse, and only one may exist. A
query asking what is equivalent to a level must traverse both directions, and a
loader must not helpfully write the reverse — that would assert something nobody
published. It is the same refusal as declining to assert
`Submission → MarketedDevice` in the regulatory graph, where the FDA publishes
no such link.

The shape is general: it is the same problem as grading evidence in medicine,
where each body grades on its own scale and the scales do not align.

---

## What this schema does not claim

Written down before anyone finds it.

**Before the list: the MERGE rule is not enforced by anything.** The schema
says a loader must MERGE on the key, because 1.1.0 does not reject a duplicate
CREATE — measured directly, not assumed. `etl/loader.py` is still the repo
template, so for any loader but this district's the rule is prose.
**edtech-kg#7** is the national-spine loader, where it stops being a comment.
That is a statement about the loaders, not about what this schema claims, which
is why it sits above the list rather than inside it as an item "0".

1. **No student.** Individual records are permanently out of scope
   ([`scope.md`](scope.md) §1). Nothing here can answer "where is this child".
2. **No national prerequisite graph.** `REQUIRES` is populated for **one
   district**, 795 courses drawn from a 960-page sitemap. Statewide directories publish none at all, so
   this is a property of one publisher's catalogue software, not of US
   education data. Whether a second district resolves as cleanly is edtech-kg#19.
3. **No Course → Programme edge.** No public source links a district course to
   a college programme's entry requirements. Q39 is marked blocked for exactly
   this reason.
4. **No inferred competency equivalence.** See above.
5. **Completions are counts, not people.** A published aggregate cannot be
   traversed back to anyone.
6. **`PREPARES_FOR` is a published claim, not causation.** The crosswalk says a
   programme prepares for an occupation. It does not say graduates get those
   jobs, and nothing here supports that reading.

## Verified against the engine

Every statement in `schema/edtech_kg.cypher` executes clean on a **fresh
Samyama-Graph 1.1.0** instance — `tests/test_schema_engine.py`, with
`SAMYAMA_REQUIRE_ENGINE=1` so an unreachable engine fails rather than skips.

The tier-4 shapes were run, not assumed — **and now they are run by a test**,
against a fixture ladder four courses deep with one branch that leaves its
subject, so "across a subject boundary" is a property of the fixture rather
than a hopeful reading of one:

| Question | Form | Result |
|---|---|---|
| Q61 blast radius | `(x)<-[:REQUIRES*1..10]-(closed)` | ✅ reached depth 2 across a subject boundary |
| Q65 what must I take first | `(t)-[:REQUIRES*1..10]->(need)` | ✅ full ancestor set |
| Q62 shortest route | `shortestPath((a)-[:REQUIRES*1..10]->(b))` | ✅ |
| Q66 deepest chain | `max(length(p))` | ✅ found without being given the depth |

`tests/test_schema_engine.py`, under **the tier-4 shapes, actually run**. They
need `SAMYAMA_TEST_URL` pointed at a fresh instance — they write and delete,
unlike the constraint test above, which only issues DDL. A further test asserts
that every question number in this table has a test, so the two cannot drift.

Until this round the four ✅ above were the one set of claims on this page that
nothing executed, on a page otherwise careful to mark what is observed rather
than tested. Writing the tests immediately found something the ticks had been
asserting incorrectly:

> **`shortestPath` requires a variable on both endpoints.** Written with
> anonymous nodes — `shortestPath((:Course {name:'A'})-[…]->(:Course {…}))` —
> 1.1.0 answers `Planning error: shortestPath target must have a variable`. Bind
> them first and it runs. A constraint on how the query is written, not on what
> the engine can answer, and the form in the table above is now the form that
> was executed.

**One engine limitation found while doing it**, raised as
[samyama-graph#21](https://git.samyama.ai/Samyama.ai/samyama-graph/issues/21)
rather than worked around silently. A **pattern used as an expression inside
`WHERE`** does not parse in 1.1.0:

| Form | Parses in 1.1.0 |
|---|---|
| `WHERE (c)-[:REQUIRES]->()` | ✗ parse error |
| `WHERE NOT (c)-[:REQUIRES]->()` | ✗ parse error |
| `WHERE size((c)-[:REQUIRES]->()) = 0` | ✗ parse error |
| `WHERE exists((c)-[:REQUIRES]->())` | ✗ parse error |
| `WHERE NOT EXISTS { MATCH (c)-[:REQUIRES]->() }` | ✅ |
| `OPTIONAL MATCH … WITH c, r WHERE r IS NULL` | ✅ |

The capability is there; the inline pattern-expression syntax is not. So Q34 —
*"which courses have no prerequisite, the entry points"* — is answerable, in
this form:

```cypher
MATCH (c:Course)
WHERE NOT EXISTS { MATCH (c)-[:REQUIRES]->() }
RETURN c.title
```

That table is **observed, not executed** — it is the one substantive claim on
this page that no test runs, and it goes stale silently the day
samyama-graph#21 lands and four of its rows become wrong. **edtech-kg#72** is to run the
six forms against a live engine and assert each verdict.

Loaders, demo queries and anything generating Cypher must use `EXISTS { }`.
That last point is the one worth remembering: text-to-Cypher will emit
`WHERE NOT (a)-[:R]->(b)`, because that is what its training data contains, and
it will fail at runtime rather than at generation.

## Reuse

Every external term adopted, aligned or minted is recorded with its verdict and
a link to its definition in [`ontology-reuse.md`](ontology-reuse.md).

**Nothing is minted** — every shape the answerable questions need already had a
published name.

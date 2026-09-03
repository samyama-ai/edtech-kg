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
| `Course` | `url` | One published course page in one district's catalogue | **791** courses (960 sitemap pages − 127 subject − 42 pathway; #74) |
| `Programme` | `cip_code` | A field of study, 6-digit CIP | 2,143 in the crosswalk, of which 1,949 map to an occupation |
| `Occupation` | `soc_code` | An occupation, SOC code | 867 in the crosswalk — 868 counted `99-9999 NO MATCH`, which is a sentinel, not an occupation (#70) |
| `Institution` | `unitid` | A college or university, IPEDS | 6,256 |
| `School` | `ncessch` | A school, CCD | 102,268 |
| `District` | `leaid` | A school district, CCD | 19,714 |
| `Subject` | `url` | The catalogue's own grouping of courses | **127** subject pages (the same depth split; #74) |
| `Requirement` | `id` (sha1) | A stated condition that is **not** a course reference | **138 stated conditions**. The key is `sha1("<page URL>\|<normalised text>")`, so a page stating two conditions is two nodes — 138 is one each today, which is a fact about the catalogue and not about the key. All 138 sit on course pages; `HAS_REQUIREMENT` accepts a pathway too, and none states one |
| `Pathway` | `url` | A published route through courses — a CTE career pathway or specialty program | **42** — 36 under `/career-and-technical-education-cte/` and 6 elsewhere: three specialty programs, the Governor's School, JROTC, and Virtual Prince William. Counted from the loaded urls, not from the section names |
| `Completion` | `id` (sha1) | One institution × programme × award level × **demographic** × year. Not a graduate — a demographic cell | **9,026,310** rows, which is 300,877 IPEDS rows × 30 demographic columns. The awards they describe are **10,620,172** (#43) |

**`Pathway` moved here from tier 2**, and its key changed from `ctid` to `url`.
It was modelled on the Credential Registry, which publishes 98 pathways against
47,861 Registry *course records* — a different population from `Course` above,
which is district catalogue pages — so it was declared and left empty. But a
district publishes pathways too, as pages: 42 load from PWCS. A district
pathway has no `ctid`, so keeping that key would have given all 42 nodes a null
value for the declared key — which 1.1.0 accepts in silence, because a
constraint here declares the key and does not enforce it.

**edtech-kg#85 then asked what the second publisher needs, and it is measured**
rather than argued — `python -m etl.probe_pathway_identity` reads all 98
published Registry pathways (`docs/sources/pathway-identity.md`):

| candidate | present | distinct | lost to a merge |
|---|---|---|---|
| `ceterms:ctid` | 98 / 98 | 98 | 0 |
| `ceterms:subjectWebpage` | 78 / 98 | 71 | 7 |

Twenty Registry pathways publish no webpage, so `url` repeats the null-key
failure in the other direction — and seven more would be *silently merged*,
because four department landing pages are each published as several distinct
programmes. A key that is absent is visible; a key that merges is not.

The verdict is a composite carrying the identifier space,
`Pathway.id = "<space>|<identifier>"` with space `url` or `ctid` — the shape
`AwardingBody`, `Level` and `Competency` already use. It is **parsed from the
left**, the opposite of `Level`, because here the leading component is the one
free of `|`. The constraint still names `url` and moves to `id` when a loader
first writes one; the Registry's own pathways remain unloaded, blocked on
**#56**.

**Where the district's figures come from.** `etl/probe_pwcs.py` reads the
sitemap's 960 pages and classifies each one before counting it. The catalogue
has three kinds: 127 subject indexes, 791 courses, 42 pathway pages, and all
three are declared above, so the split closes as 127 + 791 + 42 = 960 with
nothing left over. Rates are quoted against the 791, not the 960.

**The kinds are not read off the URL alone.** Depth is the catalogue's own
structure and it holds for 956 of the 960 pages. Four publish a pathway's
course table at COURSE depth, and classifying those by depth cost 172 published
rows — the loader read them as courses and never opened their tables
(edtech-kg#87). A page rendering that field is a pathway whatever its URL says;
the district's markup is the better evidence, and it is the evidence the rows
come from. Depth still decides everything else, because a subject index and a
course carry no field that tells them apart.

None of the district rows above is a number the probe prints as such today, and
**edtech-kg#74** is where the probe is corrected to report them separately. The
table carries the corrected figures because a reader skimming it should not
take away a number this page goes on to refute.

`Completion` is 9,026,310 because that is what **the Urban wrapper**
publishes. IPEDS publishes 300,877 rows for the same collection and year and
carries the demographics as **columns**; the wrapper unpivots them, and
300,877 × 30 = 9,026,310 exactly. Measured in
[`sources/federal-direct.md`](sources/federal-direct.md).

**Neither figure is a number of graduates.** The same file reports
**10,620,172** awards for first majors — more than the row count it is easy to
mistake for awards. Quote the award count when describing this graph to
anyone; quote the row count only when describing the node.

Whether a bounded slice or all of it is loaded is **edtech-kg#23** — a
question about the loader, not about the source.

## Node labels — tier 2, modelled and empty

| Label | Key | Why it is here, and why it is empty |
|---|---|---|
| `Credential` | `ctid` | 133,346 published, but under each publisher's own terms rather than CTDL's CC BY 4.0 (edtech-kg#56) |
| `AwardingBody` | `id` | The competency gap, below |
| `Level` | `id` = `body\|code` | Same |
| `Competency` | `id` | Same |
| `EarningsRecord` | `id` | BLS, O\*NET and College Scorecard are *named but not counted* (edtech-kg#37, edtech-kg#21) |
| `Place` | `id` | "Near me" needs geography to be true first (edtech-kg#44) |

## Edge types

| Edge | From → To | Meaning |
|---|---|---|
| `REQUIRES` | Course → Course | **The prerequisite edge.** 240 measured, all resolving |
| `HAS_REQUIREMENT` | Course / Pathway → Requirement | A prose condition — not a course reference |
| `INCLUDES` | Pathway → Course | What a published pathway is made of. The pathways publish **390 rows**: 374 resolve to a loaded course and **16 resolve to none** — the 16 are additional to the 374, not drawn from it. Of the 374, **58 repeat a pathway-course pair already listed**, each because that course appears in a second named section of the same pathway, and 1.1.0 holds one edge per pair (#77), so the section names are joined onto the one edge and `rows` records how many folded in. **374 − 58 = 316 edges.** On the 16: measured, every one names a Drupal node id the catalogue publishes no page for. The check is "not a loaded course" rather than "not published", so a row naming a page that IS published but is a Subject or a Pathway would land here too — none does today. Carries the district's section name and credit value |
| `PREPARES_FOR` | Programme → Occupation | The CIP-SOC crosswalk. 5,903 mappings, from 6,097 rows — 194 carry the `99-9999 NO MATCH` sentinel and are a statement that there is no mapping (#70) |
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
fifteen of the twenty tier-4 questions answerable — blast radius, shortest
path, reachability, ancestor and descendant sets. Two of those four are
answered with a caveat rather than outright — shortest path is Q62 and
reachability is Q77, both ⚠️ — and they are counted here because the key calls
⚠️ answerable. NOT cycle detection: that is
Q71, marked ❌ because this engine does not bind a repeated variable across a
variable-length pattern, so `(c)-[:REQUIRES*1..1]->(c)` matches every edge
rather than the ones returning to `c`. Direction is *course → what it requires*,
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
body and every learning platform defines its own levels, and none publishes
what a level means in competency terms.** A pass mark advances a student in one
system and not in another. No crosswalk exists.

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

**Before the list: the MERGE rule is enforced for one loader, not by the
engine.** `etl/load_pwcs.py` MERGEs on the key throughout, and a test compares
the property it keys each label on against the property this file declares — so
for that loader the rule is checked rather than hoped for. It is still not a
guarantee: 1.1.0 does not reject a duplicate CREATE, measured directly rather
than assumed, so any future loader that forgets is stopped by nothing but that
test. **edtech-kg#7**, the national-spine loader, is where the rule gets tested
a second time.

That is a statement about the loaders, not about what this schema claims, which
is why it sits above the list rather than inside it as an item "0".


1. **No student.** Individual records are permanently out of scope
   ([`scope.md`](scope.md) §1). Nothing here can answer "where is this child".
2. **No national prerequisite graph.** `REQUIRES` is populated for **one
   district**, 791 courses drawn from a 960-page sitemap. Statewide directories
   publish none at all, so this is a property of one publisher's catalogue
   software, not of US education data. Whether a second district resolves as
   cleanly is edtech-kg#19.
3. **No Course → Programme edge.** No public source links a district course to
   a college programme's entry requirements. Q39 is marked blocked for exactly
   this reason.
4. **No inferred competency equivalence.** See above.
5. **Completions are counts, not people.** A published aggregate cannot be
   traversed back to anyone.
6. **`PREPARES_FOR` is a published claim, not causation.** The crosswalk says a
   programme prepares for an occupation. It does not say graduates get those
   jobs, and nothing here supports that reading.

## A page is classified by what it publishes, not only by its URL

This was one of the holes listed above until edtech-kg#87 closed it, and it has
its own heading now because it is no longer a limit this schema carries. Kept
rather than deleted: how a page gets its label is a property of the schema, the
next source will raise the same question, and a defect that disappears once
fixed teaches nobody what to look for.

Four pages render a pathway's course table at course depth. Three sit under
`/specialty-programs/` — the Center for Biotechnology and Engineering, the
Information Technology Center, and International Baccalaureate — and the fourth
is Virtual Prince William, under its own path. Read by depth alone they loaded
as `Course`, their tables were never opened, and 172 published rows never became
edges. Nothing failed: the loader and the engine agreed about a set that was
already short, which is why it took a reviewer asking what the classifier
assumed.

Fixed in edtech-kg#87. The markup now wins over the depth, and the loader
prints every page where the two disagree — so the next one is visible
rather than absorbed.

`INCLUDES` moved from 185 edges to 316, and the +131 is checkable rather
than asserted. The four pages publish **182 rows**: 172 resolve to a loaded
course and 10 resolve to none. Of those 172, **41 repeat a pair already
listed on the same pathway** and fold onto one edge (#77), leaving
**172 − 41 = 131 new edges**, so **185 + 131 = 316**. The 10 unresolvable
rows are part of the 16 the `INCLUDES` row above accounts for; the other 6
were already there.

The node total is unchanged at 1,098: the four pages did not appear or
disappear, they changed label. `Requirement` is unchanged too — all 138
requirement blocks sit on course pages, and none of the four reclassified
pages carries one, measured after the change rather than assumed.

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

**This table is executed, not observed.** `tests/test_schema_parse_table.py`
reads these six rows out of this page and runs each one against a live engine,
so the page and the engine cannot drift apart quietly. The rows are read from
here rather than restated in the test: editing this table changes what runs.

Re-executed against **1.7.0** on 2026-09-01 and all six verdicts are unchanged.
The heading states 1.1.0 because that is the version this repo pins and the one
the figures elsewhere on this page were measured on — see #24.

The verdicts are expected to change: [samyama-graph#21](https://git.samyama.ai/Samyama.ai/samyama-graph/issues/21)
asks for pattern predicates in `WHERE` to parse, and on the day that lands four
of these rows become wrong. The test fails that day and says which direction
the engine moved, rather than leaving this page recommending a workaround for a
limitation that no longer exists.

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

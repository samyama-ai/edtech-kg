# Sources and standards register

Every source and standard this repo has looked at, what it contributes, and
where its licence stands. One row each, and **every row has a status** — that
is the point of the file.

Without this the folder becomes twenty-odd pages nobody reads before adding a
twenty-first source, and the licence questions in [`../scope.md`](../scope.md)
get rediscovered rather than answered. Closes #46.

**Three rules keep it honest:**

1. A row may not read **cleared** without a **named licence and the date it was
   checked**. #13 and #14 exist because that was not done up front.
2. A **rejected** source stays in the table, with its reason. The register's
   value is as much in what was ruled out as in what was taken in — a later
   reader who does not know Ed-Fi was investigated will investigate it again.
3. Every figure cited on a linked page is printed by the script named on it.
   Nothing in `docs/sources/` is hand-counted, and this register quotes those
   pages rather than restating their numbers.

**Status** is one of `unexamined` · `examined` · `cleared` · `rejected`.
*Examined* means the work was done and the answer was not yes — an open licence
question, or a source that answers a different question than the one asked.

---

## Loaded, or ready to load

| source / standard | publisher | what it contributes | licence position | status | issue |
|---|---|---|---|---|---|
| IPEDS — completions, directory | NCES | institutions and awards | US-government public domain | **cleared** | — |
| [IPEDS — enrolment](enrolment.md) | NCES | **the half of #8's question 4 that does not exist** — students counted by institution, class level, race, sex and residence, never by programme | US-government public domain, same footing as completions | examined | edtech-kg#204 |
| CCD — schools, districts | NCES | the school and district side | US-government public domain | **cleared** | — |
| [CIP-SOC crosswalk](cip-soc-crosswalk.md) | NCES + BLS | **the join the graph rests on** — programme to occupation | US-government public domain | **cleared** | edtech-kg#70 |
| [O\*NET crosswalk workbooks](licences.md) | US Dept of Labor | occupation detail behind the crosswalk | CC BY 4.0 by the crosswalks page's own notice, checked **2026-08-31** — *not* the Database licence, which excludes that page | **cleared** | edtech-kg#14 |
| [College Scorecard](college-scorecard.md) | US Dept of Education | programme-level earnings | US-government public domain | **cleared** | edtech-kg#21 |
| [Urban Institute Education Data API](education-data.md) | Urban Institute | **the route every measured count arrives through** — IPEDS, CCD and Scorecard, republished. Licence quoted in [licences.md](licences.md) | ODC-By v1.0, checked **2026-08-31**; reuse permitted, citation requested | **cleared** | edtech-kg#13 |
| [PWCS course catalogue](course-prerequisites.md) | Prince William County Public Schools | **the only district loaded** — and the only published prerequisites found | A public catalogue, but reuse permission is a human decision rather than a published licence. **Not settled.** | examined | edtech-kg#4 |
| [Four more Clean Catalog districts](second-district.md) | Arlington, Clover Park, Kenosha, Central Islip | **whether prerequisites generalise** — measured, and they do not: districts state them, only PWCS states them traversably | Same footing as PWCS above — public catalogues, robots.txt checked **2026-09-08** and confined to Drupal internals, but reuse permission is a human decision rather than a published licence. **Not settled.** The record holds counts and short prose excerpts — up to 120 characters each — kept as evidence for a measurement, not as a republication of the catalogue. | examined | edtech-kg#19 |
| [ECS graduation requirements](graduation-requirements.md) | Education Commission of the States | **the other half of a course plan** — credits by subject, all fifty states, normalised. Measured and not taken | `reports.ecs.org/robots.txt` is **`Disallow: /`**, checked **2026-09-09**, and the public landing page answers 403. **Refused.** Nothing was fetched. | rejected | edtech-kg#41 |
| [Who already sells this](who-sells-this.md) | GT.school, Ellucian, PowerSchool/Naviance, Stellic, Civitas Learning | **what the field publishes** — term counts over one public page each; only one of six mentions degree audit, and the incumbent's product pages 404 | Public marketing pages, robots.txt checked **2026-09-10** before any request. **Coursicle NOT FETCHED**: its robots.txt disallows a list of AI user-agents, ours is not on it, and we stopped anyway. Counts and no excerpts — nothing is republished. | examined | edtech-kg#47 |

## Vocabularies and standards

| source / standard | publisher | what it contributes | licence position | status | issue |
|---|---|---|---|---|---|
| [CTDL — the vocabulary](ctdl.md) | Credential Engine | `Pathway`, `CourseComponent`, `ComponentCondition`, and a direct prerequisite property | CC BY 4.0, quoted verbatim on the page | **cleared** | edtech-kg#28 |
| [CEDS](ceds.md) | CEDS Standards | the federal vocabulary this sector already speaks; 1,369 classes | **Apache-2.0**, measured **2026-08-28** | **cleared** | edtech-kg#29 |
| [Ed-Fi DS 6.0](ed-fi-and-case.md) | Ed-Fi Alliance | the K-12 data standard | **Apache-2.0**, measured **2026-08-28** | **cleared** | edtech-kg#31 |
| [CASE v1p0](ed-fi-and-case.md) | 1EdTech | competency and standards framework | Use is **governed by a 1EdTech licence agreement** — not Apache-2.0 and not Creative Commons. A licence agreement is not a public grant. | examined | edtech-kg#32 |
| [SCED](sced.md) | NCES / National Forum on Education Statistics | the national course taxonomy — a course *identifier*, and it defines a sequence element | US-government public domain | **cleared** | edtech-kg#34 |
| [Career Clusters](code-sets.md) | Advance CTE | the language US high schools actually speak | **© 2023 Advance CTE. All rights reserved.** No machine-readable release; branded PDFs only. Read **2026-08-27**. | **rejected** | edtech-kg#35 |

## Occupation and outcome sources

| source / standard | publisher | what it contributes | licence position | status | issue |
|---|---|---|---|---|---|
| [BLS occupational projections](bls-occupation.md) | Bureau of Labor Statistics | pay, outlook and entry education for 832 occupations — reaching 96.3% of those a programme can reach | US-government public domain | **cleared** | edtech-kg#37 |
| [Registered Apprenticeship](apprenticeship.md) | US Dept of Labor | the route to an occupation that is not a degree | CC BY 4.0; the RAPIDS occupation list is a US federal government work | **cleared** | edtech-kg#39 |
| [CareerOneStop](careeronestop.md) | US Dept of Labor | licensure by state — the question it was raised for turned out not to exist | **The licence was never reached.** The page records why the question was withdrawn before the terms were read. | examined | edtech-kg#38 |

## Ruled out, and why

| source / standard | publisher | what was asked | finding | status | issue |
|---|---|---|---|---|---|
| [Credential Registry — the **data**](registry-data-licence.md) | many publishers, operated by Credential Engine | can the published records be loaded? | **Not cleared — do not load.** Terms grant internal use only and route redistribution through a signed Developer Agreement, checked **2026-08-31**. The CC BY 4.0 finding is about CTDL the *vocabulary*, not this. | **rejected** | edtech-kg#56 |
| [Credential Registry — prerequisites](credential-registry.md) | as above | is `ceterms:prerequisite` actually populated? | **It is not.** Prerequisites are published as free text inside a `ConditionProfile` rather than as the resolvable edge — the relationship exists and the target must be guessed from a string. | **rejected** | edtech-kg#53 |
| [Statewide course directories](state-course-directories.md) | five state education departments | would one state clear replace hundreds of district scrapes? | **No.** Directories exist and two of five are cleanly machine-readable, but **neither carries prerequisites**. `scope.md` §3 stands. | **rejected** | edtech-kg#40 |
| [State department access](state-access.md) | five state education departments | what does automating a state department cost? | **Four of five refuse automation.** Measured **2026-08-28** — a homepage and a `robots.txt` each; Virginia refuses both with 403. | examined | edtech-kg#50 |
| [Reading IPEDS / CCD / Scorecard direct](federal-direct.md) | NCES, US Dept of Education | can the federal collections be read at source, so one third party is not a single point of failure? | Read **2026-09-01**. The reason it was raised has already gone — see the page. | examined | edtech-kg#43 |

## Identity decisions that came out of this work

Not sources, so not rows in the register — but settled here, and easy to
rediscover otherwise.

- **Which number names a college** — IPEDS `UNITID`. `OPEID` is a crosswalk key,
  not an identity: keyed on it, three campuses of one system collapse into one
  node. [institution-identity.md](institution-identity.md), edtech-kg#45.
- **Which property keys a `Pathway`** — one label keyed on one property cannot
  hold both publishers. Measured across all 98 published pathways.
  [pathway-identity.md](pathway-identity.md), edtech-kg#85.
- **Surviving a code-set revision** — the crosswalk carries hierarchy for 10 of
  its 49 families and not the other 39, which is a mixture rather than an
  absence, and worse than either. [code-sets.md](code-sets.md), edtech-kg#36.

---

## What is not here

**No row is `unexamined`.** Every source and standard in `docs/sources/` has
been measured and has a verdict. A source someone names but nobody has looked at
does not belong in this table until it has a page — add the page, then the row.

The counts on the linked pages are printed by the probes in `etl/`, one per
source, and the tests hold the pages to the JSON those probes write. If a figure
quoted here disagrees with its page, the page is right.

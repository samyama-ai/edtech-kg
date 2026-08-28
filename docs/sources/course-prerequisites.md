# Course prerequisites — measured 2026-08-19

This is the fork in the road for the whole build. `docs/questions.md` puts it
plainly: everything in section A depends on knowing which course requires which,
and **"answering that question comes before the ontology"**.

**Answer: yes.** One real district publishes prerequisites as machine-readable
links between its own course pages, and **every one of them resolves**.

Every figure below is printed by `python -m etl.probe_pwcs`. Nothing is
hand-counted.

---

## What was measured

Prince William County Schools publishes `catalog.pwcs.edu` on Clean Catalog, a
Drupal product. Its sitemap names every course page, so the population is known
exactly rather than crawled blind. All of it was read — not a sample.

| | Courses | |
|---|---:|---|
| Pages in the sitemap | **960** | the whole catalogue: 127 subject indexes, **791 courses**, 42 CTE pathways |
| Course pages | **791** | the denominator every rate below is quoted against |
| Linking at least one prerequisite | **229** | **29.0%** of 791 courses |
| …where **every** link resolves | **229** | **100% of those** |
| …where some links resolve | 0 | |
| …where no link resolves | 0 | |
| **Resolvable prerequisite edges** | **240** | loadable today |
| Dangling links | **0** | |
| Prerequisite field rendered but unreadable | **0** | the parser is not silently missing any |
| Pages that could not be read | **0** | excluded, never counted as having no prerequisite |

### What the earlier 960 counted

An earlier version of this page quoted **229 of 960 — 24%**. That denominator
was every page in the sitemap, and the sitemap is not a list of courses. It
carries three levels, visible in the path:

| depth | example | what it is | count |
|---|---:|---|---:|
| 1 | `/band` | subject index | 127 |
| 2 | `/band/concert-band` | course | 795 |
| 3 | `/career-and-technical-education-cte/career-pathways/finance-accounting` | CTE pathway | 38 |

Those are DEPTHS. The classified counts are **127 / 791 / 42**, because four
pages publish a pathway's course table at course depth and their own markup
wins over their URL (#87). 791 is the figure quoted above; 795 is what depth
alone would say, and edtech-kg#74 asked for 795 before that override existed.

**The 240 edges are unaffected**, and that is now asserted rather than
assumed: no page classified as anything but a course states a prerequisite,
and every prerequisite link lands on a page classified as a course
(`tests/test_pwcs_classify.py`, against the cached catalogue). Only the
denominator moved — from 23.9% to **29.0%**.
| Carrying free-text requirements as well | 138 | not edges — see below |

## Why it resolves, and the FDA comparison

The prerequisite is not prose. The catalogue publishes it as a Drupal *entity
reference* — a link to another course page on the same site:

```html
<div class="field--name-field-prerequisite-courses">
  <a href="/agriculture-food-and-natural-resources/landscaping-1">Landscaping 1</a>
```

So resolution is by **URL against the sitemap**, not by matching names. A link
either lands on a published course page or provably does not. Both ends of the
edge come from the same publisher, which is the whole reason the rate is 100%.

Set against the two other prerequisite-shaped sources this repo has measured:

| | FDA predicate device | Credential Registry | **PWCS** |
|---|---|---|---|
| Published? | yes | yes | yes |
| Expressed as | free text in a PDF | free text in a JSON field | **a link** |
| Resolves to a real record | partially | **0 of 150** (#53) | **240 of 240** |
| Why | pre-1976 devices have no record | "PSYC101" has no catalogue attached | the catalogue is closed over itself |

That last row is the point. `ceterms:prerequisite` exists in CTDL and nobody
uses it (#28, #53); publishers write strings instead. PWCS did not need the
standard — its CMS made the link a first-class field, so the edge exists whether
or not anyone was thinking about graphs.

## What is *not* an edge

**138 courses carry a separate free-text field**, labelled *Requirements* on the
page — *"Enrolled in Agriculture Specialty Program"*, *"Teacher recommendation"*.
These are real conditions and they are **not course references**. They are
counted and reported separately, never folded into the 240, because loading them
as edges would claim a link the source does not make.

Both shapes have a home without inventing one, because
[`schema:coursePrerequisites`](https://schema.org/coursePrerequisites) accepts a
`Course` **or** free `Text` — its own definition says *"may be completion of
another Course or a textual description like 'permission of instructor'"*.

(The reuse decision that picks that term over CTDL's stricter
`ceterms:prerequisite` is #33, landing separately in #61. It is named here
rather than linked, because that file is not in this branch's tree.)

## Three corrections this probe produced

An earlier draft of this page, written from an ad-hoc parse of 40 courses,
claimed **45% state a prerequisite and 89% of those resolve**. Writing the probe
corrected all three of its figures:

1. **45% → 29.0%.** The earlier parse flattened each page to text and matched
   `Prerequisite:\s*(...)`, which ran the value into the page footer — the
   school's street address became part of the course name — and counted
   *"Prerequisite: None"* as a stated prerequisite.
2. **89% → 100%.** Reading the links instead of the prose removes the guesswork
   entirely. Nothing dangles.
3. **40 courses → 791.** The whole catalogue, so the rate is the rate.

The direction of the finding survived; none of the numbers did.

## What this does and does not license

**It does mean the demo can be prerequisite chains.** 240 resolvable edges over
791 courses is a real graph, in the domain a student actually asks about, and it
is the graph-native story that `docs/questions.md` says section A needs.

**It does not mean this generalises.** One district, not the country. #40
established that statewide directories carry no prerequisites at all, so this
is a property of *this publisher's CMS*, not of US education data. Whether a
second district resolves as cleanly is #19, and it is still open.

**Chains are shallow at 240 edges.** How deep they actually run is not measured
here — the probe counts edges, not path length. That is worth knowing before the
demo leans on the word "chain".

---

**Method.** Every figure from:

```bash
python -m etl.probe_pwcs                # the full sweep, all 960 catalogue pages
python -m etl.probe_pwcs --json         # machine-readable, with timestamp
python -m etl.probe_pwcs --limit 50     # a quick run — the output says it is partial
```

Pages are cached under `data/pwcs/` (gitignored), so re-running the figures
costs a school district nothing. Live fetches are rate-limited.

The prerequisite is read from its own markup block rather than from flattened
page text, because flattening leaks the footer into the value. Navigation links
are excluded by construction — only the prerequisite field counts.

Resolution is strictly against the sitemap. The read pages are not folded into
the set of published paths, so the check is not partly self-referential, and an
off-site link is never counted even if its path happens to exist here — the
claim being made is 100% and it should be airtight.

A page that **renders the prerequisite field but yields no links** is counted and
reported separately, not read as a course without prerequisites. If the
catalogue's markup drifts, that number rises instead of the rate quietly
falling — which is the same class of error this page was written to correct. It
is currently zero, so the parse is verified rather than assumed.

The probe refuses rather than reporting a figure it cannot vouch for: a sitemap
with no `<loc>` entries, a sitemap with no course pages, or a sweep that parsed
no courses. A page that cannot be read after one retry is **reported as unread**
rather than dropped, because a page we could not read is not a course without a
prerequisite.

`tests/test_probe_pwcs.py` covers the parsing, the resolution and the refusals;
fourteen mutations were tried against it and all fourteen turn the suite red.

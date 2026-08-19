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
| Course pages in the sitemap | **960** | the whole catalogue |
| Linking at least one prerequisite | **229** | 24% |
| …where **every** link resolves | **229** | **100% of those** |
| …where some links resolve | 0 | |
| …where no link resolves | 0 | |
| **Resolvable prerequisite edges** | **240** | loadable today |
| Dangling links | **0** | |
| Prerequisite field rendered but unreadable | **0** | the parser is not silently missing any |
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

This matches the reuse decision in `docs/ontology-reuse.md`:
`schema:coursePrerequisites` accepts a `Course` **or** free `Text`, so both
shapes have a home without inventing one.

## Three corrections this probe produced

An earlier draft of this page, written from an ad-hoc parse of 40 courses,
claimed **45% state a prerequisite and 89% of those resolve**. Writing the probe
corrected all three of its figures:

1. **45% → 24%.** The earlier parse flattened each page to text and matched
   `Prerequisite:\s*(...)`, which ran the value into the page footer — the
   school's street address became part of the course name — and counted
   *"Prerequisite: None"* as a stated prerequisite.
2. **89% → 100%.** Reading the links instead of the prose removes the guesswork
   entirely. Nothing dangles.
3. **40 courses → 960.** The whole catalogue, so the rate is the rate.

The direction of the finding survived; none of the numbers did.

## What this does and does not license

**It does mean the demo can be prerequisite chains.** 240 resolvable edges over
960 courses is a real graph, in the domain a student actually asks about, and it
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
python -m etl.probe_pwcs                # the full sweep, all 960 pages
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

# Can we get course prerequisites? — measured, 2026-08-17

This decides the shape of the whole build. Every question in section A of
[`../questions.md`](../questions.md) — *"I want to be a nurse, what do I take
next semester?"* — depends on knowing which course requires which. Without it
the graph is programme → occupation → earnings, which is useful but not
graph-native. With it, prerequisite chains are the demo.

**Answer: yes, for at least one real district, published openly, in a form a
loader can read. Measured, not assumed.**

---

## 1. What does not exist

Checked first, because it is what everyone assumes is there:

| Source | Verdict |
|---|---|
| Federal open data (`data.ed.gov`, NCES EDGE) | Institutions, districts, completions. **No course-level data at all.** |
| Urban Institute Education Data API | Same — the source of our 9,026,310 IPEDS figure, and it stops above the course. |
| **Ed-Fi Data Standard** | A K-12 data *standard*, widely adopted, that models course data — **but it is how districts exchange data with their own vendors, not a public feed.** The data is structured somewhere; access needs a district relationship. |
| State course code directories (e.g. Florida CCD) | Publish course numbers, titles and descriptions statewide. Prerequisites appear inside prose descriptions if at all, and the delivery is PDF or a JavaScript app rather than a file. |
| OCCAPI | A real open course-catalogue API standard — European higher education, not US K-12. |

So there is **no national machine-readable source of course prerequisites**.
That much of the pessimism in Solutions issue #23 was right.

## 2. What does exist

Individual districts publish a *program of studies* — the catalogue a student
picks next year's courses from. Most are PDFs. **Some are websites.**

**Prince William County Public Schools, Virginia** publishes at
`catalog.pwcs.edu`, built on a product called Clean Catalog (Drupal). It has:

- **982 course pages** in its sitemap, organised by subject
- one HTML page per course
- an explicit **Prerequisites** field, naming other courses

There is no JSON API — `/jsonapi` returns 404 — so this is HTML parsing, not an
API call.

## 3. What the data actually contains

40 course pages sampled at random from the sitemap, fetched with a 0.4s delay
and an identifying user-agent.

| | Count | Share |
|---|---:|---:|
| Names a prerequisite course | **18** | 45% |
| Says "None" explicitly | 6 | 15% |
| Describes it in prose, not as a name | 5 | 12% |
| No prerequisite line at all | 11 | 28% |

**The number that matters is resolution.** A prerequisite is only an edge if the
name it gives points at a course that exists.

> **Of the 18 named prerequisites, 16 resolve to a course page — 89%.**

Both failures are the parser, not the data: one is a compound line covering two
languages at once, and the other is `"U.S. and Virginia History"` split at the
full stop. With better parsing the real rate is above 90%.

Examples of what an edge looks like:

```
Automotive Technology 2    -> Automotive Technology 1
English 10                 -> English 9
IGCSE Geometry             -> Algebra 1
Advanced Geometry          -> Advanced Algebra 1
Practical Nursing 3        -> Practical Nursing 1, Practical Nursing 2
Plumbing 2                 -> Plumbing 1
```

That is a chain, and chains of unknown depth are what a graph is for.

## 4. Why this is better than the FDA predicate case

The obvious worry is that this repeats the mistake in `regulatory-affairs-kg`,
where the predicate device is a free-text name inside a PDF and the resolution
rate is still unmeasured. It does not, and the difference is specific:

| | FDA predicate device | PWCS prerequisite |
|---|---|---|
| Where it lives | Inside a 510(k) Summary **PDF** | An HTML field on the course page |
| Vocabulary | Free text, no controlled list | The catalogue's **own** course names |
| Target may not exist | Yes — pre-1976 devices have no record | Rare; the catalogue is closed over itself |
| Resolution rate | **unmeasured** | **89% measured** |

The names resolve here precisely because both ends come from the same
catalogue. That is not luck; it is a property of the source.

## 5. What this costs us — stated now, not later

**One district, not the country.** PWCS is large — one of Virginia's biggest —
but a graph built on it describes *its* pathways. Any national claim would be
false. A second district has not been verified: the vendor says it serves other
districts, and the structure would likely repeat, but that is an assumption
until one is measured.

**28% of courses carry no prerequisite line.** Chains are partial by nature,
exactly as the FDA ones are. An unresolved or absent prerequisite must be
modelled explicitly rather than dropped — a truncated chain that looks complete
is worse than no chain.

**12% state the requirement in prose** — *"intended for students who have
previously completed…"*. Those need judgement, not parsing, and should be
recorded as unresolved rather than guessed at.

**It is scraping, not an API.** A site redesign breaks the loader. The parse
must be defensive and the extraction date recorded with every edge.

**Permission needs a human decision.** `robots.txt` disallows admin, search and
user paths; it does not disallow the course pages, and there is no crawl-delay
directive. That is a public catalogue a district publishes for families to
read. Even so, whether we ingest another organisation's site into a product is
a question for Sandeep, not for a loader. **Ask before building.**

## 6. What this means for the build

Prerequisite chains are viable. Section A of the questions document moves from
❌ to ⚠️ — answerable for one district, with the coverage stated in the answer.

Recommended order:

1. **Get permission cleared** before any bulk fetch. Everything below is
   pointless if the answer is no.
2. **The national spine first** — CIP-SOC, IPEDS, O\*NET. Entirely public,
   already measured, and it answers 16 of the 26 questions on its own.
3. **PWCS prerequisites as the second tier**, which turns the strongest
   questions on and gives the demo its graph-native story.
4. **Measure the resolution rate over all 982 courses**, not 40, and publish it
   in the dataset card — the number the FDA build never got.

The open question that replaces the one this answers: **does a second district
resolve as cleanly?** If yes, this generalises. If no, the product is a
per-district integration, which is a different business.

---

**Method.** Sitemap fetched from `catalog.pwcs.edu/sitemap.xml` (982 URLs);
40 course pages sampled with `random.seed(7)`; prerequisite text extracted from
the rendered page; each name slugified and matched against the sitemap. Every
figure above is from that run and reproducible from it. No figure is estimated.

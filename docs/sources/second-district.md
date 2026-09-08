# Prerequisite COVERAGE does not generalise; resolution does

**Every figure here was printed by `python -m etl.probe_second_district`.** The
record is `second-district-measured.json`;
`tests/test_second_district_doc.py` fails if this page and that record
disagree, in either direction.

    python -m etl.probe_second_district --record

## The question, and why the answer needs two numbers

edtech-kg#19 asks whether a second district's prerequisites resolve as cleanly
as PWCS's, and quotes 89%. That figure has since been superseded — reading the
typed links instead of the prose gives **100%**, recorded in
[`course-prerequisites.md`](course-prerequisites.md) — and it answers only half
the question.

*Resolution* is: of the prerequisite links a district publishes, how many land
on a course it also publishes. *Coverage* is: how many of its course pages
carry such a link at all. **A district with one link that resolves scores 100%
on the first and nothing on the second.**

## The answer

| district | pages | read | with a typed prerequisite | share | links resolving |
|---|---:|---:|---:|---:|---:|
| PWCS (Prince William County, VA) | 817 | 60 | 17 | **28.3%** | 18/18 (100.0%) |
| APS (Arlington, VA) | 698 | 60 | 3 | **5.0%** | 4/4 (100.0%) |
| Clover Park (WA) | 1585 | 60 | 0 | **0.0%** | 0/0 |
| Kenosha (WI) | — | — | — | — | — |
| Central Islip (NY) | 202 | 60 | 5 | **8.3%** | 10/10 (100.0%) |

Ceiling of 60 course pages per district, seed
`19`, the same fields and the same classifier everywhere. Where a
district publishes fewer pages than the ceiling the whole catalogue was read,
so the denominator is **pages read**, never the ceiling.

**Resolution generalises and coverage does not.** Every typed link measured in
every district resolves — 18/18
at PWCS, 4/4 at Arlington,
10/10 at Central Islip. But
**28.3% of PWCS course pages carry a
typed prerequisite against 5.0% of
Arlington's** — 5.7 times as many, and against
0.0% at Clover Park.

## Two fields, and only one of them is a prerequisite field

- **`field-prerequisite-courses`** is an entity reference the CMS links to
  other course pages. A graph edge already.
- **`field-pr`** is free text.

The second is counted here as *"has a non-empty prose field"* and **not** as
*"states a prerequisite"*, because measurement shows it is used as a general
notes field. Among its contents: *"This course is not eligible for high school
credit."*, *"No lab class"*, and several GMU credit notes. An earlier version
of this page divided by that count and so partly measured how chatty each
district's notes are.

Arlington's prose does carry real prerequisites — *"Previous band experience
and audition by band director"* — which is the point. A prerequisite stated in
prose is true, useful and untraversable.

## The structure differs, and the vendor is the same

All five run Clean Catalog, taken from
[the vendor's own K-12 client list](https://www.cleancatalog.com/k12/) rather than
guessed at.

1. **Enumeration.** 3 of the five publish no sitemap, and
   Kenosha's holds no course pages, so four are enumerated by crawling the
   catalogue's own paginated index. On PWCS — the one district where both
   methods work — the crawl finds 792 of the
   sitemap's 817, so the crawl is close to a census
   rather than a sample. That calibration is the only reason the other four
   population figures can be read as counts.
2. **Layout.** Kenosha publishes pathway pages and no per-course pages, so
   there is nothing to attach a prerequisite to.
3. **Field use.** Clover Park publishes 1585 course pages — the
   largest catalogue here — and not one of the 60 sampled carries a
   typed prerequisite.

## What this means

**Prerequisite coverage is a per-district integration, not a national
dataset.** The extractor generalises — one pair of patterns read all five
catalogues — and so does resolution. What does not generalise is whether the
district fills the field in, and PWCS is the outlier that does.

A product built on prerequisite traversal works in Prince William County and
has between a fifth and none of the edges to follow elsewhere.

## What this does not establish

Five districts, one vendor, a ceiling of 60 pages each,
and Arlington's figure rests on 3 typed
prerequisites in 60 pages. It says nothing about districts on other
platforms, and a larger sample would move these percentages.

**An earlier version of this page reported Arlington at 1.7% and Clover Park
with 51 pages.** Those were wrong: the index crawl was not following the
catalogue's pager, so it read the first page of each index and sampled from
that — a biased subset rather than a small one. The pager is followed now, and
Arlington publishes 698 course pages rather than 101. The
direction of the finding survived the correction; the magnitudes did not, which
is the argument for the calibration in point 1 above.

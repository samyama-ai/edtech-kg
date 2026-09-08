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
| PWCS (Prince William County, VA) | 817 | 60 | 17 | **28.3%** | 18/18 |
| APS (Arlington, VA) | 101 | 59 | 1 | **1.7%** | 1/1 |
| Clover Park (WA) | 51 | 51 | 0 | **0.0%** | 0/0 |
| Kenosha (WI) | — | — | — | — | — |
| Central Islip (NY) | 53 | 53 | 2 | **3.8%** | 3/4 |

Ceiling of 60 course pages per district, seed
`19`, the same fields and the same classifier everywhere. Where a
district publishes fewer pages than the ceiling the whole catalogue was read,
so the denominator is **pages read**, never the ceiling.

**Resolution generalises and coverage does not.** Every link PWCS publishes
resolves (18/18), so does
Arlington's one, and 3 of
4 at Central Islip. But
**28.3% of PWCS course pages carry a
typed prerequisite against 1.7% of
Arlington's** — a seventeen-fold difference in whether the edge exists to
follow.

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

## The structure differs three ways, and the vendor is the same

All five run Clean Catalog, taken from
[the vendor's own K-12 client list](https://www.cleancatalog.com/k12/) rather than
guessed at.

1. **Enumeration.** PWCS publishes 817 course pages in a
   sitemap; an index crawl of the same catalogue finds
   73. **3 of the five publish no
   sitemap at all**, and Kenosha's holds no course pages. So the method behind
   PWCS's own population figure does not carry over.
2. **Layout.** Kenosha publishes pathway pages and no per-course pages, so
   there is nothing to attach a prerequisite to.
3. **Field use.** Clover Park's 51 pages carry neither field.

## What this means

**Prerequisite coverage is a per-district integration, not a national
dataset.** The extractor generalises — one pair of patterns read all five
catalogues — and so does resolution. What does not generalise is whether the
district fills the field in, and PWCS is the outlier that does.

A product built on prerequisite traversal works in Prince William County and
has almost nothing to traverse in the other four.

## What this does not establish

Five districts, one vendor, a ceiling of 60 pages each,
and Arlington's figure rests on a single typed prerequisite. It says nothing
about districts on other platforms, and a larger sample would move these
percentages — though not, at seventeen-fold, the direction. What it settles is
the question as asked: **the second district does not carry the edges PWCS
does**, and neither do the third, fourth or fifth.

# Prerequisites do not generalise beyond PWCS

**Every figure here was printed by `python -m etl.probe_second_district`.** The
record is `second-district-measured.json`; `tests/test_second_district_doc.py`
fails if this page and that record disagree, in either direction.

    python -m etl.probe_second_district --record

## The question

edtech-kg#19: PWCS resolves 89% of its named prerequisites. **Does a second
district?** If yes, prerequisites are a national product. If no, this is a
per-district integration — a different business, and one Ruchir should hear
about early.

## The answer: no

| district | pages | enumerated by | state a prerequisite | in the typed field | share |
|---|---:|---|---:|---:|---:|
| PWCS (Prince William County, VA) | 817 | sitemap | 21 | 17 | **81.0%** |
| APS (Arlington, VA) | 101 | index crawl | 20 | 1 | **5.0%** |
| Clover Park (WA) | 51 | index crawl | 0 | 0 | **0.0%** |
| Kenosha (WI) | — | no course pages | — | — | — |
| Central Islip (NY) | 53 | index crawl | 5 | 2 | **40.0%** |

Sample of 60 course pages per district, seed
`19`, the same field and the same rule everywhere.

**PWCS states 81.0% of its prerequisites in the
field that produces an edge. Arlington states 5.0%.**

## Why that is the number that matters

The catalogues carry two different prerequisite fields:

- **`field-prerequisite-courses`** is an entity reference. The CMS links it to
  other course pages, so it is a graph edge already.
- **`field-pr`** is a free-text paragraph.

A district can state its prerequisites completely, accurately and usefully in
the second and publish nothing anybody can traverse. Arlington does exactly
that — *"Previous band experience and audition by band director"* is a real
prerequisite and not an edge.

**Where the links exist, they work.** 18 of
18 PWCS links resolve to a page the same catalogue publishes, and
3 of 4 at Central Islip. The
problem is not broken links. It is that four of the five districts barely use
the field.

## The vendor is the same and the structure is not

All five run Clean Catalog, and they were taken from
[the vendor's own K-12 client list](https://www.cleancatalog.com/k12/) rather than
guessed at. They still differ in three ways that each break a different
assumption:

1. **Enumeration.** PWCS publishes 817 course pages in a sitemap.
   3 of the five publish no sitemap at all — and Kenosha's holds
   only pathway pages — while an index crawl of PWCS finds 73 of its 817 — so the method behind PWCS's own population figure
   does not carry over.
2. **Layout.** Kenosha publishes pathway pages and no per-course pages, so
   there is nothing to attach a prerequisite to.
3. **Field use.** Clover Park's 51 sampled pages state no
   prerequisite at all, in either field.

## What this means

**Prerequisites are a per-district integration, not a national dataset.** A
second extractor is not the cost — the extractor already generalises, and one
regex read all five catalogues. The cost is that **the data is not there to
extract**: the field is optional, and PWCS is the outlier that fills it in.

A product built on prerequisite traversal works in Prince William County and
degrades to prose everywhere else measured. That is worth knowing before it is
promised.

## What this does not establish

Five districts, 60 pages each, one vendor. It says
nothing about districts on other platforms, and a larger sample would move
these percentages. What it does settle is the question as asked: **the second
district does not resolve as cleanly as PWCS**, and neither do the third,
fourth or fifth.

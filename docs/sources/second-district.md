# Districts state prerequisites; only PWCS states them traversably

**Every figure here was printed by `python -m etl.probe_second_district`**,
except the PWCS page counts cited from [`schema.md`](../schema.md), which say
where they come from. The record is `second-district-measured.json`;
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

| district | courses read | state a prerequisite | in a traversable form | links resolving | candidate paths |
|---|---:|---:|---:|---:|---:|
| PWCS (Prince William County, VA) | 60 | 40.0% | **28.3%** | 18/18 (100.0%) | 817 |
| APS (Arlington, VA) | 60 | 56.7% | **5.0%** | 4/4 (100.0%) | 698 |
| Clover Park (WA) | 60 | 1.7% | **0.0%** | 0/0 | 1585 |
| Kenosha (WI) | — | — | — | — | — |
| Central Islip (NY) | 60 | 46.7% | **8.3%** | 5/5 (100.0%) | 202 |

Ceiling of 60 pages per district, seed `19`,
the same fields and the same classifier everywhere.

**The districts are not missing prerequisites. Arlington states more of them
than PWCS does — 56.7% of its
pages against
40.0% — and publishes them in a form nothing
can follow.** 28.3% of PWCS pages
carry a traversable prerequisite against
5.0% of Arlington's.

Resolution, meanwhile, generalises completely: every typed link measured in
every district resolves —
18/18 at PWCS, 4/4 at Arlington,
5/5 at Central Islip.

## Two fields, and both of them carry prerequisites

- **`field-prerequisite-courses`** is an entity reference the CMS links to
  other course pages. A graph edge already.
- **`field-pr`** is free text.

Both hold real prerequisites. One example from each district's record:

- *“Algebra 2   or Trigonometry”* — PWCS
- *“Spanish I, or equivalent proficiency in the language as determined by a placement test.”* — APS
- *“Algebra 2 and Chemistry with passing scores on both regents exams or recommendation from Algebra 2 and Chemistry teacher”* — Central Islip

**An earlier version of this page said `field-pr` was a general notes field**
and quoted *"This course is not eligible for high school credit."* and *"No lab
class"* to prove it. Neither string is in the record, and neither ever was: an
unbounded pattern was reaching into a neighbouring field, so the evidence for
that claim was an artifact of the bug this page's probe later fixed. The
paragraph outlived its evidence, and a test held it in place by asserting the
quotes against the page rather than against the record.

The corrected reading is worse for the thesis, not better. A prerequisite
stated in prose is true, useful, and untraversable — and Arlington states more
of them than PWCS.

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
2. **Layout.** Kenosha's sitemap lists no two-segment path and five index
   candidates yielded none, so nothing here found a per-course page to attach
   a prerequisite to. A district publishing courses at three segments would
   produce the same row, so this is *not found by this method* rather than
   *does not exist*.
3. **Field use.** Clover Park's 60 read pages carry neither field —
   the only district here that states no prerequisites at all.

### Candidate paths are not courses

The last column counts two-segment paths, which is a candidate rule, not a
classification. PWCS publishes 960 pages of which [`schema.md`](../schema.md)
counts **791 courses**, 127 subject indexes and 42 pathways, and quotes every
PWCS rate against the 791. So 817 is a larger set.

**The share columns do not use it.** Each sampled page is fetched and then
classified by `etl/pwcs_pages`'s own rule — the markup, not the depth — and a
pathway leaves the denominator. **That rule looks for a field configured in
PWCS's instance**, and it removed
0 pages across
all five districts, so it is demonstrated only where there was nothing to
remove.

## Licence

**Not settled, and the same position as
[`course-prerequisites.md`](course-prerequisites.md)** — which says of PWCS
that "reuse permission is a human decision rather than a published licence".
This page adds four more districts on the same footing.

What was checked: all five publish a `robots.txt` whose disallow rules cover
Drupal internals only — `/core/`, `/admin/`, `/profiles/` — with nothing
touching `/subject/course` and no `Crawl-delay`. The probe identifies itself,
sends one request at a time with a delay, samples rather than sweeps, and
stops on a 429 rather than finishing.

**That is a courtesy check, not a licence.** These are public catalogues
published for students and counsellors; nothing here grants redistribution.
**No district's course text is republished** — the record holds counts, and
the prose examples quoted above are short excerpts shown to evidence a
measurement.

## What this means

**Prerequisite coverage is a per-district integration, not a national
dataset.** The extractor generalises, resolution generalises, and the
prerequisites themselves are there — what does not generalise is the *form*.
PWCS is the outlier that uses the field a machine can follow.

A product built on prerequisite traversal works in Prince William County and
degrades to prose in three of the other four.

## What this does not establish

Five districts, one vendor, a ceiling of 60 pages each.
It says nothing about districts on other platforms.

**The sample is small enough that the point estimates should not be read to a
decimal.** 28.3% is
17/60 and
5.0% is
3/60; their 95% intervals are roughly
17–40% and 1–14%. They do not overlap, so *PWCS is the outlier* holds — but
the ratio between them is not pinned to one significant figure by three
observations at Arlington.

**"Resolves" is set membership against our own enumeration, not a fetch.** For
the four crawl-enumerated districts that means "the index links it too". No
link was HEAD-checked.

**Three corrections are recorded rather than swapped in**, because a page
that silently replaced its numbers would leave the next reader unable to tell
a re-measurement from a redefinition.

| | what changed | superseded | now |
|---|---|---|---|
| **1** | the crawl was not following the catalogue's pager, so it read the first page of each index and sampled from that — a *biased* subset, not a small one | Arlington 101 pages, Clover Park 51 | Arlington 698, Clover Park 1585 |
| **2** | links were not deduplicated, so a course linked twice counted twice — in a rate whose whole claim is that the links land | Central Islip 10 resolving links | 5/5 |
| **3** | **the metric was redefined.** "States a prerequisite" excluded the prose field, on the strength of examples that turned out to be artifacts of an unbounded pattern. Including prose is what put Arlington above PWCS | *"28.3% of PWCS pages carry a typed prerequisite against 5.0% of Arlington's — 5.7 times as many"* was the headline | the traversable figures are unchanged; the page now leads with **coverage**, where Arlington is ahead |

**And the sentinel behind correction 3 was wrong once more after that.** It
matched four exact strings, so a trailing full stop flipped the answer:
`None.` counted as a stated prerequisite, and so did *"NO PRIOR FILM
EXPERIENCE REQUIRED."* Three of eight sampled Arlington examples were
non-statements. That took Arlington from 60.0% to
56.7% and PWCS from 39.0% to
40.0% — the direction survived, the margin
narrowed.

[`course-prerequisites.md`](course-prerequisites.md) records the same mistake
as a past correction — *"counted 'Prerequisite: None' as a stated
prerequisite"*. This repo learned it once and made it again, which is why
`tests/test_course_page_against_pwcs.py` now runs the classifier over the
cached PWCS corpus and asserts no denial counts as a statement.

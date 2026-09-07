# Texas CTE — the flag is real, the career clusters are not

Answering edtech-kg#49, which recorded that the TWEDS **C022** table "carries a
`CTE Course` flag and organises courses by **career cluster**", and hoped a
cluster would join to SOC or CIP — giving a course a route to an occupation
with no prerequisite data at all.

**Half of that is true. The flag is there. The cluster is not, and there is no
join to CIP or SOC anywhere in the published data.**

Every figure below is printed by `python -m etl.probe_texas_cte` and committed
as [`texas-cte-measured.json`](texas-cte-measured.json). Nothing is typed.

---

## Getting the file is the first finding

The issue calls C022 "downloadable as CSV". That is true only once you know a
URL the page does not give you.

The code-table page is a **JavaScript shell**: the served HTML holds `0`
`<table>` elements, `0` rows and no code ids at all — twelve `<script>` tags and
nothing else. `curl` on it returns a page with no data in it, which reads as the
table having moved rather than as the page being an application.

Rendered in a browser, it offers **Download All Code Tables**, and that link is
plain-fetchable once known:

```
https://tealprod.tea.state.tx.us/TWEDS/103/1131/2258/0/CodeTable/DownloadAll
```

One zip, **130 code tables**, 95 KB. The probe fetches that directly, so nobody
has to render the page again.

*(`tealprod.tea.state.tx.us/robots.txt` returns 200 with an HTML error page, not
a robots file — so that host publishes no crawl policy at all. `tea.texas.gov`
serves a stock Drupal robots.txt that blocks nothing relevant, which is
consistent with [`state-access.md`](state-access.md) finding Texas the one
automatable department of five.)*

## What C022 carries

| | |
|---|---:|
| rows | **1,675** |
| CTE-flagged courses | **533** |
| columns | `Code`, `Translation`, `Eligible for State HS Credit`, `Course Abbreviation`, `Course Units`, `CTE Course`, `Subject`, `Subject Area` |

**The flag does not hold what you would guess.** Its values are `H` (531), `M`
(2) and blank (1,142) — high school and middle school, not `1`/`Y`. Testing for
the obvious values counts **zero** CTE courses and reads as "the flag is empty",
which is a wrong finding rather than a failed one. The probe records the values
it found rather than the ones it expected.

## What C022 does not carry

**`Subject` and `Subject Area` are empty on all 1,675 rows.** Not sparse —
empty. Those are the two columns that could have carried the grouping, and the
career-cluster structure the issue describes is not in the published version.

Nor is it elsewhere. Of the 130 tables, the four whose text mentions *cluster*,
*career* or *endorsement* are programme-type code lists — `C049` (26 rows,
"Adult Basic Education", "Gifted and Talented"), `DC096` (40 rows,
"Career and Technical Education" as one programme type among forty), `DC091`,
`C217`. None is a taxonomy of career areas.

## No route to an occupation

A course reaches an occupation only through CIP or SOC. Searched across **every
one of the 130 tables**, not just C022:

- **SOC-shaped codes (`nn-nnnn`): zero.**
- CIP-shaped codes (`nn.nnnn`): 37 matches, **all false positives** — statute
  references such as `TEC 12.1141(c)`, and text inside descriptions. That
  verdict is a reading, not something the probe decides: it records the matched
  strings themselves alongside the counts, so the next reader can check the
  reading rather than repeat it. `tests/test_texas_cte_doc.py` fails if this
  page calls them statute references while the record holds no sample.

So the hoped-for chain — course → cluster → occupation — has no second link and
no third.

## What this means for the question it was raised against

edtech-kg#49 asked whether this was "a weaker link we can have today". On the
current published version it is **not a link at all**: a boolean saying a course
is CTE, with nothing to join it to.

That is still worth having recorded. It closes a route that looked open, and it
does so with a measurement rather than an impression — which is the difference
between this and the next person spending a day on the same page.

**The licence question does not arise**, because there is nothing to license: no
cluster taxonomy is published here, so the Advance CTE "all rights reserved"
position in [`code-sets.md`](code-sets.md) is not engaged by this route.

## What would change the answer

- **A different table.** 130 were searched by content, but TWEDS publishes more
  than code tables — data components and submission rules were not read.
- **A different Texas source.** `txcte.org` returned **503** while this was
  measured and was not reachable at all; it is the site the issue's framing most
  likely came from, and it is not TWEDS.
- **A newer version.** This is TEDS **2023-2024**, published version
  **2024.2.1**, read on the date in the record. A column empty in one version is
  not empty forever.

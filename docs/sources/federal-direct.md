# Reading IPEDS, CCD and College Scorecard direct

**edtech-kg#43.** Every measured count in this repo arrives through the Urban
Institute Education Data API. This asks whether the federal collections can be
read at source instead, so that one third party is not a single point of
failure for the whole measured base.

Read on **2026-09-01**. Every figure below is printed by
`python -m etl.probe_federal_direct --deep`, never typed, and the run is
committed as [`federal-direct-measured.json`](federal-direct-measured.json).

## The reason this was raised has already gone

#43 was written because the wrapper's own terms were unconfirmed (#13), which
made *"one unresolved licence question a single point of failure for the entire
measured base."*

**That is settled.** #101 read Urban's terms: they republish under **ODC-By**,
checked 2026-08-31, and reuse and re-sharing are permitted with citation.

So this is no longer a licence question. It is a robustness one — whether
depending on a single wrapper is wise — and that is a weaker reason. The
recommendation below is correspondingly smaller than the issue anticipated.

## What each route costs

| route | status | size |
|---|---|---|
| IPEDS completions, one year, direct | 200 | **7.9 MB** |
| Scorecard bulk, institution | 200 | 22.5 MB |
| Scorecard API | **403** | needs an API key |
| CCD file index | 200 | carries no data links |
| Urban wrapper, for comparison | 200 | — |

**IPEDS is one file.** `c2022_a.csv` arrives as 7.9 MB
compressed. The issue asked whether completions at CIP-6 exists as a single
download per year rather than nine million rows through a paging API. It does.

**College Scorecard splits in two.** The API answers `API_KEY_MISSING` without
a registered key; the bulk files on the same site need none. "Scorecard needs a
key" is true of one route and false of the other.

**CCD is the one that resists.** Its file index and its data page both answer
200 and neither carries a single data link — the navigation is JavaScript, and
`/ccd/Data/zip/` answers 403. A direct CCD reader would have to guess a URL
pattern or drive the site. **Not established**, and said plainly rather than
left as an implied yes.

## The finding that matters most

The wrapper reports **9,026,310** rows for completions at CIP-6.
The direct file for the same year holds **300,877**.

That looks like the direct file is missing 97% of the data. It is not:

    300,877 rows x 30 demographic columns = 9,026,310

which is the wrapper's figure exactly. **IPEDS carries demographics as columns
and the wrapper unpivots them into rows.** The two describe identical data in
different shapes.

The counts therefore **reproduce**. Switching routes would not move any
published figure — the discrepancy #43 asked us to explain rather than average
away turns out to be a shape rather than a loss.

### And 9,026,310 is not a number of graduates

It is a row count of the unpivoted form. Summed properly, the same file reports
**10,620,172** awards for first majors — *more* than the row
count it is easy to mistake for awards.

`README.md` and `docs/schema.md` both say "rows", which is accurate. But
"9,026,310 completions" reads as nine million people to anyone who
has not opened the file, and the real figure is larger. Worth stating the award
count beside the row count wherever the graph is described to someone outside
this repo.

## Two things the direct route exposes and the wrapper does not

The zip carries **2 members** — `c2022_a.csv`, `c2022_a_rv.csv`.
The `_rv` file is the **revised** release, and choosing the wrong one is a
silent difference in every downstream figure. A wrapper picks for you; going
direct means picking, and saying which.

The file also carries **30 `X` flag columns** beside the
30 counts — IPEDS imputation flags, recording whether a
value was reported or derived. The wrapper's row form drops them. Nothing here
uses them yet, and any claim about data quality would want them.

## Recommendation

**Stay on the wrapper, and stop describing it as a risk.** Its licence is
cleared, its counts reconcile exactly, and it removes per-collection work that
CCD in particular would make real.

Go direct for IPEDS only if a specific need appears — the imputation flags, the
revised-versus-original distinction, or a year the wrapper has not loaded.
`c2022_a.csv` is 7.9 MB and the reader is about thirty
lines, so that door stays cheap to open.

**Do not build a CCD reader on what is known today.** Its files are not
reachable by a documented static URL, and that is the finding rather than a gap
to be filled in quietly.

## What this does not establish

- Whether the wrapper drops fields **other** than the `X` flags. Only the
  completions collection was compared, and only on row shape.
- Whether CCD publishes flat files at a stable URL at all.
- Anything about years other than the one measured.

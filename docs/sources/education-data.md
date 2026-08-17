# Education data sources — measured

Every figure here is printed by `python -m etl.probe_education`. None is typed
by hand, and none should be. Re-run the script to verify them.

**Measured 2026-08-17T10:42:03+00:00**, data year **2022**, via `https://educationdata.urban.org/api/v1`.

## Counted live

| Source | Records | Endpoint |
|---|---:|---|
| IPEDS completions (CIP 6-digit) | **9,026,310** | `college-university/ipeds/completions-cip-6/2022/` |
| IPEDS institution directory | **6,256** | `college-university/ipeds/directory/2022/` |
| CCD school directory | **102,268** | `schools/ccd/directory/2022/` |
| CCD district directory | **19,714** | `school-districts/ccd/directory/2022/` |

`completions-cip-6` is one row per institution x programme x award level x
demographic, which is why it is three orders of magnitude larger than the
institution count. It is the volume that decides how much of a year can be
loaded, not how many things exist.

## Named but not counted here

These are not reachable through the API above, so the table is silent on them.
Recording that rather than letting the silence read as absence.

| Source | Access | Why it matters |
|---|---|---|
| NCES-BLS CIP-SOC crosswalk | xlsx download | The programme-to-occupation join this graph rests on |
| O*NET occupation database | bulk download | Occupation attributes, skills and earnings |

**The CIP-SOC crosswalk is the important one.** It is the join every answerable
question in `../questions.md` depends on — the government-published link from a
degree programme to the occupations it leads to. It is published as a
spreadsheet rather than an API, so it needs its own probe once the file is
mirrored somewhere citable. Counted by hand on 2026-08-13 at 6,097 rows, 2,143
CIP codes and 868 SOC codes; **that figure is not yet reproducible from code
and should not be quoted as measured until it is.**

## Reproducing

```bash
python -m etl.probe_education              # the table above
python -m etl.probe_education --json       # machine-readable, with timestamp
python -m etl.probe_education --year 2020  # a different year
```

The script refuses rather than reporting a zero: a wrong year or a renamed
dataset answers 200 with `count: 0`, and a table row reading 0 would look like
a measurement rather than a broken request.

## Licence

The Urban Institute Education Data API republishes US federal data (IPEDS and
CCD, both NCES). **Licence position still to be confirmed and recorded** —
see #6. The underlying federal data is US-government public domain; the API
wrapper's own terms have not yet been checked, and that check is not optional
before anything is published from it.

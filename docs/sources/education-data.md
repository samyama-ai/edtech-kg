# Education data sources — measured

Every figure here is printed by `python -m etl.probe_education`. None is typed
by hand, and none should be. Re-run the script to verify them.

**Measured 2026-08-17T10:42:03+00:00**, data year **2022**, via `https://educationdata.urban.org/api/v1`.

## Counted live

**Rows, not awards.** The wrapper unpivots IPEDS's 30 demographic
columns into rows: 300,877 source rows become 9,026,310, and the awards they
describe are 10,620,172. See [`federal-direct.md`](federal-direct.md) (#43).

| Source | Records | Endpoint |
|---|---:|---|
| IPEDS completions (CIP 6-digit) | **9,026,310** rows | `college-university/ipeds/completions-cip-6/2022/` |
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
| O\*NET occupation database | bulk download | Occupation attributes, skills and earnings |

**The CIP-SOC crosswalk is the important one.** It is the join every answerable
question in `../questions.md` depends on — the government-published link from a
degree programme to the occupations it leads to. NCES publishes it as a
spreadsheet rather than an API, so it has its own probe:
`python -m etl.probe_cipsoc`. Measured at **5,903 mappings** over 2,143 CIP
codes and **867** SOC codes, with 194 programmes mapping to no occupation and
180 occupations reachable from no programme. The 194 appear on the CIP-SOC
sheet as `99-9999 NO MATCH` rows, which is why the earlier figures of 6,097 and
868 were each inflated — the sentinel is not an occupation and its rows are not
mappings (edtech-kg#70). Full detail in
[`cip-soc-crosswalk.md`](cip-soc-crosswalk.md).

O\*NET remains a bulk download rather than a queryable count, and is still
unprobed.

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

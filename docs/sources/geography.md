# Geography — what "near me" needs, and how much of it we already have

Answering edtech-kg#44. Q13 (*which colleges near me offer this programme*) and
Q25 (*are high-earning occupations reachable from low-income districts*) both
need location, and the graph holds none.

**The short answer: point geography is already in a source this repo has
cleared, and nobody noticed. Boundaries are the only part that needs a new
one.**

Every figure below is printed by `python -m etl.probe_geography` and
committed as [`geography-measured.json`](geography-measured.json). Nothing is
typed, and `tests/test_geography_doc.py` holds this page to that record in both
directions.

---

## Coordinates arrive with the directories we already read

The issue assumed NCES EDGE was needed for school and institution locations. It
is not. The Urban Institute wrapper — already in `docs/scope.md` under ODC-By,
already the route every measured count in this repo arrives through — carries
`latitude` and `longitude` on both directories.

| source | records | sampled | usable coordinates |
|---|---:|---:|---:|
| CCD school directory, 2022 | 102,268 | 32,268 over pages [1, 4, 7, 11] | **100.0%** |
| IPEDS institution directory, 2022 | 6,256 | **all 6,256 — a census, not a sample** | **100.0%** |

Neither absent values nor null-island `(0, 0)` appeared in any of them — the
probe counts all three outcomes separately rather than inferring coverage from a
total. The CCD figure is a strided sample and the record names the pages it
read; the IPEDS population fits one page, so `is_census` is true.

*(An earlier draft said 22,268 over pages 1, 5 and 11 — figures measured by hand
in a shell. The probe's stride reads 32,268 over pages [1, 4, 7, 11]. Same
finding, different arithmetic, and the reason the rule is that a probe prints
the number.)*

Both also carry `fips`, `county_fips`/`county_code`, `zip` and `cbsa`, which
answer coarse "near me" without any geometry at all — a county or a CBSA match
needs no boundary file and no spatial index.

**This changes what #44 costs.** No new source, no new licence question, and no
join to establish: the coordinates come attached to the rows the loader already
reads, keyed the way those rows are already keyed.

## Boundaries are the part that is genuinely missing

"Which district contains this address" needs geometry, and neither directory
carries it. Census TIGER does:

- `TIGER2022/UNSD/` — **56 state files** of unified school district
  boundaries, vintage 2022, public domain.

**And the vintage risk the issue names is real but avoidable.** A boundary file
from one year against a directory from another assigns schools to the wrong
district silently — no error, and every downstream equity answer inherits it.
The repo's CCD and IPEDS data year is **2022** (`DATASET-CARD.md`), and TIGER
publishes a 2022 vintage, so the two can be pinned to the same year. That is a
decision to record when boundaries are loaded, not a discovery to make
afterwards.

## An API fact worth writing down

`per_page` is ignored above a cap. `?per_page=100` and `?per_page=500` both
return **10,000 rows**, so the CCD school directory is
**11 pages, not 1,023**. The probe asks rather than assuming, and records
both numbers.

Anyone computing a stride from their requested page size gets a page number far
past the end and a 404 — which is exactly what happened while measuring this,
and it is the kind of error that looks like the source being broken rather than
the caller being wrong.

## What is still open

- **The join for boundaries.** Which identifier ties a TIGER `UNSD` polygon to a
  CCD `leaid`, and whether it is stable across years. Not measured here.
- **Whether a spatial index is needed at all.** If "near me" means a county or a
  CBSA, the codes above answer it and no geometry is loaded. If it means a
  radius, geometry is unavoidable. That is a product question, and it should be
  answered before the boundary files are downloaded rather than after.
- **`Place` is declared and unpopulated** in the schema — in the tier-2 file,
  which arrives with the branch for edtech-kg#157 and so is named rather than
  linked here. Nothing loads it; this establishes what could.

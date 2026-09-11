# Dataset card — edtech-kg

An education-to-career pathways knowledge graph. What follows is what has been
**measured**, what has been **loaded**, and what this build gets wrong.

Every figure on this page is printed by a probe in `etl/` and committed as a
record under `docs/sources/`. A number here with no record behind it is a
defect, and `tests/test_dataset_card.py` fails on one.

## Sources measured

| Source | Publisher | Records | Format | Licence | Measured |
|---|---|---:|---|---|---|
| IPEDS completions (CIP 6-digit) | Urban Institute wrapper | **9,026,310** | JSON API | ODC-By | 2026-09-01 |
| IPEDS institution directory | Urban Institute wrapper | **6,256** | JSON API | ODC-By | 2026-09-01 |
| CCD school directory | Urban Institute wrapper | **102,268** | JSON API | ODC-By | 2026-09-01 |
| CCD district directory | Urban Institute wrapper | **19,714** | JSON API | ODC-By | 2026-09-01 |
| CEDS ontology | US Dept of Education | **1,369** classes | RDF/OWL | Apache-2.0 | 2026-08-28 |
| Credential Registry | Credential Engine | **398** sampled | JSON-LD | **not cleared** | 2026-08-31 |
| O\*NET crosswalk workbooks | US Dept of Labor | 2 workbooks | XLSX | CC BY 4.0 | 2026-08-31 |
| PWCS course catalogue | Prince William County Schools | 791 courses | HTML | not settled | `sources/course-prerequisites.md` |

Counts come from `python -m etl.probe_education --record`; licences from
`probe_licences`, `registry_licence` and `probe_ceds`.

### The completions figure is rows, not people

**9,026,310** is a row count, and the row is
a demographic cell. IPEDS publishes **300,877** rows and carries the
demographics as columns; the wrapper unpivots them, and
300,877 × 30 = 9,026,310 exactly.

The awards those rows describe are **10,620,172** for first
majors — a different quantity, and a larger one. Quote the award count when
describing this graph; quote the row count only when describing the node.
Measured in [`docs/sources/federal-direct.md`](docs/sources/federal-direct.md).

## What is loaded

**One district.** Prince William County Public Schools, from pages this repo
cached — 1,098 nodes and 1,417 edges.

That edge count said **1,287** until #25 counted the graph per type rather
than quoting a figure. It is 1,417: REQUIRES 240, IN_SUBJECT
723, INCLUDES 316, HAS_REQUIREMENT
138. `README.md` had the right number and this card had a
different one, which is what a hand-maintained count does.

**Do not read the edge count from `/api/status`.** On a Cypher-loaded graph it
reports **2,834** for the 1,417 edges above; the same graph imported from a
snapshot reports 1,417.

The two graphs are the same graph. The distinction matters: if `storage.edges`
counted stored adjacency entries and the import kept only one per edge, then
the endpoint would be right and this snapshot would be lossy.

That is excluded by the **reverse expansion**, which both engines answer
identically — 240, 723, 316, 138, **1,417** in total:

    MATCH (c:Course)<-[r:INCLUDES]-(:Pathway) RETURN count(r)     316 on both

Starting from a `Course` and walking the edge backwards, an engine holding
one adjacency entry at the tail could not answer that. It answers. This is
also the query the walkthrough already rests on — `demo/demo.py` runs the
pattern and `docs/questions.md` makes the reverse edge a supported question.

The undirected count is recorded too but does **not** settle it on its own: it
comes back at exactly twice directed for all four types on both engines, which
is as much the signature of a doubling rule as of a traversal. Nor does
`storage.nodes` matching at 1,098 — a lossy-edge import would match on nodes
too. All three readings are in
[`sources/snapshot-measured.json`](docs/sources/snapshot-measured.json) under
`edge_count_readings`, from both engines.

**One state's higher education.** Virginia (`fips=51`), data year 2022 —
147 institutions, 663 programmes and
51,085 completions, with 51,085 `AT` edges and
51,085 `IN` edges. **Read back out of the graph after the load, never
inferred from the input rows** — the loader reports both and the two agree.

| | |
|---|---|
| Load time | **1425.7s**, 308,130 statements |
| Re-run over the loaded graph | 154,065 statements, **0 created** — the load is idempotent, measured rather than asserted |
| Written by | `etl/load_education.py`, from `etl/download_education.py`'s cached slice |
| Rate curve, the slice, and the schema defect the load found | [`docs/national-spine.md`](docs/national-spine.md) |
| Rows deliberately dropped | 125,692 recording zero awards, 13,950 institution-TOTAL rows (CIP 99 is a sum of the others, not a programme), 43 collapsing onto one key |
| Not loaded, though #7's scope names them | earnings, and any outcome after the award |

| graph artefact | |
|---|---|
| `edtech-kg.sgsnap` | **about 157 KB**, imports in **0.03s** into a clean engine |
| Against | a load of about 8 seconds — and no network, no source pages |
| Published as | a release asset. Not committed: `data/` is gitignored and a graph artefact is not source |
| Size varies | exporting the same graph twice gives different bytes — so a download is checked against the published file's hash, not by re-exporting |
| Verified by | `python -m etl.snapshot verify`, per label and per edge type, before a demo opens |

**Programmes to occupations.** The NCES/BLS CIP-SOC crosswalk, edition
CIP2020-SOC2018 — 867 occupations and
2,219 `PREPARES_FOR` edges, joining
634 of the 663
programmes above to the work they lead to.

| | |
|---|---|
| Written by | `etl/load_cipsoc.py`, reading through `etl/probe_cipsoc.py` |
| Load time | **28.0s**, 6,172 statements |
| Re-run over the loaded graph | **0 created** — idempotent, measured rather than asserted |
| Mappings read | 5,903, of which 3,684 name a CIP code this graph does not hold |
| Why that gap | **scope, not loss** — the crosswalk covers every CIP code; this graph holds only what Virginia awarded in 2022 |
| The edition is on the EDGE | the crosswalk is a published claim with a revision history, so two editions can disagree without one silently replacing the other |

Everything else above is measured at the source and **not loaded**.

**Node and edge counts for the other sources are absent, not blank.** No loader
has run for them. **Sixteen labels are declared and eight are written**, so
eight hold nothing:

- `schema/edtech_kg.cypher` declares ten. `etl/load_pwcs.py` writes `Course`,
  `Subject`, `Pathway` and `Requirement`; `etl/load_education.py` writes
  `Institution`, `Programme` and `Completion`; `etl/load_cipsoc.py` writes
  `Occupation`; `School` and `District` wait on a loader.
- `schema/edtech_kg_tier2.cypher` declares six, all empty: `Credential`,
  `AwardingBody`, `Level`, `Competency`, `EarningsRecord` and `Place`. The
  four Registry labels among them are blocked on the licence above, not on a
  loader.

This said "eight" and named six of the twelve, which is what happens when a
count is maintained by hand beside a schema that grew — and it then said
"four" and "twelve" for a while after a loader had made both wrong, which is
the same failure a second time. A count of zero would read as a measurement;
for the nine there has been none.

## Licences, and what may be done with each

| Source | Position | May this repo load it? |
|---|---|---|
| IPEDS, CCD, College Scorecard | US-government public domain | yes |
| Urban Institute wrapper | ODC-By, checked 2026-08-31 | yes, with citation |
| O\*NET crosswalk workbooks | CC BY 4.0 by the crosswalks page's own notice | yes, with the stated attribution |
| O\*NET Database | CC BY 4.0 **except** the crosswalks page it excludes | not the route this repo reads |
| CEDS | Apache-2.0 | yes |
| **Credential Registry data** | internal use only; any application or redistribution needs a signed Developer Agreement | **no** |
| PWCS catalogue | public pages, reuse permission unsettled | not settled — `docs/scope.md` |

The Registry row constrains the design: CTDL the **vocabulary** is openly
licensed and the **data** is not, and conflating the two is easy. Measured in
[`docs/sources/registry-data-licence.md`](docs/sources/registry-data-licence.md).

## Measured or estimated, per source

Everything in the source table is **measured** — a probe fetched it and the run
is committed. Nothing here is extrapolated.

Two figures are **bounded rather than complete**, and say so where they appear:
the Credential Registry reads 398 envelopes spread
across the population rather than all of it, and the PWCS catalogue is one
district at one point in time.

## Versions

| | |
|---|---|
| Code | Records carry a `code` stamp — the commit the tree was at when the probe ran, whether it was clean, and the package version — written by `etl/provenance.py`. **Records written before that mechanism existed carry no stamp; they gain one when their probe is next run (#6).** `tests/test_provenance.py` lists which are still unstamped. The commit that *contains* a record cannot be inside it. |
| Data year | **2022** for IPEDS and CCD |
| Engine | `1.1.0` pinned in CI; `1.7.0` also verified against the parse table |
| Graph artefact | `edtech-kg.sgsnap`, a release asset — see the table above. Not committed: `data/` is gitignored |

## Known issues

Written before anyone finds them.

- **One district, one snapshot.** Prerequisite chains describe PWCS as cached,
  not US schooling. A second district is #19 and has not been done.
- **No national prerequisite graph.** `REQUIRES` is populated for one district,
  and nothing joins secondary courses to post-secondary programmes as data —
  a real gap, and #66.
- **The completions figure is the one most likely to be misread** on this page,
  and it is the largest. See above.
- **Only 1 of 5 state education departments answers an
  automated request at all.** 2 refuse with a 403 — `robots.txt`
  included, so it is not an agent policy — and the rest fail on a redirect
  loop or a TLS error. State coverage is not a matter of effort. Measured in
  [`docs/sources/state-access.md`](docs/sources/state-access.md).
- **CCD cannot be read direct.** Its file index carries no data links and
  `/ccd/Data/zip/` answers 403, so CCD arrives only through the wrapper.
- **The Credential Registry cannot be loaded at all**, which removes the one
  source publishing pathways as structured data nationally.
- **Two sources are loaded: one district and one state's higher education.**
  Everything else above is a source this repo can reach, not a graph it holds
  — the counts for those describe what the source publishes.

## Usage

    docker run --rm -p 8080:8080 -p 6379:6379 \
      public.ecr.aws/f9f6l5u4/samyama-graph:1.1.0
    python -m etl.load_pwcs --graph edtech

    # and the national spine — the download is cached, the load takes ~24 min
    python -m etl.download_education
    python -m etl.load_education --graph edtech

See [`docs/scope.md`](docs/scope.md) for what this graph deliberately does
not model. `CONTRIBUTING.md` carries the PR and evidence standards — named
rather than linked because it arrives with #26, which is not merged yet.

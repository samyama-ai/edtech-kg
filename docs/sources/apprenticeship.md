# Registered Apprenticeship — the route to an occupation that is not a degree

Every figure on this page is printed by `python -m etl.probe_apprenticeship`.
None is typed.

**edtech-kg#39** asks whether apprenticeship is reachable as data, and how many
occupations it reaches that a CIP programme does not. The answer is yes, and
**63** — but the 63 are not the occupations the question expected, and that is
the more useful half of the finding.

## The headline

1. **Apprenticeship data is public and record-level** — but not by the routes
   the issue names. DOL's own endpoints do not answer; O\*NET publishes the
   crosswalk.
2. **419 SOC occupations are reachable by apprenticeship**, and **63 of them
   are reachable no other way** — this graph has no shape for those at all.
3. **The 63 are not the trades.** Construction and maintenance — the
   occupations everyone associates with apprenticeship — are almost entirely
   visible through CIP already. The gap is in **Production**.

## Where it actually comes from

edtech-kg#39 names apprenticeship.gov and the RAPIDS datasets on data.gov.
Measured, neither answers (`--reach`):

| Source | Identified UA | No UA |
|---|---|---|
| `careeronestop.org` (web) | **403** | **403** |
| `api.careeronestop.org` | **no connection** | **no connection** |
| `apprenticeship.gov` (web) | 200 | 403 |
| `api.apprenticeship.gov` | **name does not resolve** | — |
| `catalog.data.gov` `package_list` | **404** | **404** |
| `catalog.data.gov` `package_search` | **404** | **404** |
| control: `onetcenter.org` | 200 | 200 |
| control: `nces.ed.gov` | 200 | 403 |
| control: `careertech.org` | 200 | 200 |
| **O\*NET RAPIDS crosswalk** | **200** | **200** |

Four things about that table are deliberate.

The **control rows** are in the run, not in a sentence. They are what rules out
a general egress failure, so they have to be reproducible alongside the
failures rather than asserted beside them.

The **data.gov endpoints are named individually**. This page said "404 on every
standard CKAN endpoint" while one endpoint was probed; two are probed now and
the claim is only as wide as the table.

**`api.apprenticeship.gov` resolves nowhere** — no A record from the system
resolver, `8.8.8.8` or `1.1.1.1`, all three asked in the run. That is the one
row here that can be asserted about the publisher rather than about this
network.

And these are **`HEAD` requests**. A 403 or 405 to HEAD is **not evidence about
GET**. On a page about telling failure modes apart, that limit belongs on the
page.

Note `apprenticeship.gov` at 200 identified and 403 anonymous: an anonymity
block, the shape `docs/sources/bls-occupation.md` measured on `www.bls.gov`.
CareerOneStop returns 403 to both, which is a different thing —
`docs/sources/careeronestop.md` turns on that distinction.

So the answer to "which files are genuinely public and record-level, versus
dashboards and aggregates" is that DOL publishes the dashboard and **O\*NET
publishes the data**:

    https://www.onetcenter.org/crosswalks/rapids/Apprenticeship_RAPIDS_to_ONET-SOC.xlsx

The comparison side is O\*NET's CIP crosswalk, so both routes are counted in the
same vocabulary rather than one being converted into the other.

## What apprenticeship reaches

| | |
|---|---:|
| RAPIDS rows | **1,439** |
| Distinct apprenticeship codes | **1,171** |
| O\*NET-SOC occupations reached | **449** |
| Rolled up to SOC | **419** |

## Against the programme route

| | |
|---|---:|
| SOC reachable by a CIP programme | **688** |
| Reachable **both** ways | **356** |
| Reachable **only** by apprenticeship | **63** |
| Reachable only by a programme | **332** |

The 63 is the number edtech-kg#39 asked for. A course-planning product built
only on programmes cannot see a public, funded route into any of them.

## But they are not the trades

The issue's framing is that "for a substantial set of well-paid occupations
the road runs through an apprenticeship instead" of a degree. Measured, the
occupations where that is *exclusively* true are somewhere else:

| SOC major group | Apprenticeable | Also via a programme | **Only apprenticeship** |
|---|---:|---:|---:|
| Construction & Extraction | 39 | 32 | **7** |
| Installation, Maintenance & Repair | 46 | 42 | **4** |
| Production | 81 | 52 | **29** |

The construction and maintenance trades — electrician, plumber, HVAC, the
occupations the word "apprenticeship" calls to mind — are **already visible**
through CIP, at 82% and 91% coverage. Building the apprenticeship route to
reach them would add almost nothing.

The 63 are dominated by **Production** (29) and Transportation (8): machine
setters, operators and manufacturing roles that no CIP programme maps to. That
is the gap, and it is a narrower and more specific one than the issue assumed.

## The join

| | |
|---|---:|
| SOC our CIP-SOC crosswalk carries | **867** |
| Of those, apprenticeable | **419** |
| Apprenticeship SOC **not** in ours | **0** |
| Naive `O*NET-SOC == SOC` matches | **0** of 449 |

Two things follow. **The join is clean**: every apprenticeable occupation is
already a code this repo carries, so an apprenticeship route needs no new
occupation vocabulary — only a new edge into the ones that exist.

And the suffix problem holds on a second, independent file. Every O\*NET-SOC
code carries a `.NN` suffix, so string equality against a SOC code matches
**nothing**. That is the safe failure — a partial match would be the dangerous
one — and it is the same result the code-set survival research measured on the
O*NET occupation listing, which arrives with edtech-kg#36 and is not on this
branch. Confirmed here independently rather than cited, which is the point: two
files, same rule.

## What this does not establish

- **Sponsor and programme location are not in this file.** It is an
  occupation-to-occupation crosswalk, so "is there an apprenticeship near me"
  is still unanswered. edtech-kg#39 asks for location and this does not carry
  it; the RAPIDS programme records that would are behind the endpoints above.
- **Coverage by state is not measured**, for the same reason. State agencies
  feed RAPIDS unevenly and this file cannot show that.
- **No wage or quality signal.** "Well paid" is not tested here; that would come
  from `docs/sources/bls-occupation.md`, and pairing the two is worth doing
  before anyone builds on the 63.
- The RAPIDS codes are the **approved occupation list**, not active programmes.
  An occupation can be approved with no live programme in it.

## Licence

O\*NET crosswalk files are published by the O\*NET Resource Center under
CC BY 4.0. The RAPIDS occupation list is a US federal government work.
Redistribution of the derived counts is not in question; a loader would carry
the attribution O\*NET asks for. See edtech-kg#14 for the standing O\*NET
licence question.

## Re-run

```bash
python -m etl.probe_apprenticeship            # the tables
python -m etl.probe_apprenticeship --reach    # re-check what answers
python -m etl.probe_apprenticeship --json     # both, machine-readable
```

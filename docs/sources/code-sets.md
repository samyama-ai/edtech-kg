# CIP, SOC, O\*NET and Career Clusters — surviving a code-set change

Q20 asks what happens when the crosswalk is revised. **edtech-kg#36** asked
about hierarchy, revisions and whether O\*NET-SOC is safe to join to SOC.
**edtech-kg#35** asked whether Career Clusters — the language US high schools
actually speak — is usable at all.

Every figure here comes from `python -m etl.probe_codesets`. The Career
Clusters section is a **reading of a licence**, not a measurement, and says so.

## The short answers

1. **The crosswalk carries hierarchy for 10 of its 49 families and not the
   other 39** — a mixture rather than an absence, which is worse than either.
   A uniform gap is easy to code around; this one answers for a fifth of the
   families and returns nothing for the rest.
2. **O\*NET-SOC aligns with SOC perfectly, and a naive join matches nothing.**
   That is the good failure. A partial match would have been the dangerous one.
3. **Career Clusters is "All rights reserved" and publishes no machine-readable
   crosswalk.** Not cleared for use.

## 1 · Hierarchy — a mixture, not an absence

edtech-kg#36 says `probe_cipsoc.py` "sees only leaves". Measured, it is a
mixture:

| | |
|---|---:|
| CIP codes in the crosswalk | **2,143** |
| — 6-digit leaves | 2,116 |
| — 4-digit series rows | 17 |
| — 2-digit family rows | 10 |
| Distinct 2-digit families | **49** |
| — with a family-level row | 10 |
| — **without one** | **39** |

A uniform absence would be easy to code around. This is not uniform: look up a
family's own row and you get an answer for ten of the forty-nine and nothing
for the rest. That is the kind of gap that produces a plausible partial result.

**Is the hierarchy derivable from the code string?** The *code* is — `11.0701`
is in family `11` and series `11.07`, by construction. The *name* is not. For
the 39 families with no rollup row there is no title anywhere in the file, so
"which family of programmes" cannot be answered in words without the separate
NCES hierarchy file.

That confirms edtech-kg#36's parenthetical — it needs the file — and gives the
reason: not because the codes are opaque, but because the labels are missing.

## 2 · O\*NET-SOC is not SOC, and that is safe

O\*NET publishes its own occupation taxonomy with codes that look like SOC
codes and are not. This is what edtech-kg#36 called "a real and silent source
of error".

| | |
|---|---:|
| O\*NET-SOC 2019 occupations | **1,016** |
| SOC codes they roll up to | **867** |
| SOC codes our crosswalk carries | **867** |
| In O\*NET and not ours | **0** |
| In ours and not O\*NET | **0** |
| **Naive string-equality matches** | **0 of 1,016** |

Two things fall out of that, and they point opposite ways.

**The taxonomies align exactly.** 867 and 867, with nothing on either side.
Once the suffix is handled, every O\*NET occupation reaches a SOC code this
graph already knows.

**And a naive join matches nothing at all.** Every O\*NET code carries a `.NN`
suffix — `11-1011.00` against SOC's `11-1011` — so string equality returns zero
rows rather than some wrong ones. **That is the safe failure**: a join that
silently matched 60% would have produced a figure nobody could reproduce. This
one fails loudly on the first query.

**The join is one-to-many.** 76 SOC codes carry more than one O\*NET
occupation, the largest carrying ten:

    15-1299  Computer Occupations, All Other  ->  10 O*NET occupations
                                                  (Web Administrators,
                                                   GIS Technologists, …)

So any future `Occupation` node populated from O\*NET must decide whether it is
a SOC occupation or an O\*NET one. They are not the same grain, and averaging
O\*NET attributes up to a SOC code is a modelling choice, not a lookup.

## 3 · Career Clusters — not cleared

Read from <https://careertech.org/career-clusters/>, on the retrieval date in
the probe output.

| | |
|---|---|
| Structure | **14 Clusters, 72 Sub-Clusters** — as edtech-kg#35 states |
| Copyright notice | **© 2023 Advance CTE: State Leaders Connecting Learning to Work. All rights reserved.** |
| Data files on the framework page | **0** |
| Data files on the **crosswalks** page | **0** |
| PDFs published there instead | **6** |

The framework page describes crosswalks "between the modernized Framework, the
original Framework, and national labor market data". Both pages are fetched and
counted separately, because the sentence that corroborates the zero is about the
crosswalks page and the two are not the same document.

The six files actually published on the crosswalks page are all PDFs, and the
probe names them rather than describing them: a cluster grid, the Clusters
Wheel and its key, a Spanish wheel and legend, and a **Brand Book**. No CIP, SOC
or NAICS crosswalk is published as data on either page.

The **0** is a count of links matching a data-file extension (`.xlsx`, `.xls`,
`.csv`, `.json`) on the two pages named above — not an exhaustive audit of the
site. It is stated that narrowly because the zero is what the licence position
rests on, and there are two ways a zero can be wrong. A pattern that is too
strict misses a link that is there; a page that did not load has no links at
all. Both would read as "no data files published".

The first is handled by matching either quote style and allowing a query
string after the extension. The second is refused outright: the probe stops if
the page carries **neither** the copyright notice **nor** the "14 Clusters and
72 Sub-Clusters" line, so a redirect, a cookie wall or a script shell — which
carry neither — halts the run instead of producing a zero that reads like a
finding.

Neither, not either. Advance CTE can reword a copyright line or restate the
cluster count without the page having failed to load, and refusing on one
missing landmark would turn an ordinary edit into a broken probe. Losing the
reading is a cost too; this refuses the failure and not the page.

The zero in the table above is a page that loaded and has no data files on it.

The prose is the third corroboration: the files that *are* published were read,
and they are PDFs.

That combination answers edtech-kg#35's question without needing a lawyer:
a trademarked framework, "all rights reserved", distributed as branded PDFs.

**Recorded as NOT cleared, read 2026-08-27.** edtech-kg#35 asked for a licence
position in writing with a date, and this is it: nothing on the site grants
reuse, and the copyright notice withholds it. The date is the reading's, not the
notice's — the notice says 2023 — and it is here rather than only in the probe
output because a position taken in writing has to carry the day it was taken.
Using Career Clusters requires asking Advance CTE — the same route as the
Urban Institute and O\*NET licence questions in
edtech-kg#13 and edtech-kg#14.

**This matters more than it looks.** CIP is not the language a high school
speaks; Career Clusters is. A course-planning product that cannot say "Health
Science" is speaking a vocabulary its users do not. The blocker is permission,
not data.

## What this means for the schema

- **Do not model CIP or SOC hierarchy from the crosswalk alone.** It carries
  ten families of forty-nine. Either fetch the NCES and BLS hierarchy files or
  derive the codes and leave the names empty — but do not let a lookup return
  a partial answer that reads as complete.
- **Never join O\*NET to SOC by string equality.** Strip the `.NN` suffix
  first. The alignment is perfect once you do.
- **Decide the grain before loading O\*NET.** 1,016 occupations against 867 SOC
  codes is a real one-to-many, not a rounding difference.
- **Career Clusters stays out** until permission exists.

## What was not established

- **The revision crosswalks** — CIP2010→CIP2020 and SOC2010→SOC2018 exist and
  were not measured here. The question "did this programme change or was it
  renumbered" is still open, and it is the one Q20 turns on.
- **How many CIP codes actually move between revisions.** Same reason.
- **Whether Advance CTE would grant permission.** Not asked. That is an email,
  not a probe.

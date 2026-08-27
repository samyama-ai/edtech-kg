# CIP, SOC, O\*NET and Career Clusters — surviving a code-set change

Q20 asks what happens when the crosswalk is revised. **edtech-kg#36** asked
about hierarchy, revisions and whether O\*NET-SOC is safe to join to SOC.
**edtech-kg#35** asked whether Career Clusters — the language US high schools
actually speak — is usable at all.

Every figure here comes from `python -m etl.probe_codesets`. The Career
Clusters section is a **reading of a licence**, not a measurement, and says so.

## The short answers

1. **The crosswalk carries almost no hierarchy** — and what it carries is
   inconsistent, which is worse than carrying none.
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
original Framework, and national labor market data". **Both pages are fetched**,
because the sentence that corroborates the zero is about the crosswalks page and
an earlier version of this probe read only the framework page — so the strongest
number here was counted somewhere other than where the prose pointed.

The six files actually published on the crosswalks page are all PDFs, and the
probe names them rather than describing them: a cluster grid, the Clusters
Wheel and its key, a Spanish wheel and legend, and a **Brand Book**. No CIP, SOC
or NAICS crosswalk is published as data on either page.

The **0** is a count of links matching a data-file extension (`.xlsx`, `.xls`,
`.csv`, `.json`) on the two pages named above, not an exhaustive audit of the
site. It is
stated that way because the zero is what the licence conclusion rests on, and a
pattern too strict would produce the same zero from a link it simply failed to
match — the wrong way round for a licence check. The prose above is the
corroboration: the files that *are* published were read, and they are PDFs.

That combination answers edtech-kg#35's question without needing a lawyer:
a trademarked framework, "all rights reserved", distributed as branded PDFs.

**Recorded as NOT cleared.** edtech-kg#35 asked for a licence position in
writing with a date, and this is it: nothing on the site grants reuse, and the
copyright notice withholds it. Using Career Clusters requires asking Advance
CTE — the same route as the Urban Institute and O\*NET licence questions in
edtech-kg#13 and #14.

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

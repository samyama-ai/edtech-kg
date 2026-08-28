# Statewide course directories — measured 2026-08-18

Issue #40 called this the highest-value unknown in the repo, and it is: one
state cleared would be worth hundreds of district scrapes and would change the
product from a per-district integration into a state-wide one.

**The answer is no**, on the evidence available. Statewide course directories
exist, two of the five checked are cleanly machine-readable, and **neither
carries prerequisites**. `docs/scope.md` §3 stands unchanged.

Two states measured is not fifty. What makes this more than a two-state sample
is the *reason* — set out below — which is structural rather than incidental.
That reason is an argument, not a measurement, and it is labelled as one.

---

## What was measured

| State | Machine-readable? | Records | Prerequisites field? | Notes |
|---|---|---:|---|---|
| **Texas** | ✅ CSV | **1,635** | **No** | TWEDS C022 SERVICE-ID table, direct download |
| **New York** | ✅ XLSX | **2,012** | **No** | Comprehensive Course Catalog, SCED-based, full descriptions |
| Florida | ✖ not parsed | — | not established | fldoe.org answered **403** on this run; CPALMS course search is a JavaScript app with no course API |
| Virginia | ✖ not parsed | — | not established | doe.virginia.gov answered **403** on this run |
| California | ✖ not parsed | — | not established | cde.ca.gov answered **303 in a redirect loop** on this run — see below; code sets are inside a manual-download workbook |

Two states measured, three not. Saying so rather than generalising from two.

**California is a firewall, not a redirect.** The 303 is what `urlopen` reports
after following the chain until it gives up; following it by hand takes 50 hops
and lands on `www6.cde.ca.gov/wafalert.html`, a web-application-firewall alert
page. So California is the same kind of finding as Florida and Virginia — an
automated request being turned away — rather than a page that has moved. The
probe records `redirect_loop: true` for it, which is the distinction #50 turns
on: a blocked fetch is not evidence that data does not exist.

**Those three statuses are re-fetched on every run, not remembered.** They were
a hardcoded constant in the first version of the script, which meant Florida
could have opened up and the table would still have printed `403` forever. #50
is now re-checkable by running the probe.

## Texas — the fields it actually has

`Code · Translation · Eligible for State HS Credit · Course Abbreviation · Course Units · CTE Course · Subject · Subject Area`

A course code list. Nothing about sequence, and nothing about what must come
first.

## New York — the strongest candidate, and still no

New York publishes the most complete thing of the five: **2,012 courses**, each
with a real description. The workbook has five sheets but the courses are on one
of them — `All courses`. The other four (`Change Tracker`, `New Courses`,
`Removed Courses`, `New Descriptions`) track what changed between editions, and
summing them would double-count every course that was merely revised. An earlier
draft of this page said "2,012 courses across five sheets", which was wrong about
where the number comes from even though the number was right.

The probe now refuses if no sheet named like `All courses` is present, rather
than falling back to whichever sheet happens to be first. Fields:

`Course Code (Course ID) · Course Code Description · Course Description ·
Course Level · Course Subject Area · CTE Indicator · AP Indicator · IB Indicator`

Searching **every string in the whole workbook** — 5,625 distinct values. The
terms are split, because they are not equally good evidence:

| term | occurrences | |
|---|---:|---|
| `prerequisite` | **0** | strong — counts toward the verdict |
| `pre-requisite` | 0 | strong |
| `must have completed` | 0 | strong |
| `before taking` | 0 | strong |
| `prior to` | 3 | weak — occurs in ordinary prose |
| `successful completion` | 1 | weak |

The split matters for more than tidiness. The first version of the script summed
all six and printed *"New York … prerequisite terms: 4"* while this page
concluded zero — a reader running the probe got the opposite answer from the one
the document asserts. The verdict now counts strong terms only, and the printed
table says so.

The four weak hits are course-description prose, not requirements — phrases of
the form *"…examining time periods from discovery or colonialism through World
War II"* and similar. None names a course that must come first.

Not "buried in the description". **Absent.**

## Why — and this is the part that matters

The pattern is structural rather than accidental, and understanding it stops
anyone re-running this search in six months.

**A state course code list exists for reporting and funding, not for course
planning.** Its job is to let every district describe a course the same way so
the state can count enrolments, fund programmes and check graduation credit. It
answers *"what is this course, for state purposes"*.

**A prerequisite is a local decision.** Whether Algebra 2 requires Algebra 1 at
a given school is set by that school or district — it varies by school within a
state, which is exactly why the state code list cannot carry it.

So the two are different artefacts, and the state one will never grow the field
we want. Prince William County has prerequisites *because it is a school
district publishing a catalogue for its own families*, not because Virginia
publishes anything.

## What this means for scope

**`docs/scope.md` §3 is unchanged and now better supported.** Course-level
prerequisites remain a per-district source. The one-district boundary is not a
gap in our research; it is a property of how US education data is published.

The follow-on question in **#19** — does a second district resolve as cleanly as
PWCS — becomes more important, not less. It is now the only route to knowing
whether this generalises.

## Three access findings worth recording separately

**Three fetches were blocked, which is not the same as three states resisting
access.** Florida and Virginia returned 403 to a plainly-identified request from
one machine on one afternoon; California's documentation page redirected.

CDNs bot-block routinely, and a different user-agent, a browser session or a
request to the department might well succeed. What is established is that a
naive automated fetch fails — not that the data is unreachable. #50 exists to
find out which.

**New York's catalogue is SCED-based.** That was the opening for #34 and #48,
and both are now answered in [`sced.md`](sced.md) — with a result that closes
the door rather than opening it. New York does key to SCED: 2,001 of its 2,012
courses carry a five-digit code. But **Prince William County publishes no SCED
code for any of its 791 courses**, so there is no join to make. Falling back to
matching on course titles reaches 8%, and reaches the wrong 8% — the AP and IB
courses that already had a national identity, not the local CTE programmes a
family cannot find anywhere else.

SCED is worth an optional `sced_code` property, populated where a district
publishes one. It is not worth a key.

**Texas has a `CTE Course` flag and a career-cluster structure.** That touches
#35 (Career Clusters), now answered in [`code-sets.md`](code-sets.md): the
framework itself is **"All rights reserved"** and publishes no machine-readable
crosswalk, so it is recorded as not cleared. Texas's own cluster structure is
different — a state publishing its own file — and remains a weaker but real and
downloadable link from a course to a career area.

---

## Reproducing

```bash
python -m etl.probe_state_courses          # the table above
python -m etl.probe_state_courses --json   # machine-readable, with timestamp
```

Every figure on this page comes from that script — the same standard as
`probe_education.py` and `probe_cipsoc.py`. Nothing is stored: the three states
that do not parse are fetched on every run and report whatever status the server
gives today.

It refuses rather than reporting a figure it cannot vouch for — an emptied
source, a workbook with no `All courses` sheet, a response that is not a zip,
or a Texas response missing the `Code` and `Translation` columns. That last one
matters because a maintenance page served with a 200 parses as CSV perfectly
well, and would otherwise be counted as courses.
A file that is reachable but corrupt exits under `source malformed` rather than
`refused`, because a broken download and an honest zero are different findings.

**Three corrections it produced**, all to this page:

1. **1,636 and 2,013 → 1,635 and 2,012.** Both counted the header row as a
   course.
2. **"2,012 courses across five sheets" → one sheet.** The count comes from
   `All courses`; the other four sheets track edition-to-edition changes.
3. **"prerequisite terms: 4" → 0.** The script summed strong and weak terms
   together, so its own output contradicted this page's conclusion.

That is the second time on this repo that writing the probe has corrected the
prose it was meant to confirm, and the first time it did so three times over.

Measured 2026-08-18T10:47:12+00:00.

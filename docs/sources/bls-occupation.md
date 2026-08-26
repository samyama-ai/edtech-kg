# BLS occupational projections — measured 2026-08-20

#37 asked whether a federal source can carry pay, outlook and entry education,
so that three questions do not rest on O\*NET while its terms are unconfirmed
(#14).

**Yes.** One table, public domain, carries all of it — and it covers **96.3% of
the occupations a programme can reach**.

Every figure below is printed by `python -m etl.probe_bls`.

---

## What it carries

`data.bls.gov/projections/occupationProj`, **832 detailed occupations**, one row
each:

| Field | Present |
|---|---:|
| Employment 2024 | 832 — 100% |
| Employment 2034 | 832 — 100% |
| Employment change | 832 — 100% |
| Employment percent change | 832 — 100% |
| Occupational openings, annual average | 832 — 100% |
| Median annual wage 2024 | 832 — 100% |
| **Education, work experience and training** | **832 — 100%** |

No field is patchy. Every occupation BLS projects carries every one of them.

That last row is the one worth noticing: **BLS assigns its own typical
entry-level education per occupation.** That is Q85 — *"which occupations pay
above median but need only a certificate or associate degree"* — from a single
federal table, with no licence question attached.

## Coverage against what this graph can reach

A national table of 832 rows is not the same as covering the occupations a
programme leads to. The denominator that matters is the crosswalk:

| | |
|---|---:|
| Reachable from a programme | **867** |
| Carried by BLS directly | **820** — 94.6% |
| **Answerable one way or another** | **835 — 96.3%** |

**867.** The crosswalk once reported 868, because that count included
`99-9999` — its own explicit *NO MATCH* sentinel, the code it uses for a
programme that maps to no occupation. It is not an occupation and cannot be an
answer, so this probe excluded it and the two pages disagreed by one for a
while. Settled in **edtech-kg#70**: the crosswalk probe now excludes the
sentinel as well, and reports it separately rather than dropping it. Both pages
say 867.

### The 47 not carried are three different facts

Reporting one number would make a structural exclusion look like a data gap:

| | | |
|---|---:|---|
| **Military occupations** | 19 | BLS does not project major group 55 at all |
| **Carried only at the broad level** | 15 | e.g. `13-1021` is absent but `13-1020` is present — the answer exists, coarser |
| **Absent outright** | **13** | the only real gap |

Here are the thirteen, because a reader should be able to see which occupations
we cannot answer for without re-running anything:

```
21-1011  21-1014  25-2055  25-2056  25-9042  25-9043  25-9049
51-2022  51-2023  53-1042  53-1043  53-1044  53-1049
```

Printed by the probe under **absent outright, in full**, and repeated as
`missing_outright` in `--json`. They cluster in community and social service
(`21-`), education (`25-`), production (`51-`) and transportation (`53-`).
Absent means absent at every level: the broad-parent test has already run on
these, so `53-1040` is not published either — otherwise `53-1042` would sit in
the row above.

## SOC vintage — the thing that would break the join silently

The crosswalk file is `CIP2020_SOC2018_Crosswalk.xlsx`; the 2024–34 projections
use the same **SOC 2018** vintage. So the join is code-to-code with no
translation.

This mattered enough to check because a vintage mismatch does not raise an
error — it produces *numbers*, just wrong ones, by matching codes that mean
different occupations in different editions. #36 owned keeping this true as the
code sets revise; [`code-sets.md`](code-sets.md) now records what was measured.

Two findings there bear on this page. **O\*NET-SOC is not SOC** — every O\*NET
code carries a `.NN` suffix, so a naive join matches nothing at all rather than
matching some wrong ones, which is the safe failure. And once the suffix is
stripped the two taxonomies align exactly: the same 867 codes, with none on
either side. The revision crosswalks themselves are still unmeasured.

## Openings are national only

The projections table publishes **one openings figure per occupation, for the
United States**. There is no state or metro breakdown of openings.

That bears directly on how honestly Q86 can be answered. A supply-versus-openings
comparison is already a stretched claim at national level — completions and
openings are two independently collected series. Built from national openings and
local completions it would be worse, and the answer must not imply local demand.

## OEWS — wages by geography, and nothing else

**May 2025 release** — the newest published, found by the probe rather than
written down here.

| | Status | Size |
|---|---|---|
| National | 200 | 0.3 MB |
| State | 200 | 7.6 MB |
| Metropolitan | 200 | 39.9 MB |

Stating the vintage matters because the projections beside it are 2024–34 with a
2024 median wage. Mixing the two without saying so would put a 2025 local wage
next to a 2024 national one and imply they are the same vintage — the same class
of silent mismatch as the SOC vintage above.

### The release is searched for, and here is why that is not fussiness

The first version of this page said **May 2023**, hard-coded as `oesm23*.zip` in
the probe. That was two releases stale, and it had every appearance of being
measured — the sizes beside it were real, fetched from live headers.

The obvious guard — bump the year, see a 404 — does not work:

> **`www.bls.gov` answers a request for a file that does not exist with `200` and
> an HTML page**, not a 404. `HEAD` on `oesm26nat.zip` returns `200` with
> `content-type: text/html` and no `content-length`. `oesm25nat.zip` returns
> `200`, `application/x-zip-compressed`, 279,525 bytes.

So a status check alone would have reported next year's unpublished release as
available, with a blank size column that reads as a formatting glitch. The probe
counts back from the current year and accepts a release only when **every**
geography in it is served as a zip — content type, not status. A half-published
year is not reported as current with a geography quietly missing.

This is the third variant of the same defect on this page: a claim that looks
measured because something nearby was measured. See the User-Agent section below
for the other two.

OEWS answers *"what does it pay near me"* down to metro area. It carries **no
projections and no education assignment** — those live only in the projections
table, nationally. So "what does it pay" localises; "is it growing" does not.

Sizes are read from response headers rather than by downloading; the question
here is which geographies exist.

## What O\*NET would still be needed for

This is the question #37 was really asking, and the answer shrinks #14 from a
blocker to a preference.

| | Source |
|---|---|
| Pay, outlook, openings, entry education | **BLS — public domain, settled here** |
| Wages by state and metro | **OEWS — public domain** |
| **Skills, abilities, work activities, work context** | **O\*NET only** |
| **Task statements, tools and technology** | **O\*NET only** |

So O\*NET is no longer required for any question currently marked answerable. It
would be required to add new ones — skill-based matching, "what would I actually
do all day" — which is a different and later conversation.

**#14 should be re-scoped**, not closed: the licence question stops blocking the
questions we have and starts gating questions we might want.

## Access — and a correction worth carrying

The probe fetches **one `www.bls.gov` page with eight different User-Agents**:

| User-Agent | Contact URL | |
|---|:---:|---|
| Ours — `edtech-kg research (+https://…)` | yes | **200** |
| A different name — `kg-source-survey (+https://…)` | yes | **200** |
| The browser string with `(+https://…)` appended | yes | **200** |
| `(+https://…)` alone, no product name at all | yes | **200** |
| `edtech-kg research` — same name, URL removed | no | 403 |
| A full modern browser string | no | 403 |
| urllib's default, `Python-urllib/3.x` | no | 403 |
| Empty string | no | 403 |

**The discriminator is a contact URL in the User-Agent — not identification in
general, and not automation.** The split is clean across all eight: every string
carrying a contact URL is served and every string without one is refused,
including a full browser string.

The bottom four rows are the ones that make this a finding rather than a guess.
An earlier version measured five agents — ours served, four others refused —
which is equally consistent with *"a contact URL is what matters"* and with
*"this exact string is allowlisted"*. One served sample cannot separate those.
So the last three added rows hold the contact URL constant and vary everything
around it: change the product name, keep the URL — served. Take the browser
string that was refused and append the URL — served. Send the URL with no
product name at all — served. Remove the URL from our own string — refused.

This sentence has now been wrong twice, which is why it is a matrix rather than
a yes/no. The first version named a field `unidentified_request` and sent the
identifying header anyway — it varied the host, not the header. The second sent
`headers={}` and called it anonymous, but **urllib supplies
`Python-urllib/3.x`**, so "no User-Agent" was never tested and the claim that a
short or absent one is refused was still unmeasured. Both read as findings.

It matters because this repo has drawn conclusions from 403s before. Re-tested
against that: **Florida still refuses our identified request** (#40, #50), so
that finding stands. But the general lesson is narrower than "a 403 means the
publisher blocks automation" — here it meant *this client did not say who to
contact*.

A third variant of the same defect is recorded under OEWS above: a hard-coded
release year that looked measured because the sizes beside it were. The shared
shape is worth naming — **a claim sitting next to a measurement is not itself
measured**, and on this page it has now happened three times.

---

**Method.** Every figure from:

```bash
python -m etl.probe_bls                # the tables above
python -m etl.probe_bls --json         # machine-readable, with timestamp
```

The table is parsed from the published HTML, whose tags are uppercase — a
lowercase-only pattern silently finds nothing, which is why the probe refuses
rather than reporting zero occupations if the heading is missing. The
all-occupations total row is excluded; counting it would inflate the denominator
and put a fictional occupation in the coverage set.

Coverage is measured against the SOC codes in the crosswalk file, read with the
same parser `probe_cipsoc` uses. If that file is not present locally the probe
says so rather than reporting zero coverage.

`tests/test_probe_bls.py` covers the parsing, the coverage arithmetic and the
three-way split; twelve mutations were tried against it and all twelve turn the
suite red.

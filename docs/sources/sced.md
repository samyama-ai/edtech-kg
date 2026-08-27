# SCED — the national course taxonomy

**School Courses for the Exchange of Data**, published by NCES through the
National Forum on Education Statistics. US government, public domain.

Every figure on this page comes from `python -m etl.probe_sced`. Nothing is
typed in.

Two issues asked about it and they are one question. **edtech-kg#34** asked what
SCED is and whether it carries a sequence field. **edtech-kg#48** asked whether
enough states align to it that a `Course` keyed on SCED would be portable. SCED
is only worth a node if a real district's catalogue can reach it, so both are
answered by the same measurement.

## The short answer

**SCED defines a sequence element. Nobody publishes it. And the one district
this repo has loaded cannot reach SCED at all.**

## What SCED is

| | |
|---|---|
| Current version | **SCED 13.0** |
| Courses | **1,791** |
| Columns the master file publishes | Course Title · SCED Course Code · Course Description · Change Status |
| Elements a record may carry | **6** |
| Attributes it may also carry | **17** |
| Landing page | <https://nces.ed.gov/forum/sced.asp> |

The standard names far more than the master file publishes, and it draws its
own line between the two: six **elements** — the code, subject area, level,
grade span, Carnegie credit, and sequence — and seventeen **attributes**,
which is where Course Title and Course Description sit. That distinction is
read from the sheet's own banner rows rather than assembled here, because an
earlier version of this probe assembled it and got a right-looking total over
the wrong members.

Note the version: **13.0**, where edtech-kg#34 says 12. The issue was written
against the page as it stood and NCES has published a version since. The probe
reads the file rather than pinning a number, so the next release shows as a
changed figure instead of a stale constant.

A SCED code is five digits: the first two are the subject area, the rest
identify the course within it.

## The sequence element — and why it does not help

SCED's element list includes **Sequence of Course**, defined as:

> Where a specific course lies when it is part of a consecutive sequence of
> courses. This element should be interpreted as "part 'n' of 'm' parts."

That is worth reading twice, because the name invites the wrong conclusion.
**"Part n of m" is one course split across terms** — Algebra 1 taught over two
semesters is part 1 of 2. It is not a relationship between two different
courses, and it says nothing about what a student must pass first.

So a reader who hears "SCED has a sequence field" and concludes it solves the
prerequisite problem has been misled by the name. It does not. `docs/scope.md`
§3's conclusion — that no national machine-readable source carries prerequisites
— survives SCED intact.

And the master file does not publish the element at all. Its four columns are
above; sequence is not among them. It is a thing a district *may* record when
it reports its own data, not a thing the taxonomy ships.

## Does any state publish it?

New York's Comprehensive Course Catalog is the one SCED-keyed state directory
this repo has found — `docs/sources/state-course-directories.md` records the
five that were checked.

| | |
|---|---|
| Rows in the sheet | **2,012** |
| Distinct course codes | **2,012** |
| Five-digit SCED codes | **2,001** |
| New York extensions | **11** — `01003CC`, `03001L` and nine more |

The rows and the distinct codes are both given, and they agree here: 2,001 SCED
codes plus 11 extensions is 2,012. They are reported separately because the
table used to mix them — two lines counted rows and one counted distinct codes,
so it added up only because this file repeats no code.
| Publishes a sequence column | **No** |

The eleven extensions are New York adding to the taxonomy, not using it —
`01003CC` is a Common Core variant of SCED `01003`. Counting them as SCED
alignment would overstate it, so the probe separates them.

**New York publishes eight columns and none is a sequence.** The element exists
in the standard and is absent from the one state that keys to it.

## The measurement that decides it

A taxonomy nothing can join to is a document, not an identifier. So: how much
of a real district's catalogue can reach a SCED code?

| | |
|---|---|
| PWCS courses loaded | **791** |
| Publishing a SCED code | **0** |
| Reachable by name alone | **67 — 8%** |

**Prince William County publishes no SCED code for any course.** Not one. So
there is no join to New York's catalogue to be had; the 8% is what remains if
you fall back to matching on course titles, which is a guess rather than a key.

The 8% is also generous, deliberately. It is measured after stripping
programme markers — `AP`, `IB`, `AICE`, `honors` — and parenthetical
qualifiers, so `AICE Biology (AS Level)` gets its best chance against
`Biology`. A stricter comparison returns less: without the parenthetical rule
it was 58 rather than 67, and that difference is the measure of how much of the
match depends on being lenient.

### And the 8% is the wrong 8%

The courses that match are the ones that were already national:

    AP Biology · AP Calculus AB · IB Physics (SL) · AP U.S. History
    Concert Band · Accounting · Geometry · Trigonometry

The courses that do not are the ones a district is distinctive for:

    Greenhouse Plant Production & Management · Turfgrass Management
    Landscaping 1 · Landscaping 2 · Horticulture Sciences

That is the shape of the result. SCED reaches the courses that already had a
national identity — an AP exam, a standard maths sequence — and misses the
local CTE programmes, which are exactly the part of a catalogue that a family
cannot find anywhere else.

## What this means for the schema

**Do not key `Course` on SCED.** The key would be null for every course in the
only catalogue currently loaded.

What SCED is worth is a **second, optional identifier** — a `sced_code` property
that is populated where a district publishes one, and absent where it does not.
That makes a future join possible without pretending one exists today, and it
keeps `url` as the key that actually resolves.

The honest summary for `docs/scope.md`: SCED gives a national vocabulary for
naming a course. It does not give prerequisites, it does not give a usable
sequence, and it does not give this graph a join — because the district that is
loaded does not speak it.

## What was not established

- **How many states publish a SCED-aligned course list.** Five were checked in
  edtech-kg#40 and one is SCED-keyed; three of the five block automated access
  (edtech-kg#50), so the denominator is unknown rather than small.
- **Whether a district's own codes map cleanly to SCED, or approximately.**
  PWCS publishes none, so there was nothing to compare.
- **Whether SCED versions drift between states.** One state is not a sample.

# IPEDS enrolment — the students are counted, the programme is not

Answering edtech-kg#204, split out of #8's question 4: *"which programmes have
the widest gap between who enrols and who completes?"*

**The question cannot be answered from this source, and not because a loader is
missing. Completions are published by programme. Enrolment is not published by
programme anywhere in the API — so the two sides have no key to join on.**

That is a legitimate answer to a research issue, and it is the one #204
anticipated: *"IPEDS enrolment is by institution and year, not by CIP
programme... that measurement alone might close this issue."*

Every figure below is printed by `python -m etl.probe_enrolment` and committed as
[`enrolment-measured.json`](enrolment-measured.json). Nothing is typed.

---

## What each side carries

| endpoint | rows (2022) | programme key |
|---|---:|---|
| `fall-enrollment` (race/sex) | 523,520 | none |
| `fall-enrollment` (age/sex) | 252,504 | none |
| `fall-enrollment` (residence) | 142,718 | none |
| `enrollment-full-time-equivalent` | 5,959 | none |
| `admissions-enrollment` | 8,686 | none |
| `enrollment-headcount` | no rows for 2022 | none |
| **`completions-cip-6`** | **9,026,310** | **`cipcode_6digit`** |

The volume was never the problem. `fall-enrollment` returns half a million rows
for one year — it is a rich dataset, cut by class level, degree-seeking status,
full- or part-time, race, sex and residence:

```
class_level, degree_seeking, enrollment_fall, fips, ftpt,
level_of_study, race, sex, unitid, year
```

Every one of those is a fact about *a student*. None is a fact about *what they
are studying*. The finest grain available is one institution in one year, and
the question needs one programme in one year.

## The negative claim, made from the whole catalogue

"No enrolment endpoint is by programme" is worth little if it rests on the six
endpoints someone thought to try. The probe reads the published endpoint list
and reports every path in the API carrying `cip`:

```
/api/v1/college-university/ipeds/completions-cip-2/{year}/
/api/v1/college-university/ipeds/completions-cip-6/{year}/
/api/v1/college-university/ipeds/program-year-tuition-cip/{year}/
/api/v1/schools/crdc/discipline-instances/{year}/
/api/v1/schools/crdc/discipline/{year}/disability/lep/sex/
/api/v1/schools/crdc/discipline/{year}/disability/race/sex/
/api/v1/schools/crdc/discipline/{year}/disability/sex/
/api/v1/schools/crdc/sat-act-participation/{year}/disability/sex/
/api/v1/schools/crdc/sat-act-participation/{year}/lep/sex/
/api/v1/schools/crdc/sat-act-participation/{year}/race/sex/
```

Ten paths. Six are CRDC — K-12 discipline and SAT participation, a different
universe entirely. Of the three at college level, two are the same completions
dataset at different CIP widths, and the third is **tuition** by programme.

So the API knows what a programme is. It attaches programmes to awards and to
prices. It never attaches them to enrolment.

## What this means for a reader of #8

#8 shipped four of five questions. This documents why the fifth did not, in a
form a reader can check rather than take on trust.

It also settles the shape of any future attempt. The three-step plan in #204 —
probe, download, loader — would have spent its second and third steps building a
join that cannot exist. The probe was the right first step, and it is the only
step worth taking against this source.

## If someone picks this up anyway

Three routes, none of them a loader against this API:

**Accept a coarser question.** Enrolment and completions both carry `unitid`, so
"which *institutions* have the widest gap between who enrols and who completes"
is answerable today. It is a different question — it cannot name a programme —
but it is a real one and the data is already loaded on one side.

**Find a source that publishes enrolment by programme.** Some state systems do.
That is a new source with its own licence check, not an extension of this one.

**Close it.** "Cannot be answered from this source" is a finding, and this repo
records that kind elsewhere — see [`texas-cte.md`](texas-cte.md), where a career
cluster that was expected to join to CIP turned out not to exist either.

## Re-running it

```bash
python -m etl.probe_enrolment            # print
python -m etl.probe_enrolment --record   # rewrite the record
python -m etl.probe_enrolment --year 2020
```

It downloads nothing and needs no key: one request per endpoint with `limit=1`,
because the fields are the finding and a single row carries them.

One behaviour worth knowing if you change it. `enrollment-full-time-equivalent`
returns **zero rows for `level_of_study=99`** and 5,959 for levels 1, 2 and 3.
Asked only at 99 — the level the other endpoints accept — it looks like an empty
dataset, and the table above would have carried a false "no rows" against a
populated source. The probe tries each level before reporting emptiness, which is
why `enrollment-headcount` above can be trusted when it says no rows for 2022.

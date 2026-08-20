# College Scorecard earnings — measured 2026-08-20

#21 asked what the earnings figures actually cover, before any question answers
with them.

**The caveat we recorded is right, and it is one of three.** The other two were
not written down, and one of them pushes the number up.

Every figure below is printed by `python -m etl.probe_scorecard`.

---

## Who is counted

Quoted from the publisher's own glossary rather than paraphrased:

> *"The median annual earnings of individuals who **received federal financial
> aid** during their studies and completed an award at the indicated field of
> study. To be included in the median earnings calculation, the individuals
> needed to be **working and not be enrolled in school** during the year when
> earnings are measured. Median earnings are measured in the **fourth full year**
> after the student completed their award."*

Three filters, not one:

| Filter | Effect on the number |
|---|---|
| **Federal aid recipients only** | The cohort is not all graduates. Already recorded in `scope.md` |
| **Working, and not enrolled** | **Excludes the unemployed and anyone who went on to further study — this raises the median** |
| **Fourth full year after completion** | Not a starting salary. Four years of career progression are in it |

The second is the one worth stating loudest. A median that excludes people who
are not working is not "what graduates earn" — it is *what employed graduates
earn*, and the difference is largest exactly where employment is weakest.

The cohort is the 2017–18 and 2018–19 award years pooled, measured in calendar
2022 and 2023, inflation-adjusted to 2024 dollars.

## How often a figure is actually there

227,980 rows — institution × programme × credential level — across **6,128
institutions** and **2,777 programme-and-level combinations**.

| Field | Published | | Suppressed |
|---|---:|---:|---:|
| `EARN_MDN_1YR` | 52,226 | 22.9% | 156,343 |
| `EARN_MDN_HI_2YR` | 55,871 | 24.5% | 134,566 |
| `EARN_NE_MDN_3YR` | 43,645 | 19.1% | 153,377 |
| **`EARN_MDN_4YR`** | **58,112** | **25.5%** | 169,868 |
| `EARN_MDN_5YR` | 50,512 | 22.2% | 158,057 |

**Three quarters of programme rows carry no earnings figure at all.** Most are
privacy-suppressed — too few completers to publish without identifying them —
rather than missing.

That is a property of the unit, not a defect: a programme at one institution
often graduates a handful of people. It means an earnings answer is available
for about one programme-at-an-institution in four, and the graph must say so
rather than return nothing and imply zero.

## The coverage gap falls where it hurts most

At the four-year horizon, by credential level:

| | Level | Published | Share |
|---|---|---:|---:|
| 1 | Undergraduate certificate or diploma | 8,163 / 43,465 | **18.8%** |
| 2 | Associate's degree | 9,280 / 42,373 | **21.9%** |
| 3 | Bachelor's degree | 27,617 / 71,664 | **38.5%** |
| 4 | Post-baccalaureate certificate | 118 / 1,249 | 9.4% |
| 5 | Master's degree | 10,403 / 38,621 | 26.9% |
| 6 | Doctoral degree | 1,150 / 12,637 | 9.1% |
| 7 | First professional degree | 737 / 2,350 | 31.4% |
| 8 | Graduate/professional certificate | 448 / 13,921 | 3.2% |
| 99 | Non-credential (preparatory) programme | 196 / 1,700 | 11.5% |

**The bachelor's degree is the best-covered credential, at 38.5%. Certificates
and associate degrees are half that.**

That is the finding this issue produces. `docs/questions.md` Q85 asks *"which
occupations pay above median but need only a certificate or associate degree"* —
described there as *"probably the single most useful answer in this whole list
for a student who cannot afford four years."* Those are precisely the credentials
Scorecard covers worst.

It does not block the question — BLS carries entry-education and pay for 96% of
reachable occupations (`bls-occupation.md`), which is a different route to the
same answer. But **the institution-level "what will I earn from this specific
programme" version of it is thin exactly where it matters**, and an answer that
does not say so is misleading.

## The caveat that must travel with an answer

> Earnings are the median for students who received federal financial aid, who
> were working and not enrolled in further study, four years after completing.
> They exclude the unemployed, so they are higher than the median for all
> graduates. A figure is published for about a quarter of programmes; the rest
> are withheld to protect small cohorts.

Shorter, where space is tight:

> Median for aided, employed completers, four years out. Not all graduates.

## What is not measured here

- **The institution-level file.** This page measures the field-of-study file,
  which is the programme-level one and the one a pathways question needs.
  Institution-wide earnings are a separate file and a coarser answer (#43).
- **Whether suppression correlates with programme type** beyond credential
  level. The level split is measured; a finer cut is not, and would change how
  the caveat is worded if it turned out to be systematic.
- **The API.** There is one, and it is documented; this uses the bulk file
  because the question is about coverage, and coverage is a whole-file question.

---

**Method.** Every figure from:

```bash
python -m etl.probe_scorecard --download   # ~17 MB, gitignored
python -m etl.probe_scorecard              # the tables above
python -m etl.probe_scorecard --json       # machine-readable, with timestamp
```

**The download link is discovered, not hardcoded.** The published URL carries
its release date — `Most-Recent-Cohorts-Field-of-Study_06102026.zip` — so a
pinned link would 404 on the next publication and read as a source problem
rather than a rename.

Two markers had to be measured rather than assumed: `PS` for privacy-suppressed
and `NA` for not applicable. Neither is blank, so a first pass testing for
emptiness reported **100% coverage** of a field that is three-quarters
suppressed. The share is taken over all rows, not over the ones that carry a
value, for the same reason.

Credential level names come from the file's own `CREDDESC` column. Naming them
in the probe produced a table claiming the bachelor's degree had 1,249 rows —
wrong, and plausible enough to have shipped.

`tests/test_probe_scorecard.py` covers the markers, the discovered link and the
cohort reading; eight mutations were tried against it and all eight turn the
suite red.

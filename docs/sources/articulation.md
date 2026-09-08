# Credit that carries: an institution-level yes, a course-level no

**Every figure here was printed by `python -m etl.probe_articulation`.** The
record is `articulation-measured.json`; `tests/test_articulation_doc.py` fails
if this page and that record disagree, in either direction.

    python -m etl.probe_articulation --record

Reads the Urban Institute Education Data API, already cleared under ODC-By in
[`education-data.md`](education-data.md). No new source and no new licence
question.

## The question

edtech-kg#42: the graph has two tiers that do not touch — high-school courses
on one side, CIP and IPEDS programmes on the other — and the bridge is
**credit that carries**. The issue expects no national source and says a no is
worth as much as a yes.

**It is not a flat no, and the difference is granularity.**

## At institution level the data exists, nationally and completely

IPEDS 2022 publishes credit-granting flags on every one of its
**6,138 institutions**:

| flag | grants | does not | share of those answering |
|---|---:|---:|---:|
| `ap_credit` | 3,240 | 2,810 | **53.6%** |
| `dual_credit` | 2,935 | 3,115 | **48.5%** |
| `credit_for_life` | 2,168 | 3,882 | **35.8%** |
| `military_training_credit` | 2,892 | 3,158 | **47.8%** |

These are properties of a node this graph already has. `Institution` is
declared, IPEDS is the source it is keyed on, and nothing has to be joined to
anything to use them.

## At course level nothing does

**0 of the 129 endpoints** the API
publishes mention articulation, credit acceptance, course equivalence,
transfer credit or credit by exam — searched for
`articulat`, `credit accept`, `course equivalen`, `transfer credit`, `credit by exam`.

The three endpoints that come closest are demographic counts:

| endpoint | rows | keyed on | names an institution | names a credit amount |
|---|---:|---|---|---|
| `dual_enrollment` | 2,343,168 | crdc_id, disability, fips, leaid, lep | **no** | **no** |
| `ap_ib_enrollment` | 2,343,168 | crdc_id, disability, fips, leaid, lep | **no** | **no** |
| `offerings` | 97,632 | crdc_id, fips, leaid, ncessch, year | **no** | **no** |

`dual_enrollment` and `ap_ib_enrollment` carry **2,343,168
rows each** and answer *how many students* — broken down by race, sex,
disability and English-learner status. `offerings` names courses
(`ap_courses_indicator` and four more) but only as counts
and indicators at a school.

**Not one of the three names an institution, and not one names a credit
amount.** So there is no row anywhere in this API that says *this course earns
this much credit at that college* — which is the edge the issue is asking for.

## What that means for the graph

The two tiers can be joined by a claim about an **institution** and not by a
claim about a **course**, and those support different questions.

- **Answerable now:** "of the colleges this programme leads to, which grant
  credit for AP?" — a property lookup on a node already declared, at national
  coverage.
- **Not answerable from national data:** "does *this* high-school course earn
  credit at *that* college?" — which is what a shortest-route calculation with
  time and cost in it needs.

So **Q4 should be re-rated in [`questions.md`](../questions.md)** rather than
left implying a route nobody can compute — which is what the issue asks for if
the answer is no, and the answer is no at the granularity Q4 needs.

## What this does not establish

One API. It says nothing about state articulation databases published
separately — California's ASSIST is the mature example and answered HTTP 400
to two documented endpoints on 2026-09-08, so whether it is reachable
as data is untested here rather than settled. It says nothing about per-college
AP policy pages, which are published as prose per institution and would be a
different kind of source entirely.

What it settles is the question as asked of the national data this repo
already reads: **the institution-level flag is there and the course-level edge
is not.**

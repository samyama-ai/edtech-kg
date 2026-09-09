# The progression rules are captured as flags; the substance is prose

**Every figure here was printed by `python -m etl.probe_progression_rules`.**
The record is `progression-rules-measured.json`;
`tests/test_progression_rules_doc.py` fails if this page and that record
disagree, in either direction.

    python -m etl.probe_progression_rules --record

## The shape

edtech-kg#66 clusters four blocked questions that share one:

| | question | the rule that would answer it |
|---|---|---|
| **Q39** | which courses satisfy this programme's entry requirement? | a college's admission prerequisites |
| **Q57** | a state changes graduation requirements — which courses become mandatory? | a state's graduation policy |
| **Q58** | an accreditation lapses — what is affected? | an accreditor's scope |
| **Q93** | which pathways cross from secondary into post-secondary? | articulation agreements |

The issue's claim is that every one of these rules exists, is public, and is
written as prose. **It holds — and the measurement sharpens it.**

## The national data does not omit these rules. It flags them.

IPEDS publishes admission requirements for **6,138
institutions** across **48 fields**, of which
**18 are requirement flags**. The flags fire:

| flag | institutions |
|---|---:|
| `reqt_college_prep` | 653 |
| `reqt_competencies` | 176 |
| `reqt_hs_record` | 1,733 |

**0 of the 48 fields name a
course.**

So the data knows that **653 institutions require
college-preparatory coursework** and does not say which coursework. That is
the pattern in a sentence, and it is worse for a graph than an absence would
be: **a flag looks loadable.** `Institution -[:REQUIRES]-> ???` has a subject,
a predicate and nothing to point at.

## Where the substance lives instead

| question | source | status | bytes | JSON | downloadable files |
|---|---|---:|---:|---|---:|
| Q57 | ecs | 403 | 0 | **no** | 0 |
| Q57 | nces | 200 | 60,710 | **no** | 0 |
| Q58 | dapip | 200 | 1,225 | **no** | 0 |

- **Q57.** The Education Commission of the States comparison — the one
  compilation that normalises fifty states — answers **403** to this client.
  NCES serves a page with **2
  HTML tables** and no downloadable file: a table a person reads.
- **Q58.** The federal accreditation database answers 200 with
  **1,225 bytes** — an
  application shell. The data is behind a browser.
- **Q93.** Measured under edtech-kg#42 and read from
  `articulation-measured.json` rather than re-measured: **0 of
  129 endpoints** name a course-level rule, while the
  same source carries institution-level flags —
  `ap_credit`, `credit_for_life`, `dual_credit`, `military_training_credit`.

**Four questions, four rules, and the same answer each time.** Every one is
captured at the level of "does this institution do X", and none at the level
of "which course".

## Why this is one finding and not four

The issue says the shape has appeared three times across two domains — the FDA
predicate device, competency levels, and now this. The measurement adds the
detail that makes it actionable:

**These are not missing datasets. They are datasets with the join stripped
out.** Every source measured here publishes the *existence* of a rule as a
tidy machine-readable flag and leaves the *content* — the course, the credit,
the equivalence — in a document. That is a consistent design decision by four
independent publishers, which is a fact about how US education data is
collected rather than a gap any one of them will close.

For the graph, it means Q39, Q57, Q58 and Q93 cannot be answered by loading
more sources. They need either a per-institution extraction from prose, or a
narrower question.

## What this does not establish

Four questions, four sources, on 2026-09-08. A **403** is a refusal to
*this* client — an account or an agreement might open ECS, and none was
sought.

It says nothing about whether the prose could be extracted. Every rule
measured here is published and readable; the finding is that none of them is
published as a join. Whether an extraction is worth building is a different
question from whether a source exists, and this page only answers the second.

Q93 is not re-measured here. Two probes measuring one fact is two figures that
can disagree, and this page would be quoting the other's conclusion either
way.

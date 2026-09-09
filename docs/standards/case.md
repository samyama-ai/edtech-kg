# CASE: the specification is real; the registry is not reachable as data

**Every figure here was printed by `python -m etl.probe_case`.** The record is
`case-measured.json`; `tests/test_case_doc.py` fails if this page and that
record disagree, in either direction.

    python -m etl.probe_case --record

## The question

edtech-kg#32: course titles do not survive crossing a district boundary;
standards might. 1EdTech's **CASE** is the specification for exchanging
learning standards in machine-readable form, and **CASE Network 2** is
advertised as hosting frameworks from all 50 US states, *"free to browse and
use"*.

The issue is explicit that this has to be measured: *"'available for anyone to
use' on a website is a statement of intent, not a licence — find the
licence."*

**There is no licence to find, because there is no data to licence.**

## Route 1 — CASE Network 2 is a browser application

| path | status | bytes | CASE JSON |
|---|---:|---:|---|
| `/ims/case/v1p0/CFDocuments` | 403 | 0 | **no** |
| `/uri/` | 403 | 0 | **no** |
| `/CFDocuments` | 200 | 3282 | **no** — the root markup |

The root answers **200** with 3282 bytes of a
single-page application. Every documented CASE path either refuses with
**403** or returns that same shell. **0 of
3 paths serve CASE JSON.**

"Machine-readable" describes the *format* the standards are stored in. It does
not describe the access, and the access is a browser.

## Route 2 — OpenSALT serves CASE, and holds a sandbox

The reference implementation answers **200** and returns real CASE
JSON: **95 documents from 39
creators**. But the creators are not state education agencies:

| creator | documents |
|---|---:|
| PCG Test Prep | 9 |
| ETS | 7 |
| Florida Report Card Project | 7 |
| PCG Copy | 6 |
| Gwinnett County Public Schools | 6 |
| Alabama Test | 5 |

*"PCG Test Prep"*, *"PCG Copy"* and *"Alabama Test"* are fixtures. This is a
working CASE endpoint holding demonstration data — which is what a reference
implementation is for, and is not fifty states.

**No document carries a licence field of any kind.** Checked as the CASE
v1p0 model spells it — `licenseUri` — and as three plausible alternatives:

| field | documents carrying it |
|---|---:|
| `licenseUri` | 0 |
| `licenceUri` | 0 |
| `rights` | 0 |
| `rightsHolder` | 0 |

The zero is checkable because the **whole key set is recorded**: across all
95 documents the server publishes
17 distinct keys, and licensing is not among them.

An earlier version of this page counted `licenceUri` — the British spelling,
which is in no version of the specification — so the zero was a property of
the key name rather than of OpenSALT, and the test could not catch it because
the fixture fed the same misspelling. The count agreed with itself. Recording
what the documents actually carry is what makes the claim checkable.

## Route 3 — CPALMS serves one document for every course

CPALMS is where the issue says to look for the edge that *"makes this useful
rather than merely present"* — a state publishing a **course → standard**
alignment.

**Three different course ids return byte-identical documents**, and none of
them contains its own id:

| course id | status | bytes | standard links | names its own id |
|---|---:|---:|---:|---|
| 13087 | 200 | 63,041 | 0 | **no** |
| 17414 | 200 | 63,041 | 0 | **no** |
| 20205 | 200 | 63,041 | 0 | **no** |

**1 distinct document for 3 course
ids.** So the missing alignment is not a separate fact — *the whole page is an
application shell*, the same shape as route 1. The server publishes no course
content at all, and a browser assembles it afterwards.

An earlier version of this page measured one course id and said Florida
*"publishes no alignment in its markup"*, inferring that a browser assembles
it. The inference was right and the measurement was too narrow to support it:
one page carrying no alignment is consistent with several explanations, and
three identical pages leave one.

## The verdict: standards do not become a node tier

`docs/questions.md` sets the rule — **a tier serving none of the 26 questions
stays out** — and standards do not clear it, for a reason simpler than
relevance: **the data is not obtainable.**

- The registry that claims fifty states is not an API.
- The API that works holds test fixtures.
- The state alignment that would make standards useful is rendered, not
  published.

Nothing here says the standards are absent. They are published, they are real,
and a person can read them. What is missing is a machine route to them, which
is the only kind this repo can load.

## What this does not establish

Three routes on 2026-09-09, 3 course pages at CPALMS, and one
reference server. A **403** is a refusal to *this* client — an account, an API
key or an agreement might open the registry, and none was sought. What is
settled is that **no unauthenticated machine route was found**, which is the
condition every other source in `docs/sources/` was cleared against.

Re-run the probe before treating this as durable: the registry was rebranded
"Standards Satchel" at some point before this measurement, and a host that
refuses today may serve tomorrow.

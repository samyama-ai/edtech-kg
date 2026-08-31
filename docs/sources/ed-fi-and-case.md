# Ed-Fi and CASE — the other two of the three

Answering edtech-kg#31 and edtech-kg#32. With the CEDS investigation —
edtech-kg#29, which lands on its own branch — these are the three #69 waits on
before #33's four provisional rows can be decided.

The CEDS column below is quoted from that measurement rather than linked to
it, because the file is not on `main` yet and a link would break whichever of
the two merges first.

Measured **2026-08-28** by `python -m etl.probe_vocabularies`, which writes
[`vocabularies-measured.json`](vocabularies-measured.json).

## The comparison, which is the point

| | CEDS | Ed-Fi DS 6.0 | CASE v1p0 |
|---|---|---|---|
| **Licence** | Apache-2.0 | Apache-2.0 | **use for products governed by a 1EdTech licence** |
| **Machine-readable** | RDF, 20 MB | OpenAPI YAML, 3.7 MB | JSON-LD context |
| **Citable term URIs** | yes, but opaque (`C200072`) | **none** | yes (`CFItem`) |
| `School` | `C200199` | `edFi_school` | — |
| `District` | `C200188` | `edFi_localEducationAgency` | — |
| `Course` | `C200072` | `edFi_course` | — |
| `Standard` / competency | `C200065` | `edFi_learningStandard` | `CFItem` |
| `Course ALIGNS_TO Standard` | `C200064` | — | `CFAssociation` |

## Ed-Fi is a shape, not a vocabulary

**622 `edFi_` schemas across 186 REST resource paths**, Apache-2.0, published
as OpenAPI. It defines all four school-system shapes.

**There is nothing to cite.** `edFi_school` is a schema name inside an OpenAPI
document — not a resolvable identifier, not a URI, not a term with a
definition at an address. A graph cannot say *"this node is an
`edFi_school`"* in any way a reader could follow.

That is #31's own title — *"a model to stay compatible with, not a feed to
load"* — now measured rather than assumed. Ed-Fi tells you what fields a
school record should carry. It does not give you a word for *school*.

Four data-standard versions are published side by side — 3.3, 4.0, 5.0 and
6.0. Compatibility with Ed-Fi therefore means compatibility with *a version*,
which is a commitment CEDS's stable identifiers do not ask for.

## CASE is a vocabulary, with a licence to read

**119 terms** in the published JSON-LD context, 27 of them datatype
declarations sitting beside their classes (`dtCFItem` beside `CFItem`).

It defines the competency side precisely — `CFDocument` for a standard set,
`CFItem` for a standard, `CFAssociation` for the alignment edge — which is the
one shape CEDS names awkwardly and Ed-Fi splits across resources.

But its own specification says:

> Use of this specification to develop products or services is governed by the
> license with 1EdTech found on the 1EdTech website

**That is not Apache-2.0 and it is not a Creative Commons licence.** CEDS and
Ed-Fi need no such reading; CASE does, and the answer is a licence agreement
rather than a public grant. The narrow permission the page *does* grant is for
using excerpts "in producing requests for proposals".

**This is a reading of published terms, not legal advice.** As with the
Credential Registry — see edtech-kg#56 — the remedy is asking rather than a
better reading. That page is not linked here because it lands on a separate
branch, and a document that cites a file `main` does not have is a broken link
the moment this merges first.

## What is not established

**That all 50 states publish their standards as CASE.** #32's title says
"already machine-readable", and this page does not confirm it. The
specification is published and implementations exist — OpenSALT answered — but
one state endpoint tried (`case.georgiastandards.org`) did not resolve, and a
census of fifty states is its own piece of work. **Nothing here supports a
count.**

**Whether anyone publishes Ed-Fi or CASE data we could read.** Same gap as
CEDS, and the same reason: #53's lesson is that a defined term and a populated
one are different facts.

## What this means for #69

All three have now reported, which is what #69 was waiting for. On the
evidence:

- **CEDS is the alignment target for the school-system side.** Apache-2.0,
  resolvable URIs, defines all four shapes. The cost is opaque identifiers.
- **Ed-Fi is a compatibility model, not a citation.** Its shape is worth
  matching; it cannot be aligned *to* in the sense #33 means.
- **CASE is the better model for the competency shape** and the only one whose
  licence is not a public grant. Adopting it is a decision with a licence
  attached, and that is a decision for a person.

Deciding the four rows and removing the word "provisional" is **#69's** work,
not this page's. `docs/ontology-reuse.md` is deliberately untouched.

## Re-measuring

```bash
python -m etl.probe_vocabularies              # the tables
python -m etl.probe_vocabularies --record     # refresh the committed record
python -m etl.probe_vocabularies --no-cache   # re-download the 3.7 MB
```

No test fetches. `edfi_resources`, `case_terms` and `case_licence` all take
their document text.

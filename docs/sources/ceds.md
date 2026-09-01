# CEDS — the federal vocabulary, and what aligning to it would cost

Answering edtech-kg#29. CEDS is the vocabulary this sector already speaks, and
#33's reuse decision left four rows **provisional** waiting on it.

Measured **2026-08-28** by `python -m etl.probe_ceds`, which writes
[`ceds-measured.json`](ceds-measured.json).

| | |
|---|---:|
| Source | [`CEDS-Ontology.rdf`](https://github.com/CEDStandards/CEDS-Ontology) |
| Size | **20,242,062 bytes** of RDF |
| Licence | **Apache-2.0** |
| Classes | **1,369** |
| Distinct labels | **1,369** |

## It is data, not a PDF

That is the first thing #69 asks and it is the one that decides whether
"align to CEDS" is a citation or a transcription job. CEDS publishes a real
OWL/RDF ontology on GitHub under Apache-2.0, alongside `CEDS-Elements`,
`CEDS-IDS` and `CEDS-Data-Warehouse`.

**Contrast with Career Clusters** ([`code-sets.md`](code-sets.md)), where the
crosswalks page publishes PDFs and no machine-readable file at all, and the
licence position could not be cleared. CEDS is the opposite case on both
counts.

## It defines every shape #33 left provisional

| our shape | CEDS class | identifier |
|---|---|---|
| `School` | K12 School | `C200199` |
| `District` | Local Education Agency | `C200188` |
| `Course` | Course | `C200072` |
| `Standard` / competency | Competency Definition | `C200065` |
| `Course ALIGNS_TO Standard` | Competency Definition Association | `C200064` |

None is missing. That is a stronger result than the CTDL investigation
produced, where the term existed and [nobody populated
it](credential-registry.md).

## The cost: every identifier is opaque

`Course` is **`C200072`**. Not `ceds:Course` — `C200072`.

The meaning lives in `rdfs:label`, not in the URI. A graph aligning to CEDS
cites `https://w3id.org/CEDStandards/terms/C200072` and has to carry the human
name separately, where CTDL gives `ceterms:Course` and schema.org gives
`schema:Course` — URIs a reader can check without a lookup.

**Labels are unique** — 1,369 distinct labels across 1,369 classes, measured
rather than assumed. So a label *is* a usable key, and the ambiguity that
would have made this much worse does not exist. But it is still a second
column to carry, and a label is not a stable identifier: it is the identifier
that CEDS promises not to change.

## What is not established here

**Whether anyone publishes CEDS.** #53's lesson was that CTDL defines a
perfect prerequisite edge and no publisher populates it, and the same question
has to be asked of anything before adopting it.

It is deliberately not answered by guessing. **CEDS is a reporting vocabulary
rather than a publishing one** — states map their data *to* CEDS for federal
reporting rather than publishing records *in* it — so "do publishers use it"
is not the same question it was for the Credential Registry, and answering it
needs a different measurement than counting envelopes.

## What this does not close

**#69 stays open.** Its own rule is that the four provisional rows are decided
only once #29, #31 *and* #32 report, and Ed-Fi and CASE have not. This page is
one of the three.

What it does establish, for those rows: **CEDS is adoptable** — licensed,
machine-readable, and it defines all four shapes. Whether it is the *best* of
the three is not decidable from one investigation, which is exactly why #33
required all three.

## Re-measuring

```bash
python -m etl.probe_ceds              # the tables
python -m etl.probe_ceds --record     # refresh the committed record
python -m etl.probe_ceds --no-cache   # re-download the 20 MB
```

Cached under `data/`, which is gitignored. No test downloads it: `classes()`,
`unique_labels()` and `shapes()` all take the RDF text.

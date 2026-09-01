# The Credential Registry's data is not openly licensed

Answering edtech-kg#56, which exists to stop a correct finding travelling one
step too far.

**#28 established that CTDL — the vocabulary — is CC BY 4.0**, quoted verbatim
in [`ctdl.md`](ctdl.md). That is clean and adoptable, and nothing here changes
it.

**The records in the Registry are a different question with a different
answer.** They are published by many organisations, and the operator's terms
do not open them.

Read on **2026-08-31** by `python -m etl.registry_licence`, which also writes
[`registry-licence-measured.json`](registry-licence-measured.json).

---

## Why the confusion is easy to fall into

credreg.net's footer is headed **"Policies and Terms of Use"** and states, two
lines later:

> Credential Transparency Description Language (CTDL) by Credential Engine is
> licensed under a Creative Commons Attribution 4.0 International License

A reader who stops there concludes the Registry is CC BY 4.0. The sentence is
about **CTDL**, and the footer's "Terms" links go to `/ctdl/terms`,
`/meta/terms` and `/qdata/terms` — which are listings of vocabulary *terms*,
not terms of use.

The actual terms of use are on a different domain:
<https://credentialengine.org/terms/>.

## What those terms say

Quoted, because the conclusion rests on the wording rather than on a reading
of it.

**The grant:**

> Credential Engine grants you a personal, limited, revocable, nonexclusive,
> and nontransferable license to view, access, and use the Websites and the
> Credential Registry, solely for your personal use and internal use within
> your organization

**The restriction:**

> You may not reproduce, publish, distribute, display, modify, create
> derivative works from, sell in any way, in whole or in part, or make
> commercial use of the Credential Registry or any content on the Websites
> without the separate prior consent of Credential Engine

**And for anything built on it:**

> develop software applications that access and use data from the Websites and
> the Credential Registry; or (ii) aggregate, publish, transmit or otherwise
> reproduce, transfer, distribute or disseminate data from the Websites and the
> Credential Registry to third parties, whether for commercial or noncommercial
> purposes; must in addition to these Terms of Use agree to and sign our
> Developer Agreement

Note **"whether for commercial or noncommercial purposes"**. Being a research
project is not an exemption on the face of this text.

## Can a publisher licence its own record more openly?

Not in practice, and barely in principle.

CTDL has **1,032 terms**. Searching them for *licence*, *copyright*, *rights*
or *terms* returns **five**, and four are not what they look like:

| term | what it actually is |
|---|---|
| `ceterms:License` | a **credential type** — a government authorisation to do a job, like a nursing licence. Not a data licence, and it is what a search for "license" finds first. |
| `ceterms:RightsAction` | an action asserting legal rights over a credential |
| `ceterms:rightSource` | the right-hand parameter of a constraint |
| `statementCat:TerminationTerms` | a statement category — the conditions under which an *agreement* ends |
| **`ceterms:copyrightHolder`** | the only one about rights in the resource: *"Person or organization holding the rights in copyright to this resource."* |

*Terms* has to stay in that search: a property called `termsOfUse` is exactly
what this question asks whether CTDL has. It does not have one.

And `copyrightHolder` names a holder, not a licence. It says who owns the
rights; it does not say what anyone else may do.

**Measured: 0 of 398 published records carry it**, read across four
resource types — courses, credentials, learning opportunity profiles and
pathways.

**How the sample was taken matters more than its size here**, so the record
states it per type and this page repeats it. The pages are **spread at a
stride** across each result set rather than read off the front:

| type | how it was sampled |
|---|---|
| Course | 2 pages of 50 at a stride of 479, reaching pages 1–480 of 958 (47,862 records) |
| Credential | 2 pages of 50 at a stride of 1,334, reaching pages 1–1,335 of 2,669 (133,428 records) |
| Learning opportunity profile | 2 pages of 50 at a stride of 222, reaching pages 1–223 of 445 (22,247 records) |
| Pathway | every page — 98 records is the whole population, not a sample |

The stride is the point. Reading pages 1, 2 and 3 is not a sample of the
Registry, it is a sample of whatever sorts first — and one publisher's bulk
upload can dominate that. A head sample would turn *"no publisher populates
this field"* into *"this publisher does not"*, which is a far weaker claim
wearing the same number. The walk is deterministic rather than random, so the
figure reproduces.

So there is no per-record licence field to read, no publisher populating the
one adjacent field, and a blanket term of use that reserves everything.

## What this means for this repo

| | |
|---|---|
| CTDL, the vocabulary | **cleared** — CC BY 4.0 (#28) |
| Credential Registry data | **not cleared. Do not load.** |

Concretely, on the face of the published terms:

- **Loading Registry records into a published graph is not permitted** without
  a separate agreement. "Aggregate … or otherwise reproduce" covers it, and
  "noncommercial" is named rather than excused.
- **A sweep of every course (#58) is a software application that
  accesses and uses Registry data**, which the terms route through a signed
  Developer Agreement. #58 should not proceed on the assumption that it may.
- **Measurements already published in [`credential-registry.md`](credential-registry.md)
  are counts about the data, not reproductions of it.** That document was
  careful to record that the licence "was not established here", so nothing
  published so far rests on an assumption this contradicts.
- **The 398 records this page rests on were read under the same reading.**
  Reading a sample to find out what the terms say, and publishing a count
  rather than the records, is the same act as the paragraph above — and it is
  the act #58 would escalate into a sweep of every course, redistributed. The
  line this page draws is between reading to answer a question and
  aggregating to republish, not between reading and not reading.

**This is a reading of published terms, not legal advice**, and the remedy is
not a better reading — it is asking. Credential Engine publishes a Developer
Agreement for exactly this, and a signed one would change the answer. That is
a decision for a person, and it is why this row is `not cleared` rather than
`rejected`.

## Re-reading it

```bash
python -m etl.registry_licence            # the terms and the count
python -m etl.registry_licence --record   # refresh the committed record
```

`--record` stamps the run's own date, so refreshing it **fails the doc test
until the "Read on" line above is edited to match**. That is deliberate: it
forces the prose and the record to be updated together rather than letting the
page keep a date the measurement no longer has.

No test fetches. `terms_of_use`, `rights_terms_in` and
`carrying_a_rights_field` all take their input rather than going to get it.

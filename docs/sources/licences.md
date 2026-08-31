# O\*NET and the Urban Institute — the licence positions, quoted

Answering edtech-kg#13 and edtech-kg#14. Both ask the same thing of different
publishers: find the terms, **quote them rather than paraphrase**, and record
what attribution is owed.

Everything below is a span lifted out of the page named beside it, read on
**2026-08-31** by `python -m etl.probe_licences`. The same run writes
[`licences-measured.json`](licences-measured.json), which the tests check this
page against, so a quote here that drifts from the page is a test failure
rather than a discovery.

A licence position is **read**, not measured — the distinction
[`code-sets.md`](code-sets.md) draws. A wrong measurement is a wrong number. A
wrong licence position is a statement about what this project may lawfully
publish.

---

## O\*NET — and the exception nobody reads to

> Except as noted below, the content of the O\*NET 31.0 Database is licensed
> under a Creative Commons Attribution 4.0 International License

— <https://www.onetcenter.org/license_db.html>

That is the sentence everyone stops at, and stopping there is the mistake this
issue existed to catch. Four lines further down the same page:

> This license applies only to downloadable files on the following pages:
> O\*NET Database — Database Releases Archive — Spanish Language Resources

**The crosswalks page is not on that list.** The two workbooks this repo
actually reads are published there, not on any of those three:

- `Classfication of Instructional Programs (CIP)` — the publisher's spelling
- `Registered Apprenticeship Partners Information Data System (RAPIDS)`

So the Database licence does not cover the files we use. Citing it at them
would be citing a document that excludes them by name.

They are cleared, but by a notice of their own, on the page that publishes
them:

> Crosswalk Files by U.S. Department of Labor, Employment and Training
> Administration is licensed under a Creative Commons Attribution 4.0
> International License

— <https://www.onetcenter.org/crosswalks.html>

Same licence, different instrument. The answer to #14 is yes; the reason is
not the one the question assumed.

### The attribution, verbatim

O\*NET publishes the exact wording to reproduce, so it is reproduced rather
than rewritten:

> This page includes information from the O\*NET 31.0 Database by the U.S.
> Department of Labor, Employment and Training Administration (USDOL/ETA).
> Used under the CC BY 4.0 license. O\*NET® is a trademark of USDOL/ETA.

Three obligations travel with it, all stated on that page:

1. **The version number is part of the attribution.** O\*NET asks for
   `"O*NET 31.0 Database"`, not `"O*NET Database"`. Anything this repo
   publishes has to name the version it read.
2. **If we modify the data, we must say so** — their wording adds
   *"[Your name or company] has modified all or some of this information.
   USDOL/ETA has not approved, endorsed, or tested these modifications."*
   A graph that reshapes a crosswalk into nodes and edges has modified it.
3. **`O*NET®` is a trademark and must be used as an adjective** — "includes
   information from the O\*NET database", never "includes O\*NET".

---

## Urban Institute Education Data Portal

#13 exists because the underlying IPEDS and CCD data is US-government public
domain while the **wrapper** is not, and its terms had never been read.

> All data made available via the Education Data Portal in any form is
> licensed to you under the Open Data Commons Attribution License (ODC-By)
> v1.0

— <https://educationdata.urban.org/documentation/>

**Reuse: yes. Re-sharing: yes.** ODC-By is permissive and carries an
attribution condition, not a share-alike one. Nothing in it blocks publishing
counts, a loader, or a derived graph.

The portal asks for a specific citation, quoted here so it can be reproduced
exactly:

> [dataset names], Education Data Portal (Version ), Urban Institute, accessed
> Month, DD, YYYY, <https://educationdata.urban.org/documentation/>, made
> available under the ODC Attribution License

#13 also asks whether going direct to NCES would avoid a restrictive answer.
It would — the federal sources are public domain — but the answer is not
restrictive, so that is not a reason to go direct. edtech-kg#43 argues for
going direct on other grounds, and this finding neither supports nor weakens
it.

---

## What this changes

| Source | Position on 2026-08-31 | Status |
|---|---|---|
| O\*NET **Database** files | CC BY 4.0, version-bearing attribution | `cleared` — but we do not read these |
| O\*NET **crosswalk** workbooks | CC BY 4.0 by the crosswalks page's own notice | `cleared` — these are the ones we read |
| Urban Institute Education Data Portal | ODC-By v1.0, citation requested | `cleared` |

Both rows in [`../scope.md`](../scope.md) move off **"terms to confirm"** and
**"not yet checked"**.

Two of the seven scope rows were open questions. **One remains: the PWCS
catalogue**, whose reuse permission is a human decision rather than a
published licence. It is not cleared by anything on this page.

**Cleared is not discharged.** The three obligations above — the
version-bearing attribution, the declaration of modification, and adjectival
use of the trademark — are recorded here, and nothing in this repo emits them
yet. They fall due when something built from these files is published, which
is #36's work, not this page's.

## Re-reading it

Deliberately uncached. A licence position is exactly the thing that should be
re-read rather than served from a copy taken months ago:

```bash
python -m etl.probe_licences            # the positions, as prose
python -m etl.probe_licences --record   # refresh the committed record
```

No test makes those requests. Every reader in `etl/licence_positions.py` takes
page text rather than a URL, so the suite hands it fixtures and the pages are
fetched only when a person asks for it.

`--record` stamps `retrieved_at` with the day it runs, while the dates written
into the prose above are maintained by hand. Refreshing the record therefore
turns `test_the_record_names_the_date_it_was_read` red until the sentences are
updated to match. That coupling is deliberate — a re-read that quietly left
stale dates in the prose is the failure this page exists to prevent — but it
is a red suite, not a broken one.

# Contributing

Short on purpose, and it stands alone — everything a PR here has to satisfy is
below. The twelve failure classes these rules were distilled from live outside
the repo; ask a maintainer if you want the long form.

## One issue, one branch, one PR

Never bundled. If a fix would push a PR past the size below, raise a second
issue and a second PR.

    <type>/<issue>/<kebab-description>

`feat` `fix` `chore` `docs` `refactor` `test` `research`, optionally scoped —
`feat(etl)/7/national-spine`. The PR body must contain `Closes #<N>` so the
issue closes on merge.

## Keep it under ~700 insertions, and under 250 if you can

Measured across **38 merged PRs**, counting `REQUEST_CHANGES` reviews. Every figure here is printed by
`python -m etl.probe_review_cost` and committed as
[`docs/sources/review-cost-measured.json`](docs/sources/review-cost-measured.json)
— this page states that rule below, so it had better follow it.

| insertions | PRs | mean review rounds | worst |
|---|---:|---:|---:|
| under 250 | 10 | **0.1** | 1 |
| 250–700 | 14 | **1.0** | 3 |
| 700–1500 | 6 | **5.8** | 10 |
| over 1500 | 8 | **9.6** | 14 |

The step between 700 and 1500 is not gradual. A large PR is not reviewed more
slowly, it is reviewed *repeatedly* — each round adds surface and the next
round finds defects in that surface.

Refresh with `python -m etl.probe_review_cost --record`. It needs a Gitea
token and makes one API call per merged PR, which is why the run is
committed rather than repeated by the suite. It skipped
**7** merges that name no PR — branch syncs, not reviewed changes — and says so rather than dropping them quietly.

## The evidence standard

**Measured is labelled measured. Estimated is labelled estimated.** Anything
else is a claim wearing a number's clothes.

- **Every figure in a document is printed by a probe, never typed.** If you
  cannot point at the command, delete the figure.
- **Commit the run**, so the page can be checked without repeating the fetch,
  and test the page against it **in both directions** — a figure on the page
  that is not in the record was typed; a figure in the record that is not on
  the page is a measurement nobody published.
- **Write the limits down before a reviewer finds them.** What the change does
  *not* establish belongs in the document, not in the reviewer's comment.
- Raw data is never committed. `data/` is gitignored.

## What a PR body carries

- The before and after, with the conditions the measurement was taken under
- **The rows that did not improve**, beside the ones that did
- What the change does not move — and a new issue if that is interesting
- The limits you already know about

## Tests

- **Unit and behaviour**, not one or the other.
- **Mutation-test every fix**: break it on purpose and confirm the suite goes
  red. A fix whose mutation passes will ship half-done and look complete.
  Check the mutation *applied* — a `replace` that matched nothing reports a
  pass and reads as proof.
- **Drive the code, not the artifact.** A test that reads a committed record
  says nothing about the code that wrote it. This repo has been caught by that
  repeatedly.
- Constants a guard rests on are **derived and asserted**, never tuned until
  the suite passes.
- Run the suite with an engine reachable, or the engine tests skip and a skip
  reads as a pass:

      SAMYAMA_TEST_URL=http://localhost:8201 SAMYAMA_URL=http://localhost:8201 \
        python3.11 -m pytest -q

  Use `python3.11`. No file over 500 lines — review skips it and blocks the PR.

## Before you push

Read your own diff as if someone else wrote it, and ask the three questions
that catch the most:

1. Every figure I put in a document — did a probe print it, or did I?
2. Every guard I added — is there a sibling call site with the same hole?
3. Every fix — does it break a promise made two lines up?

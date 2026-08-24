# Contributing

The standard a PR here works to. Written down so it is shared, rather than learned by
having PRs sent back — which is how it was being learned, at a measured cost of **4.8
change-request rounds per PR**.

## One issue, one branch, one PR

Branch names are `<type>/<ISSUE-ID>/<kebab-desc>`, where type is one of `feat` `fix`
`chore` `docs` `refactor` `test`. The PR body carries `Closes #N`, which is the only thing
that closes an issue on merge — not a commit message, not a comment.

**Never stack more than two PRs deep.** One stack four deep (#84 → #83 → #82 → #68) cost
more delay than every review round in the repo combined: one slow review blocked four PRs,
and each took four rounds.

Bundling several issues into one PR needs agreement first. It is sometimes right — a single
investigation answering three research questions should not be written three times — but it
is the exception.

## Every figure is printed by code

No number reaches a document by being typed. Probes print figures; documents quote what the
probes printed; tests assert the two agree.

This is the rule the repo has broken most often, and the failures are instructive: **427**
courses outside every chain where the measured answer was **395**, arrived at by arithmetic;
**868** occupations where the crosswalk's own `NO MATCH` sentinel made it **867**; **795 of
795** courses reported as stating a prerequisite when the real figure was **229**, because a
conditional count returned the row count.

The last one is the shape to fear. It parsed, it ran, it returned no error, and the answer
it gave — every course has a prerequisite — is exactly what a complete source looks like.

So: state the limitation before anyone finds it, and give the measurement next to the claim.

## Break your own fix before asking for review

A green suite proves nothing about a fix until you have made the fix wrong on purpose and
watched a test go red. On one day in this repo, **three fixes passed a fully green suite and
only failed when deliberately broken** — the tests around them were asserting something
else.

So for each fix: revert it in place, run the suite, confirm red, restore. If nothing goes
red, the test does not test the fix.

Watch for the vacuous pass in particular — a containment check against an empty set, a regex
that stopped matching because prose was reworded, a skip that reads as a pass. Several
guards in this repo now feed their own source file back through their own parser for exactly
this reason.

## Before requesting review

```bash
SAMYAMA_TEST_URL=http://localhost:8201 SAMYAMA_URL=http://localhost:8201 \
  SAMYAMA_REQUIRE_ENGINE=1 python -m pytest -q

python -m pyflakes <changed files>
python -m flake8 --select=E301,E302,E303,E741,F <changed files>
```

**Run the style pass last.** A PR was reported style-clean and then edited further; the
review found two violations introduced after the check. A check that ran before the last
edit is not a check.

`SAMYAMA_REQUIRE_ENGINE=1` turns an unreachable engine into a failure instead of a skip,
because "verified against the engine" must never reach a document on the strength of a run
nobody made.

## Size

**500 lines** per file, enforced by `tests/test_file_sizes.py`. Review skips a file over
that and blocks the PR, so an oversized file is worse than a badly organised one — it is an
unread one, and it is usually the file carrying the assertions.

Split by **subject, not by length**. Two files nobody can name is not an improvement. The
precedent is `test_probe_registry.py` → how the Registry is read, what it holds, and the
command line, with the shared builders in their own module.

The exception list is empty and may only shrink.

## What a PR body should contain

- The measurement, before and after, with the conditions it was taken under
- What did **not** improve, alongside what did
- Which reviewer findings you are rejecting, and the measurement that rejects them — a
  finding that does not hold should be answered with numbers, not silently ignored
- The mutations you ran

## Engine version

Every figure in this repo was measured against one engine build, recorded in
`etl/engine.py`. The image tag and the engine version are different numbers — see the README
section "Which engine produced these figures". On a bump, every published figure is
unverified until re-measured; that is worse than wrong, because nothing looks different.

## Data

No raw data in the repo. `data/` is gitignored. Probes cache what they fetch, documents cite
the source page, and a snapshot ships on a release rather than in the tree.

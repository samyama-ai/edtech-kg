# CI has never run the tests

**Every figure in the measured sections below was printed by
`python -m etl.probe_ci_history`, except where a section says otherwise.**
Two sections say otherwise and are marked where they begin: the incident
account, whose figures come from the merge history, and this page's
references to issue numbers. The
record is `docs/sources/ci-history-measured.json`; `tests/test_ci_history_doc.py` fails if
this page and that record disagree, in either direction.

Reading it needs a token — the Actions API is not public on a private repo:

    export SAMYAMA_GITEA_TOKEN=...
    python -m etl.probe_ci_history --record

## The measurement

Every figure here is measured. The suite duration is the one the Actions API
cannot report, so the probe times it directly and records the command.

| workflow | runs | succeeded | median | longest | `uses:` |
|---|---|---|---|---|---|
| `ci.yml` | 222 | **0** | 7.0s | 58s | 2 |
| `runner-diagnostic.yml` | 7 | 5 | 4.0s | 5s | 0 |
| `runner-diagnostics.yml` | 1 | 1 | 6.0s | 6s | not committed |

`runner-diagnostics.yml` — the plural — is an earlier diagnostic, since
deleted. It ran once and succeeded, and it is in the table because it is in
the record.

**It is not counted in the comparison below.** Its `uses:` cannot be read: the
file is not in the tree, so nothing can confirm it fetched no actions. It
corroborates and it does not verify, and the two must not be added together —
an earlier draft of this page said leaving it out "halved the action-free
evidence" while the comparison said 1 of 1, which is the page contradicting
itself about its own central claim.

Of those, **222 have usable timestamps** and 0 do not — the
floor count below is over the timed ones, because a run whose stamps will not
parse has no duration and an absent duration is not a small one.

`ci.yml` has run **222 times since 2026-08-21 and succeeded
0 times.**

## The tests have never executed — and that is a stronger claim than "CI fails"

The suite takes **47 seconds** locally with an engine already up — timed by
the probe, not asserted:

    python -m pytest -q --deselect tests/test_ci_history_doc.py

That figure was a typed `51` until a review pointed out that disclosing an
assertion is not the same as measuring it, and this is the figure the whole
argument turns on: if the suite took 30s the floor would drop toward 40s, the
58s run could have executed tests, and the headline would weaken.

`tests/test_ci_history_doc.py` is deselected from that timing because it asserts
this very figure — timing the whole suite is circular and could never
bootstrap. One module of 87.

CI additionally pulls a container image and polls for it. So **60 seconds
is a floor** — a chosen round number above the measured suite time, not a
figure derived from it, because the image pull is not timed here. A run that
*ended* faster than that cannot have run the tests,
whatever step it reported.

**0 of 222 timed runs reached that floor.** The longest run
in the repo's history is 58s.

That is what makes the red tick misleading rather than merely unhelpful. A red
tick normally means *the tests ran and something failed*. Here it has always
meant *the tests did not run*, and those look identical on the PR page.

## What isolates the cause

Two workflows, same runner, same repository, same week:

- **0 of 222** runs succeeded for the workflow that fetches
  actions (`actions/checkout@v4`, `actions/setup-python@v5`).
- **5 of 7** runs succeeded for the workflow that fetches
  nothing at all.

`runner-diagnostic.yml` (#167) was written with no `uses:` — deliberately, not
even `actions/checkout`.

**THAT COMPARISON DOES NOT SUPPORT A CAUSE, AND THIS PAGE SAID IT DID.**
Every one of the diagnostic's eight steps carries `continue-on-error: true`,
with `|| true` inside them — by design, so that one run maps the whole surface
instead of stopping at the first broken thing. **A workflow built so that
nothing can fail it did not fail.** Its 7 of 7 is not evidence that its steps
worked; it is evidence that they were not allowed to matter.

The caveat below used to list "step tolerance (0 tolerant versus 8)" beside
trigger and step count, as one confound among several. It is not one among
several. It is the whole of the difference in outcome.

**And the claim was then tested directly.** `ci.yml` had its two actions
removed (#186), and its first run without them failed as well. Removing the
actions did not turn the tick green, so fetching an action is at most part of
the cause and is not established as any of it.

It is still **not a controlled experiment**, and the differences that remain
are the ones this page always listed — trigger, step count, and the step
tolerance above. What has changed is which of them the outcome rests on.

What remains true is the fact, not the explanation: **0 of 222 runs of this
repo's test workflow have ever succeeded**, so the red tick has never been a
statement about the tests.

What would settle it is the step log of a failing run, which needs a browser
session — the API exposes run status and not step output, and the token
carries no admin scope to list the runner or its labels.

## What this does NOT establish

The diagnostic's success is **not** evidence that the runner can reach the
network. All **8 of its 8 steps** are
`continue-on-error` — by design, so one run maps the whole surface instead of
halting at the first broken thing. The cost of that design is that the job
reports success whatever its probes found, and its 4-second
duration is equally consistent with every probe failing immediately.

So the job outcome carries no information about DNS, PyPI or the container
registry. **That answer is in the log**, and Gitea exposes no job-log endpoint
to a repo-scoped token — the probe therefore does not claim it. Reading it
means opening the run in the web UI.

This distinction is the reason the page stops here rather than concluding. A
diagnostic that reports success because it was built not to fail is exactly
the shape of guard this repository keeps finding in its own tests.

## What follows

Nothing in `ci.yml` explains this and nothing in `ci.yml` can fix it. A repo
that dropped `setup-python` would move the failure to `pip install pytest`,
and then to `docker run`. The workflow is correct, its guards are
mutation-tested by `tests/test_ci_workflow.py`, and it starts working the
moment the runner can fetch what a job asks for.

**This is a runner-administration problem, not a repository one.** The open
question — whether the runner has no network at all, or only cannot reach the
action registry — is answered by one person reading the diagnostic's log.

## What it cost, once, this week

Not hypothetical. **The figures in this section are read from the merge history, not printed by
the probe** — the opening claim above covers the measurements, and this is an
account of one incident.

On 2026-09-07 four PRs merged in sequence — #172, #171, #173,
#175 — each green on its own branch, none conflicting textually with any other.
`main` went red on the fourth merge with five failures that had appeared on no
branch: #171 added a guard requiring every probe to write its record through a
stamped writer, and #173 and #175 were already in flight with probes that do
not.

This is the failure a merge-gating CI exists to catch, and it is invisible to
per-branch testing however careful that testing is — the two changes are only
in contact once both are on `main`. Nobody noticed at merge time. It was found
by running the suite locally two hours later, for an unrelated reason.

The fix is a separate change. What belongs here is the cost: **the repository
was merging into a broken `main` with a red tick that had meant nothing for
222 runs, and no signal distinguished that from any other day.**

Until then, **the tick on a PR in this repo means nothing**, and the suite has
to be run locally before merging:

    SAMYAMA_TEST_URL=http://localhost:8201 python -m pytest -q

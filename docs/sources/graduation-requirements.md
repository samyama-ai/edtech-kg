# State graduation requirements: the compilation exists and refuses us

**Every figure here was printed by `python -m etl.probe_graduation`.** The
record is `graduation-requirements-measured.json`;
`tests/test_graduation_doc.py` fails if this page and that record disagree,
in either direction.

    python -m etl.probe_graduation --record

## The question

edtech-kg#41: a student choosing next semester solves two constraints —
prerequisites (*what am I allowed to take*) and graduation requirements
(*what must I have by the end*). Without the second, a plan can be
prerequisite-valid and still fail to graduate the student. **A wrong answer
given confidently, which is worse than no answer.**

The issue names the Education Commission of the States' 50-state comparison
and is explicit about the licence: *"ECS is a non-profit and this is their
compilation — permission, not public domain."*

## Permission is refused, in the place a machine is meant to look

| source | robots.txt | permission | page | fetched |
|---|---:|---|---:|---|
| ECS 50-state comparison | 200 | **refused** | — not asked | **no** |
| ECS landing page | 403 | allowed | 403 | **no** |
| NCES state education reforms | 200 | allowed | 200 | yes |

`https://reports.ecs.org/robots.txt` is **`Disallow: /`** — a blanket refusal to every
crawler. The compilation is there and it is exactly the shape the issue
describes; we may not take it.

The public landing page answers **403** to this client, so the
comparison is not readable either way.

## The federal route is not an independent one

The issue asks *"whether going to the state regulations directly is cleaner,
since the underlying statutes are public even where the compilation is not."*

NCES publishes a collection of state-policy tables and **none of them is
graduation requirements**. The adjacent tables that do exist credit their
data to ECS:

> Education Commission of the States, Age Requirements for Free and Compulsory Education , retrieved January 8, 20

So the federal site is not a second source for this. Where it covers state
policy at all, it republishes the compilation we have just been refused —
and a licence follows the data rather than the host.

## What this leaves

**The requirements themselves are public.** They live in each state's statute
and regulation, and nothing here says otherwise. What does not exist is a
**normalised, machine-readable, fifty-state** version we may use:

- ECS built one and refuses crawlers.
- NCES did not build one and cites ECS where it comes close.
- Fifty separate statutes are public and are fifty different documents in
  fifty different shapes — the shape this repo has now measured four times
  and named in
  `progression-rules.md`, which arrives with edtech-kg#66 and is named here
  in prose rather than linked because it is not yet on `main`: the rule is
  published for a human, not as a join.

So a course plan cannot be checked against a graduation requirement from
national data. `docs/scope.md`'s rule already covers what to say instead:
**an answer says "meets the prerequisite", never "you will graduate"** — and
the schema must not make the stronger claim easy to state by accident.

## What this does not establish

Three sources on 2026-09-09. A **403** and a `Disallow` are refusals
to *this* client — ECS licenses its compilations, and an agreement would
settle it. **None was sought**, so what is measured is that no
unauthenticated machine route exists, which is the condition every other
source in this register was cleared against.

It also says nothing about per-state extraction. Fifty statutes are readable;
whether extracting them is worth building is a different question from
whether a dataset exists, and this page answers only the second.

**No page disallowed by robots was fetched.** The gate is in the probe rather
than in a habit, and the reason is in its docstring: while exploring this
issue the ECS table was fetched several times *before* its `robots.txt` was
read. That is the wrong order, and a probe that asks permission afterwards
has not asked.

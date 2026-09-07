# Samyama Graph 1.1.0 — measured behaviours

Everything this repo has established about the engine it runs on, in one place.
Each entry says what was measured, what it costs, and where the working code
that proves it lives.

**Why this file exists.** These findings were spread across five module
docstrings, a schema header, a demo, and four issues. A behaviour that only
exists in a comment beside the one call site that hit it is a behaviour the next
author rediscovers — and several here return a wrong answer rather than an
error, so rediscovery means a wrong figure shipped, not a crash.

**Version.** The image is `public.ecr.aws/f9f6l5u4/samyama-graph:1.1.0`. The
engine inside reports `1.7.0` at `/api/status` — the tag and the binary's own
version disagree, which is itself worth knowing, because a figure attributed to
"1.1.0" cannot be checked against a version the engine does not admit to
(`etl/engine.py`). **A tag is not a version.** Re-measure on any change of
either.

---

## The dangerous ones — wrong answer, no error

These are the reason this file is not a list of parse errors. Each returns
something plausible.

### `MERGE` ignores the constraint's index and scans

Write rate falls roughly as `1/n` while `MATCH` on the same constrained property
stays flat. At 1,500 nodes `MERGE` runs at 692/sec; at 37,141 it runs at 35.
`CREATE` into the same label holds at 749/sec throughout, and the same `MERGE`
against a nearly-empty label runs at 815 — so it is the size of the label being
merged into, not the statement.

This turns bulk loading from linear into quadratic: `n` rows cost about
`n² / 2k`, with `k ≈ 1.34 million`. Nine million rows is not 25 hours, it is
about 350 days.

**Workaround, measured:** a lookup and a conditional create — two round trips,
both index-backed — ran at 300/sec where `MERGE` managed 63.
edtech-kg#169. The arithmetic and the slice it decides are written up in
`first-load.md`, which arrives with the branch for edtech-kg#23 and is not
linked here until it lands.

### `REMOVE` reports success and changes nothing

`REMOVE n.p` parses, matches the node, and returns success while leaving the
property in place. `REMOVE n.p RETURN n.p` returns the value it has just claimed
to remove. `SET n.p = null` behaves the same, and deleting the node does not
help — one re-created with the same key comes back carrying the property.

So **"this property is absent" is a claim about a graph that has never held it**,
never about one that has been re-loaded. No loader change fixes this.
edtech-kg#163 · `etl/engine.py`

### An edge `MERGE` ignores its property map

`MERGE (a)-[e:R {s:'one'}]->(b)` followed by the same with `{s:'two'}` leaves
**one** edge holding `'one'`. The pattern matches on start, type and end alone.
A loader that MERGEs per row loses the second silently — no error, no trace in
the counts.
edtech-kg#77 · `etl/load_pwcs.py`

### `ORDER BY` on an alias introduced in `RETURN` is silently dropped

`RETURN length(p) AS d ORDER BY d` comes back unsorted; `ORDER BY length(p)`
sorts. Aggregate aliases are the exception and do work. An unsorted list that
looks sorted is the kind of thing an audience notices before the presenter does.
edtech-kg#79 · `demo/demo.py`, enforced by `tests/test_demo.py`

### A unique constraint does not reject a duplicate

Two `CREATE (:U {k:'same'})` against a declared-unique `U.k` both succeed. **A
constraint here is a declaration of the key, not an insert guard.** Loaders must
MERGE on the key, and nothing but a test enforces that.
`schema/edtech_kg.cypher`

### `tenant` is ignored on `/api/query`

The same graph comes back whatever tenant is sent, including one that has never
existed. `DELETE /api/tenants/<id>` returns 204 and deletes no data; an "empty"
tenant still held 2,196 nodes. One graph per process.
edtech-kg#149

---

## Parse errors — loud, and cheap to work around

| form | status |
|---|---|
| `CREATE CONSTRAINT <name> ON …` | named constraints are a parse error; a constraint cannot be named |
| `DROP CONSTRAINT …` | parse error — there is no way to drop or replace one |
| `MERGE (n:L {k: v}) SET n.p = x` | parse error. `ON CREATE SET` / `ON MATCH SET` are accepted, a bare `SET` is not (edtech-kg#75) |
| `UNWIND` | parse error alone, and returns `[]` rather than raising when it appears after a `WITH` in a longer query |
| Neo4j-5 `FOR (n:L) REQUIRE` | does not parse, despite appearing in the engine's own `CYPHER_COMPATIBILITY.md` |

`SHOW CONSTRAINTS` does parse, so what is declared can be inspected.

`ON CREATE SET` is the obvious workaround for the third row and is wrong for a
re-runnable loader: it fires only on insert, so a re-run after a rename leaves
the old value in place. `MATCH … SET` always refreshes.

---

## Things that are safe, and were checked

- **Re-applying the schema is safe.** Every statement in `schema/` applied twice
  against one instance returns no error, so the loader re-applies on each run
  without a guard. Asserted in `tests/test_schema_engine.py` rather than left as
  a property somebody remembers.
- **String literals have no escape sequence.** A quote character always opens or
  closes a literal and never appears within one, which is why `strip_comment`
  can track quotes without a parser (`etl/cypher_script.py`).

---

## Re-measuring

Nothing here should be trusted across a version change. The behaviours that
would be caught automatically are the parse errors — the suite fails. **The six
under "wrong answer, no error" would not**: they return something, and the tests
that would notice are the ones asserting a specific figure.

`etl/probe_engine_capability.py` measures the query constructs.
`etl/probe_engine_defects.py` measures the three that were previously recorded
here from prose — `REMOVE`, `tenant` and the `MERGE` index behaviour. Both are
runnable, and neither figure below is typed.

**It needs a scratch engine and it refuses a loaded one.** The probe writes
tens of thousands of nodes and cannot remove them, because not being able to
remove them is one of the defects it measures:

    docker run -d --name sg-defects -p 8224:8080 \
        public.ecr.aws/f9f6l5u4/samyama-graph:1.1.0
    python -m etl.probe_engine_defects --url http://localhost:8224 --record

Every check records `still_defective`, so **an engine upgrade that FIXES one
shows up as a changed record**, not as a probe that quietly prints something
else. All three are still present as of the committed run.

### `REMOVE` — measured, not remembered

The property survives `REMOVE` (`True`) and survives
`SET x = null` (`True`). `REMOVE p.kind RETURN p.kind`
returned `'gone-please'` — the value it had just claimed to
remove. Read back two ways, a projection and a count-by-value, so the finding
is not about a cached read.

### `tenant` — the API accepts and scopes nothing

Creating a tenant answered **201** and dropping one answered
**204**; every tenant — including one that has never existed —
saw the same graph, and dropping the tenant deleted nothing
(`True`).

The probe asserts the 201 rather than storing whatever it gets. Its first
version sent only `id`, got a 422, and would have recorded the API as
*refusing* these calls — contradicting the issue and reporting the defect as
absent. **A defect probe reporting a false absence is the worst outcome
available to it**, so a status other than 201 now stops the run.

### `MERGE` — the index is ignored

| nodes in label | `MERGE` /sec | `CREATE` /sec | `MATCH` /sec |
|---:|---:|---:|---:|
| 1,000 | 637.7 | 811.6 | 746.5 |
| 4,000 | 346.9 | 631.6 | 741.2 |
| 8,000 | 173.8 | 826.2 | 804.0 |
| 16,000 | 67.9 | 594.2 | 497.3 |

Over that range `MERGE` fell **9.4x** while `MATCH` moved
1.5x. The isolating control is the last figure: the same
`MERGE` statement against a fresh, nearly-empty label ran at
**467.2/sec** — full speed. It is the size of
the label being merged into, not the statement.

**These are timings and they vary between runs.** The committed record is one
run; re-running gives different absolute rates. What does not vary is the
shape — `MERGE` degrading by close to `1/n` while `MATCH` and `CREATE` stay
flat — and that shape is what `still_defective` tests, rather than any
threshold on a rate.

The first version of the timing was not usable and is worth recording: at a
batch of 40, `MERGE` came out FASTER at 2,000 nodes than at 500, because forty
round trips is short enough for warm-up to dominate. The engine caches parsed
ASTs and chosen plans, so the first call of a statement shape pays for parsing
that none of the rest do. Every timing is now preceded by an untimed warm-up of
the same shape.

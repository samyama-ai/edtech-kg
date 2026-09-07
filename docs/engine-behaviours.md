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

`etl/probe_engine_capability.py` measures the query constructs. It does not yet
cover `REMOVE`, `tenant`, or the `MERGE` index behaviour — those three are
recorded here from the issues that measured them, and turning them into one
runnable probe is the obvious next step.

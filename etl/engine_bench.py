"""How fast the engine writes, and whether `MERGE` uses the constraint's index.

Split from `etl/probe_engine_defects.py` when it passed the 500-line review
limit. Split by SUBJECT, not by length: everything there asks whether the
engine answers CORRECTLY — a removed property still returned, a tenant that
scopes nothing. This asks how fast it writes, which is a different question
with a different method. Correctness is read once; a rate has to be timed,
warmed up, and repeated at several sizes before it says anything.

edtech-kg#169. Nothing here reaches the network.
"""

from __future__ import annotations

import time

from etl.engine import Engine, Refused


def ratio(before: float, after: float) -> float | None:
    """How far a rate fell, or None if either end is unmeasured.

    None, never 0.0. `rate()` returns 0.0 when the elapsed clock is zero, and
    a `merge_fell_by` of 0.0 reads as "it did not fall" while meaning "there
    was nothing to divide".
    """
    if not before or not after:
        return None
    return round(before / after, 1)


#: Its own scratch label, not the correctness probe's. #169's own control is
#: that the same MERGE against a nearly-empty label runs at full speed — so
#: timing into a label something else has filled reports the other thing's
#: size, and the finding evaporates.
LABEL = "BenchProbe"

#: Label sizes at which the write rate is sampled. #169 measured to 37,141 and
#: found the fall continues; this stops at 16,000 so a probe run costs about
#: half a minute rather than an hour. **The trend is the finding, not the
#: endpoint** — a 1/n fall is visible across this range, and `--full` extends
#: it for anyone re-measuring the published table.
SIZES = (1000, 4000, 8000, 16000)
FULL_SIZES = SIZES + (32000,)
#: These are TARGETS. Each point records `nodes_at_start` and `nodes_at_end`
#: — the label grows while its own timings are being taken, so one number
#: would report a range as a point.

#: Writes timed at each size. The first version used 40 and the result was not
#: usable: MERGE came out FASTER at 2,000 nodes than at 500, which is the
#: opposite of the finding, because forty round trips is short enough for
#: process warm-up to dominate. Raised, and every timing is preceded by an
#: untimed warm-up of the same statement shape.
BATCH = 150
WARMUP = 30


def declare_constraint(engine: Engine, label: str) -> str:
    """Declare the uniqueness constraint, and say what happened.

    Returns "declared", "already" or a refusal message — never silence. The
    first version swallowed the refusal under a comment claiming it was
    "recorded, not swallowed", and no field for it existed anywhere.

    Whether the index is there is the whole subject: `MERGE` is being measured
    against a constrained key, and a run where the declaration failed measures
    something else entirely.
    """
    try:
        engine.run(f"CREATE CONSTRAINT ON (n:{label}) ASSERT n.id IS UNIQUE")
        return "declared"
    except Refused as refused:
        # A re-declaration is expected on a re-used engine and is not a
        # problem; anything else is, and the caller can see which.
        return f"refused: {refused}"


def rate(engine: Engine, statement, count: int) -> float:
    """Writes per second for `count` calls of `statement(i)`.

    Wall clock over the whole batch rather than a per-call mean: the figure
    that matters for a bulk load is throughput, and a mean of per-call times
    hides the round trip that dominates it.
    """
    # Warm up OUTSIDE the timer, with the same statement shape. The engine
    # caches parsed ASTs and chosen plans, so the first call of a shape pays
    # for parsing and planning that none of the rest do — and at small batch
    # sizes that single call decided the rate.
    #
    # Indices come AFTER the timed range, never before it. The first version
    # counted down from `-WARMUP`, which made the MATCH warm-up look up
    # `fill--30` — keys that do not exist. A miss and a hit are different code
    # paths, so the warm-up was warming the wrong one, and for the write
    # shapes the negative keys were extra rows nothing counted.
    for i in range(count, count + WARMUP):
        engine.run(statement(i))
    start = time.perf_counter()
    for i in range(count):
        engine.run(statement(i))
    elapsed = time.perf_counter() - start
    return round(count / elapsed, 1) if elapsed else 0.0


def repeated(engine: Engine, statement, count: int, repeats: int) -> float:
    """The MEDIAN of `repeats` measurements of one rate.

    **A single draw put the #169 verdict inside its own noise band.** On a
    live 1.1.0: MERGE fell 8.0x and MATCH fell 1.9x, against a rule that
    requires MATCH to fall less than 2.0x — a ~5% margin, on one unrepeated
    run, on an idle laptop. On a busier machine it flips and the probe reports
    #169 FIXED, which is the one outcome this probe exists never to produce.

    The spread is already documented and large: MERGE at 1,000 nodes swung
    403.8-621.2 across three runs, +/-54%, moving the published ratio between
    5.2x and 7.3x.

    A median rather than a mean, because the failure mode is one slow draw
    from something else running on the machine, and a mean carries it.
    """
    rates = sorted(rate(engine, statement, count) for _ in range(repeats))
    return rates[len(rates) // 2]


def merge_ignores_the_index(engine: Engine, sizes=SIZES,
                            repeats: int = 1) -> dict:
    """#169 — does `MERGE` use the constraint's index?

    Three rates at each size, on the SAME label and the same key:

      * `MERGE` on the constrained property — the one under suspicion
      * `CREATE` into the label, doing no lookup at all — the floor
      * `MATCH … WHERE key = …`, which does the same lookup MERGE needs

    If MERGE used the index it would track MATCH. The control that isolates
    the cause is the fourth: the same MERGE statement against a fresh, nearly
    empty label. #169 measured that at full speed, which is what shows the
    cost belongs to the size of the label being merged into rather than to the
    statement.
    """
    engine.run(f"MATCH (n:{LABEL}) DETACH DELETE n")
    bench_constraint = declare_constraint(engine, LABEL)

    filled, points = 0, []
    for size in sizes:
        # Fill up to `size` with CREATE, which #169 measured as flat — so the
        # fill itself does not decide the rates being compared.
        while filled < size:
            engine.run(f'CREATE (n:{LABEL} {{id: "fill-{filled}"}})')
            filled += 1

        merge_rate = repeated(
            engine, lambda i, s=size: f'MERGE (n:{LABEL} '
                                     f'{{id: "m-{s}-{i}"}})', BATCH, repeats)
        create_rate = repeated(
            engine, lambda i, s=size: f'CREATE (n:{LABEL} '
                                     f'{{id: "c-{s}-{i}"}})', BATCH, repeats)
        # SPREAD ACROSS THE WHOLE LABEL, not the first BATCH keys. Looking up
        # `fill-0..149` at every size asks for the same 150 rows however large
        # the label is, so a hot cache — the engine keeps one — would serve
        # them and the control would report "MATCH is flat" without ever
        # exercising the index at scale. A stride touches the full range, and
        # the modulo keeps the warm-up's out-of-range indices on real keys.
        stride = max(1, filled // (BATCH + WARMUP))
        match_rate = repeated(
            engine,
            lambda i, f=filled, st=stride:
                f'MATCH (n:{LABEL}) WHERE n.id = "fill-{(i * st) % f}" '
                f'WITH n RETURN n.id', BATCH, repeats)
        # Every timed CREATE and MERGE above added a node, and so did their
        # warm-ups. Counted rather than estimated: an undercount here makes
        # the NEXT size fill fewer nodes than it reports, and the whole table
        # is a claim about label size.
        # The count the timings were actually taken at, not the nominal
        # target. `filled` carries the timed and warm-up writes of every
        # earlier size, so by the last point the label held ~1,080 more nodes
        # than `size` — and every row of a table whose whole subject is label
        # size was then labelled with a number that was not the label size.
        started_at = filled
        # Every timed and warm-up write above added a node. Counted, not
        # estimated, and BOTH ends are recorded: the label grows while its own
        # timings are being taken, so a single `nodes_in_label` is a range
        # reported as a point. The fill loop tops up to `size` at the start of
        # each point, which absorbs the carry-over from earlier sizes — that is
        # why the two ends stay close, and recording both is what shows it
        # rather than asserting it.
        filled += 2 * (BATCH + WARMUP) * repeats
        points.append({"nodes_at_start": started_at,
                       "nodes_at_end": filled,
                       "requested_size": size,
                       "merge_per_sec": merge_rate,
                       "create_per_sec": create_rate,
                       "match_per_sec": match_rate})

    # The isolating control: identical MERGE, nearly empty label.
    # **The control needs the constraint too.** Without it the "identical
    # MERGE" differed in two variables — label size AND whether an index
    # existed — so a fast result could have meant either. It is only an
    # isolating control if the single difference is how much is in the label.
    engine.run(f"MATCH (n:{LABEL}Fresh) DETACH DELETE n")
    fresh_constraint = declare_constraint(engine, f"{LABEL}Fresh")
    fresh = repeated(engine,
                     lambda i: f'MERGE (n:{LABEL}Fresh {{id: "f-{i}"}})',
                     BATCH, repeats)

    first, last = points[0], points[-1]
    return {
        "issue": 169,
        "batch": BATCH,
        # How many times each rate was measured. A record that does not say
        # cannot be compared with one taken differently.
        "repeats_per_rate": repeats,
        "points": points,
        # RECORDED, which the comment on the old `except Refused: pass`
        # claimed and did not do — nothing was written and no field existed.
        # Both labels must be constrained or the control is not a control.
        "constraint_declared": {LABEL: bench_constraint,
                                f"{LABEL}Fresh": fresh_constraint},
        "merge_into_a_fresh_label_per_sec": fresh,
        # BOTH ends guarded. Only the denominator was, so a 0.0 numerator —
        # which `rate()` returns when the clock reports no elapsed time —
        # produced `merge_fell_by: 0.0`, a number that reads as "it did not
        # fall" and means "nothing was measured".
        "merge_fell_by": ratio(first["merge_per_sec"], last["merge_per_sec"]),
        "match_fell_by": ratio(first["match_per_sec"], last["match_per_sec"]),
        "still_defective": merge_is_still_defective(points),
    }


def merge_is_still_defective(points: list[dict]) -> bool:
    """MERGE degraded and MATCH did not. **Both halves are required.**

    A loaded machine slows everything, and that is not this bug — a verdict
    keyed on MERGE alone would report #169 present on any busy laptop. A
    verdict keyed on the ratio between them would report it present on an
    engine where MERGE had been fixed and MATCH had regressed.

    Its own function, not an expression inside the measurement, so the tests
    can drive THIS logic rather than a copy of it. A test that reimplements
    the rule it checks agrees with itself and proves nothing.

    Deliberately a shape test and not a threshold on a rate: absolute timings
    vary run to run, and a probe that fails when the machine is busy would be
    switched off.
    """
    if not points:
        return False
    first, last = points[0], points[-1]
    if not (first["merge_per_sec"] and last["merge_per_sec"]):
        return False
    return (last["merge_per_sec"] < first["merge_per_sec"] / 2
            and last["match_per_sec"] > first["match_per_sec"] / 2)

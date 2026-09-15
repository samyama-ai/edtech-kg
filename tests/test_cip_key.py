"""The CIP key — one canonical form, and what is not a programme.

Split out of `tests/test_load_education.py` at the 500-line review limit, by
SUBJECT: that file drives the load, this one drives the key the load and the
CIP-SOC crosswalk have to agree on.

Two defects, both merged in #187 and both found while starting #196:

  * `cipcode_6digit` arrives as an INT, so `str()` dropped the leading zero
    from every code below `10.0000`. 70 of 664 `Programme` nodes carried a
    short key, and the crosswalk keys on the dotted six-digit form — so the
    join failed QUIETLY, dropping about a tenth of programmes.
  * IPEDS files an institution-level TOTAL under `cipcode_6digit = 99`,
    written as a `Programme` like any other. Measured on Virginia 2022:
    141,688 awards under `99` against 141,908 under every real code
    combined, because the first is the sum of the second.
"""

from __future__ import annotations

import pytest

from etl import cip
from etl import load_education as loader
from etl.engine import Refused
from tests.education_fixtures import (Recorder, completions,
                                      slice_on_disk)


def test_a_cip_beginning_with_zero_keeps_it(tmp_path):
    """**The API returns `cipcode_6digit` as an int**, so `str()` dropped the
    leading zero from every code below `10.0000`: `01.0000` arrived as
    `"10000"`. Measured on a full Virginia load, 70 of 664 `Programme` nodes
    carried a short key.

    Not cosmetic. The CIP-SOC crosswalk keys on the dotted six-digit form, so
    a join against a stripped code fails QUIETLY — the query returns rows,
    just fewer, and every programme whose CIP begins with zero drops out.
    """
    engine = Recorder()
    rows = completions(1)
    rows[0]["cipcode_6digit"] = 10000          # IPEDS CIP 01.0000, as an int
    loader.load(engine, cache=slice_on_disk(tmp_path, rows))
    written = " ".join(engine.sent)
    assert "'010000'" in written, (
        f"the leading zero was dropped; statements carry "
        f"{[s for s in engine.sent if '0000' in s][:2]}")
    assert "'10000'" not in written.replace("'010000'", "")


@pytest.mark.parametrize("field", loader.WRITTEN_FIELDS["completions"])
def test_every_written_completion_field_is_checked_before_anything_is(
        tmp_path, field):
    """**The completions half of `refuse_unwritable` had no test.** Both
    `refuse_unwritable(institutions, completions)` -> `(institutions)` and
    `WRITTEN_FIELDS["completions"]` -> `()` passed the whole suite clean —
    so the claim the function's own docstring says it was written to make was
    the one thing unguarded, on the larger of the two tables.

    Parametrized over the field list rather than sampling one, because the
    module comment calls that list load-bearing: a field dropped from it is a
    value reaching the graph unchecked, and nothing else would say so.

    **The bad row is LAST, not first.** With it first the load raises on row
    one either way, so `engine.sent == []` holds whether the pre-flight ran
    or not — the first version of this test passed with `WRITTEN_FIELDS
    ["completions"]` emptied to `()`. Putting it last is what makes the
    assertion mean "nothing was written", because without the pre-flight the
    five rows ahead of it are already in the graph.
    """
    engine = Recorder()
    bad = """both " and ' quotes"""
    rows = completions(6)
    rows[-1][field] = bad
    cache = slice_on_disk(tmp_path, rows)
    with pytest.raises(Refused):
        loader.load(engine, cache=cache)
    assert engine.sent == [], (
        f"an unwritable {field} was discovered after the load had already "
        f"written — there is no transaction to roll back to")


@pytest.mark.parametrize("raw, expected", [
    (10000, "010000"), ("10000", "010000"), (120401, "120401"),
    ("01.0000", "010000"), ("51.3801", "513801"), (99, "000099"),
    (" 51.3801 ", "513801"), ("0099", "000099"),
])
def test_cip_codes_normalise_to_one_form(raw, expected):
    """One canonical form, decided once. Dotted or not, int or str, the key
    is the same six digits — otherwise the join is correct only for the
    call sites somebody remembered."""
    assert cip.cip_code(raw) == expected


def test_a_value_that_is_not_a_cip_code_is_refused():
    """Refused rather than zero-padded into something that looks like a code."""
    with pytest.raises(Refused):
        cip.cip_code("not a cip")


def test_the_institution_total_row_is_not_loaded_as_a_programme(tmp_path):
    """**IPEDS files an institution-level TOTAL under `cipcode_6digit = 99`.**
    Loaded as a programme, the totals sit in the graph beside the things they
    total — measured on Virginia 2022, 141,688 awards under `99` against
    141,908 under every real code combined, because the first IS the sum of
    the second. `MATCH (c:Completion) RETURN sum(c.awards)` then returns about
    twice the awards actually conferred, and nothing says why.

    Same class as the `race 99` / `sex 99` trap the walkthrough demonstrates,
    on a third axis — except this one was materialised as a node.
    """
    engine = Recorder()
    rows = completions(2)
    rows[0]["cipcode_6digit"] = 99             # the grand total
    summary = loader.load(engine, cache=slice_on_disk(tmp_path, rows))
    assert summary["rows_skipped_grand_total"] == 1
    assert summary["completions_in"] == 1, "the total was counted as a load"
    written = " ".join(engine.sent)
    assert "'000099'" not in written, "the grand total reached the graph"


def test_the_skipped_total_is_reported_not_swallowed(tmp_path):
    """Recorded like the other two skips. A slice that silently drops rows
    cannot be compared with IPEDS's own published total."""
    engine = Recorder()
    rows = completions(3)
    rows[0]["cipcode_6digit"] = 99
    loaded = loader.load(engine, cache=slice_on_disk(tmp_path, rows))
    lines = loader.report(loaded, loader.in_the_graph(engine))
    assert any("institution-total rows" in line for line in lines), lines
    assert any("1 institution-total" in line for line in lines), lines


@pytest.mark.parametrize("raw", [
    10000.0, "10000.0", "1.0", "abc", "1234567", "51 3801", "", "51.380",
    # Arabic-Indic numerals. `\\d` matches these, so a Unicode digit string
    # passed `fullmatch` and was zero-padded into something that LOOKS like a
    # CIP — the module's own argument is that a wrong key which parses is
    # worse than one that refuses. `[0-9]` costs nothing.
    "\u0661\u0662\u0663\u0664\u0665\u0666",
])
def test_a_value_that_is_not_a_cip_SHAPE_is_refused(raw):
    """**Digit-checking was not enough.** `str(10000.0)` is `"10000.0"`, and
    stripping the dot gave `"100000"` — a valid-LOOKING six-digit code that is
    silently a different programme. A wrong key that parses is worse than one
    that refuses, and a key that looked fine is the whole of this issue.

    So the two published shapes are matched — `51.3801` and `513801` — and
    anything else refuses.
    """
    with pytest.raises(Refused):
        cip.cip_code(raw)


def test_the_total_is_caught_by_its_SERIES_not_by_the_literal_99(tmp_path):
    """`99` normalises to `000099`, whose series is `00`. IPEDS's own series
    run 01-61, so nothing real lands there — measured on Virginia 2022,
    series `00` covers exactly the 13,950 grand-total rows and nothing else.

    Keyed on the series so a 2- or 4-digit subtotal in a future slice is
    caught by the same rule rather than needing another literal.
    """
    engine = Recorder()
    rows = completions(3)
    rows[0]["cipcode_6digit"] = 99       # the grand total
    rows[1]["cipcode_6digit"] = 1        # a 1-digit subtotal -> 000001
    summary = loader.load(engine, cache=slice_on_disk(tmp_path, rows))
    assert summary["rows_skipped_grand_total"] == 2
    assert "'000099'" not in " ".join(engine.sent)
    assert "'000001'" not in " ".join(engine.sent)


def test_a_bad_cip_is_refused_before_the_institutions_are_written(tmp_path):
    """**The partial write.** `refuse_unwritable` ran, then 147 institutions
    were written, and only THEN did the first `cip_code()` call happen — so a
    malformed code raised with the institutions already in the graph, which is
    the exact failure the pre-flight two lines above exists to prevent.
    """
    engine = Recorder()
    rows = completions(3)
    rows[-1]["cipcode_6digit"] = "not a cip"
    with pytest.raises(Refused):
        loader.load(engine, cache=slice_on_disk(tmp_path, rows))
    assert not [s for s in engine.sent if "CREATE" in s], (
        f"wrote before discovering it could not finish: "
        f"{[s for s in engine.sent if 'CREATE' in s][:2]}")


def test_a_graph_keyed_the_old_way_is_refused_not_duplicated(tmp_path):
    """**The key changed, so idempotence no longer transfers.**
    `completion_id` hashes the NORMALISED CIP now, so every id differs from
    the one the previous version produced. Run over a graph built by the old
    code, every lookup missed: a second full set of ~51,000 Completion nodes
    landed beside the first, `already_present` reported 0, and nothing raised.

    The loader's selling point is that idempotence is measured. This is the
    one case where the measurement does not carry, so it refuses.
    """
    # `c.id =` first: both statements contain "count(c)", so the more
    # specific fragment has to be matched before the general one.
    engine = Recorder({"c.id =": {"records": [[0]]},
                       "count(c)": {"records": [[51085]]}})
    with pytest.raises(Refused, match="none of them carries an id"):
        loader.load(engine, cache=slice_on_disk(tmp_path, completions(3)))
    assert not [s for s in engine.sent if "CREATE" in s], (
        "wrote into a graph keyed the old way")


def test_a_graph_keyed_this_way_loads_normally(tmp_path):
    """One match is enough — a graph loaded by this version matches on the
    first id tried, so the guard costs one query and gets out of the way."""
    rows = completions(3)
    first = loader.completion_id(rows[0])
    engine = Recorder({f"c.id = '{first}'": {"records": [[1]]},
                       "c.id =": {"records": [[0]]},
                       "count(c)": {"records": [[51085]]}})
    loader.load(engine, cache=slice_on_disk(tmp_path, rows))
    assert [s for s in engine.sent if "CREATE" in s], "the guard blocked a good load"


def test_an_empty_graph_is_not_mistaken_for_a_rekeyed_one(tmp_path):
    """Nothing held means nothing to disagree with."""
    engine = Recorder({"count(c)": {"records": [[0]]}})
    loader.load(engine, cache=slice_on_disk(tmp_path, completions(2)))
    assert [s for s in engine.sent if "CREATE" in s]


def test_the_totals_are_dropped_before_the_zero_award_filter(tmp_path):
    """**Nothing pinned the order.** The grand-total drop runs first, which is
    why `rows_skipped_zero_awards` fell from 132,284 to 125,692 and why the
    page had to say "71% of the rows left after the institution totals are
    dropped". Swap the two and both figures change meaning while the suite
    stays green.
    """
    rows = completions(4)
    rows[0]["cipcode_6digit"] = 99                      # a total, with awards
    rows[1]["cipcode_6digit"] = 99; rows[1]["awards_6digit"] = 0   # total AND zero
    rows[2]["awards_6digit"] = 0                        # a real row, zero awards
    summary = loader.load(Recorder(), cache=slice_on_disk(tmp_path, rows))
    assert summary["rows_skipped_grand_total"] == 2, (
        "totals are being counted after the zero-award filter has eaten one")
    assert summary["rows_skipped_zero_awards"] == 1, (
        "the zero-award count is including a row already dropped as a total")
    assert summary["completions_in"] == 1


def test_all_rows_still_drops_the_institution_totals(tmp_path):
    """`--all-rows` loads rows recording zero awards. It does not load
    totals — a total is not a programme at any row count — and nothing said
    so, on the flag whose documented purpose is "load everything"."""
    rows = completions(3)
    rows[0]["cipcode_6digit"] = 99
    rows[1]["awards_6digit"] = 0
    summary = loader.load(Recorder(), only_awarded=False,
                          cache=slice_on_disk(tmp_path, rows))
    assert summary["rows_skipped_grand_total"] == 1
    assert summary["rows_skipped_zero_awards"] == 0, "--all-rows dropped a zero row"
    assert summary["completions_in"] == 2

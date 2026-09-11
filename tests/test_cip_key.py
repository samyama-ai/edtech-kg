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
])
def test_cip_codes_normalise_to_one_form(raw, expected):
    """One canonical form, decided once. Dotted or not, int or str, the key
    is the same six digits — otherwise the join is correct only for the
    call sites somebody remembered."""
    assert loader.cip_code(raw) == expected


def test_a_value_that_is_not_a_cip_code_is_refused():
    """Refused rather than zero-padded into something that looks like a code."""
    with pytest.raises(Refused):
        loader.cip_code("not a cip")


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


"""`docs/national-spine.md` held to the run that produced it.

edtech-kg#7. The page was written by substituting from the record rather than
by transcribing, which removes the mistake this repo has made most often — but
a page and a record drift apart the moment either is edited, and the page is
the one a reader quotes.

Nothing here loads anything. The record is a committed run; this reads it.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "national-spine.md"
RECORD_PATH = ROOT / "docs" / "sources" / "national-spine-measured.json"


def _needed(path: pathlib.Path) -> str:
    """Read, or fail by NAME rather than at collection.

    Module-level `read_text`/`json.loads` turn a missing or renamed file into
    a collection error for the whole file — pytest reports "error" with a
    traceback and no test name, which is the least useful shape a failure can
    take.
    """
    if not path.exists():
        pytest.fail(f"{path.relative_to(ROOT)} is missing; "
                    f"`python -m etl.load_education --record` writes it")
    return path.read_text(encoding="utf-8")


PAGE = DOC.read_text(encoding="utf-8") if DOC.exists() else ""
RECORD = (json.loads(RECORD_PATH.read_text(encoding="utf-8"))
          if RECORD_PATH.exists() else {})
ISSUED, HELD = RECORD.get("issued", {}), RECORD.get("in_graph", {})


def test_the_page_and_the_record_are_both_here():
    """Named, so a rename fails one test instead of erroring the file."""
    _needed(DOC)
    _needed(RECORD_PATH)


def test_every_node_and_edge_count_on_the_page_is_the_measured_one():
    """The five counts are the whole claim of the load.

    **Anchored to the LABEL, not just to the number.** `f"| {count:,} |" in
    PAGE` ignores which row it lands in, so the page could swap 147 and 664
    between `Institution` and `Programme`, or hang a count on the wrong edge,
    and still pass — while reporting a graph that does not exist.
    """
    rows = dict(re.findall(r"^\| `?([A-Za-z(:)\[\]>\-]+)`?[^|]*\| ([\d,]+) \|$",
                           PAGE, re.M))
    for name, count in HELD.items():
        key = next((k for k in rows if name in k), None)
        assert key, f"{name} has no row on the page"
        assert int(rows[key].replace(",", "")) == count, (
            f"the page says {name} is {rows[key]}; the record says "
            f"{count:,}")


def test_the_page_states_the_counts_the_graph_held_not_the_ones_issued():
    """**They are equal in this run, and that is the finding, not licence to
    quote either.** If a later run leaves a gap, a page built from the issued
    figures would report a clean load that did not happen.

    The name promised a check on the PAGE and the body only compared two
    fields of the record — so the page could have quoted the issued figures
    throughout and this would still have passed. It now requires the page to
    carry the held count and to say which of the two it is quoting.
    """
    for label in ("Institution", "Programme", "Completion"):
        issued = ISSUED[{"Institution": "institutions_in",
                         "Programme": "programmes_in",
                         "Completion": "completions_in"}[label]]
        assert HELD[label] == issued, (
            f"the record itself shows a gap on {label}; the page says there "
            f"is none")
        assert f"{HELD[label]:,}" in PAGE, f"{label} is not on the page"
    assert "read back" in PAGE.lower(), (
        "the page does not say the counts came out of the graph rather than "
        "from the input, which is the distinction the whole report exists for")


def test_the_load_time_and_statement_count_are_the_measured_ones():
    assert f"{ISSUED['statements_issued']:,} statements" in PAGE
    assert f"{ISSUED['seconds']}s" in PAGE


def test_the_rate_curve_on_the_page_comes_from_the_recorded_run():
    """**The curve used to be sampled by a separate process during a
    different load**, so the page printed one run's curve beside another
    run's totals. Both figures were real and neither described the other.
    """
    curve = ISSUED["rate_curve"]
    assert curve, "the record carries no curve"
    rows = re.findall(r"^\| (\d+) \| ([\d,]+) \| ([\d.]+) \|$", PAGE, re.M)
    assert rows, "the page shows no curve"
    # The page rounds the elapsed seconds; the record keeps a decimal. The
    # rounding is compared, not ignored — a row whose time is off by more
    # than that is a row from another sample.
    samples = {(round(p["seconds"]), p["completions_held"],
                p["completions_per_second"]) for p in curve}
    # **The LAST sample has to be on the page.** Rows being a subset of the
    # record leaves the regression `test_the_curve_reaches_the_load_it_
    # describes` guards in the record still droppable from the page — the
    # final rate is the one nearest the size a larger slice would start from.
    last = curve[-1]
    assert re.search(
        rf"^\| {round(last['seconds'])} \| {last['completions_held']:,} \| "
        rf"{last['completions_per_second']} \|$", PAGE, re.M), (
        "the page's curve stops before the load does")
    for seconds, held, rate in rows:
        assert (int(seconds), int(held.replace(",", "")), float(rate)) in \
            samples, f"the row at {seconds}s is in no sample of the record"


def test_the_statement_rate_is_derived_from_the_curve_it_sits_under():
    """**The only figure on this page computed rather than substituted, and
    the only one that was wrong.**

    The page read "finishes at 38.6/sec ... so that is about 153
    statements/sec". 38.6 x 6 is 232; the 153 was the previous run's 25.5 x 6.
    When the record was regenerated both measured figures either side of that
    sentence were substituted and the arithmetic between them was not — on a
    page whose opening line is that nothing here was typed by hand, and for
    the figure a reader uses to size a fifty-state load.

    It survived because every other doc test checks a figure LIFTED from the
    record and none checked one DERIVED from it. This closes that shape.

    Nothing here is typed, including the six: the statements a completion
    costs come out of the record exactly, because institutions and programmes
    cost two apiece and the rest of the run is completions.
    """
    issued = ISSUED
    each = ((issued["statements_issued"]
             - 2 * (issued["institutions_in"] + issued["programmes_in"]))
            / issued["completions_in"])
    assert each == int(each), (
        f"a completion no longer costs a whole number of statements ({each}); "
        f"the page's 'six statements' sentence needs re-deriving")
    finishing = round(ISSUED["rate_curve"][-1]["completions_per_second"] * each)
    assert f"{finishing} statements/sec as it finishes" in PAGE, (
        f"the page does not carry the finishing rate its own curve gives "
        f"({finishing} statements/sec)")
    whole = round(issued["statements_issued"] / issued["seconds"])
    assert f"{whole} statements/sec averaged over the whole run" in PAGE, (
        f"the page does not carry the whole-run rate ({whole} statements/sec)")


def test_the_curve_reaches_the_load_it_describes():
    """A curve stopping short of the total hides the rate the load finished
    at — the one nearest the size a larger slice would start from."""
    assert ISSUED["rate_curve"][-1]["completions_held"] == \
        ISSUED["completions_in"]


def test_the_skipped_rows_are_stated_rather_than_left_out():
    """69% of the slice is dropped. A page that did not say so would describe
    a load of the whole table."""
    # **In their own table rows, not loose in the prose.** `"169" in PAGE`
    # is satisfied by any incidental three digits — a port number, a byte
    # count, part of a larger figure.
    # **ROW-ANCHORED, not merely cell-anchored.** Cell-anchored, swapping
    # 132,284 and 169 between the "zero awards" row and the "collapsing onto
    # one key" row passed every test while the page said the opposite of the
    # truth — mutation-verified.
    for figure, names in ((ISSUED["rows_skipped_zero_awards"], "zero awards"),
                          (ISSUED["duplicate_rows_skipped"], "one key")):
        assert re.search(rf"^\|[^|]*{re.escape(names)}[^|]*\| {figure:,} \|",
                         PAGE, re.M), (
            f"the row naming {names!r} does not carry {figure:,}")


def test_the_page_says_the_writes_are_not_merge_and_why():
    """#7's definition of done says "every write a MERGE". This load does not,
    and a deviation from the issue that is not stated is a deviation a
    reviewer has to find."""
    assert "MERGE" in PAGE
    # **In their own sentence, not loose on the page.** `"692" in PAGE` was
    # satisfied by any unrelated 692 — mutation-verified: changing the MERGE
    # rate to 999 and adding a sentence containing 692 elsewhere passed.
    assert re.search(r"692 statements/sec at 1,500 nodes", PAGE), (
        "the page does not carry the MERGE rate that justifies the deviation")
    assert re.search(r"35/sec at 37,141", PAGE), (
        "the page does not carry the rate MERGE falls to")


def test_the_page_says_what_is_not_loaded():
    """#7's scope names `Occupation` and the CIP-SOC crosswalk. Neither is
    loaded. A reader discovering that by writing a traversal that returns
    nothing is the expensive way to find out."""
    assert "not** in this load" in PAGE or "not in this load" in PAGE
    assert "Occupation" in PAGE and "CIP–SOC" in PAGE


def test_the_record_was_written_by_a_clean_tree():
    """A record stamped `dirty: true` was produced by code that is in no
    commit, which is worth knowing before quoting its figures."""
    assert RECORD["code"]["dirty"] is False
    assert RECORD["code"]["commit"] != "unknown"


def test_the_idempotence_figures_come_from_the_record():
    """**The page claimed "175,762 statements, zero created" and no record
    held it.** It came from a run done by hand, on a page whose opening
    sentence says every figure was substituted from the record — so the one
    claim the loader's whole design rests on was the one with nothing behind
    it.

    `--record` runs the load twice now, and these are the second pass.
    """
    second = RECORD["second_run"]
    assert second["nodes_and_edges_created"] == 0, (
        "the recorded re-run created something; the load is not idempotent "
        "and the page says it is")
    assert f"{second['statements_issued']:,}" in PAGE
    assert f"| **{second['nodes_and_edges_created']:,}** |" in PAGE, (
        "the page does not carry the recorded created count")
    assert second["in_graph_after"] == HELD, (
        "the graph changed between the two passes")


def test_the_page_says_which_slice_this_is():
    """**A page titled "national spine" that never says it is one state.**
    The record carries `fips` and `year`; the page did not, and every figure
    on it describes Virginia. A reader multiplying up to fifty states would
    be doing so on a page that never said not to."""
    # `str(fips)` alone was satisfied by the 51 inside 51,544 in the curve
    # table. Anchored to how the page actually writes it.
    assert re.search(rf"fips={RECORD['fips']}\b", PAGE), (
        "the page does not name the slice's FIPS code")
    assert re.search(rf"\b{RECORD['year']}\b", PAGE)
    assert "Virginia" in PAGE
    assert "one state" in PAGE.lower()


def test_the_key_collision_figures_come_from_their_own_record():
    """They were measured once by hand and written into three files. The
    page reads them from `completion-key-measured.json` now, and the figure
    it leads with is the one that says what is actually lost."""
    key = json.loads(
        (ROOT / "docs" / "sources" / "completion-key-measured.json")
        .read_text(encoding="utf-8"))
    for figure in ("rows", "groups_with_more_than_one_majornum",
                   "groups_losing_a_count", "awards_lost"):
        assert f"{key[figure]:,}" in PAGE, (
            f"the page does not carry the measured {figure}")
    assert key["awards_lost"] > key["groups_losing_a_count"], (
        "the two figures no longer differ, so the page's warning about "
        "quoting the wrong one needs re-checking")

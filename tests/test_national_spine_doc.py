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

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "national-spine.md"
RECORD = json.loads(
    (ROOT / "docs" / "sources" / "national-spine-measured.json")
    .read_text(encoding="utf-8"))
PAGE = DOC.read_text(encoding="utf-8")
ISSUED, HELD = RECORD["issued"], RECORD["in_graph"]


def test_every_node_and_edge_count_on_the_page_is_the_measured_one():
    """The five counts are the whole claim of the load."""
    for label, count in HELD.items():
        assert f"| {count:,} |" in PAGE, f"{label} ({count:,}) is not on the page"


def test_the_page_states_the_counts_the_graph_held_not_the_ones_issued():
    """**They are equal in this run, and that is the finding, not licence to
    quote either.** If a later run leaves a gap, a page built from the issued
    figures would report a clean load that did not happen.
    """
    for label in ("Institution", "Programme", "Completion"):
        assert HELD[label] == ISSUED[
            {"Institution": "institutions_in", "Programme": "programmes_in",
             "Completion": "completions_in"}[label]], (
            f"the record itself shows a gap on {label}; the page says there "
            f"is none")


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
    for seconds, held, rate in rows:
        assert (int(seconds), int(held.replace(",", "")), float(rate)) in \
            samples, f"the row at {seconds}s is in no sample of the record"


def test_the_curve_reaches_the_load_it_describes():
    """A curve stopping short of the total hides the rate the load finished
    at — the one nearest the size a larger slice would start from."""
    assert ISSUED["rate_curve"][-1]["completions_held"] == \
        ISSUED["completions_in"]


def test_the_skipped_rows_are_stated_rather_than_left_out():
    """69% of the slice is dropped. A page that did not say so would describe
    a load of the whole table."""
    assert f"{ISSUED['rows_skipped_zero_awards']:,}" in PAGE
    assert f"{ISSUED['duplicate_rows_skipped']:,}" in PAGE


def test_the_page_says_the_writes_are_not_merge_and_why():
    """#7's definition of done says "every write a MERGE". This load does not,
    and a deviation from the issue that is not stated is a deviation a
    reviewer has to find."""
    assert "MERGE" in PAGE
    assert "692" in PAGE and "35/sec" in PAGE, (
        "the page does not carry the measurement that justifies the deviation")


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

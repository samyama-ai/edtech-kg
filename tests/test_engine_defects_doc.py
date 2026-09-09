"""`docs/engine-behaviours.md`'s three defect sections, held to the record.

These three were prose until now — recorded from the issues that measured them
in shells. The page says no figure in it is typed; this is what makes that true
for the sections `etl/probe_engine_defects.py` produces.

Nothing here reaches an engine. The record is committed and the page is read
against it, in both directions.
"""

from __future__ import annotations

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "engine-behaviours.md"
RECORD = json.loads((ROOT / "docs" / "sources"
                     / "engine-defects-measured.json").read_text("utf-8"))

PAGE = DOC.read_text(encoding="utf-8")
MERGE, REMOVE, TENANT = RECORD["merge"], RECORD["remove"], RECORD["tenant"]


def stated(pattern: str) -> str:
    found = re.search(pattern, PAGE)
    assert found, f"the page no longer states this — {pattern!r} matched nothing"
    return found.group(1)


def test_the_merge_table_is_the_measured_one():
    """Every row, not the first. A table bound only at its endpoints can go
    stale in the middle and still pass — and the middle is where the shape of
    the fall is visible."""
    rows = re.findall(
        r"^\| ([\d,]+) \| ([\d.]+) \| ([\d.]+) \| ([\d.]+) \|$", PAGE, re.M)
    assert len(rows) == len(MERGE["points"]), (
        f"the page shows {len(rows)} timing rows; the record holds "
        f"{len(MERGE['points'])}")
    for row, point in zip(rows, MERGE["points"]):
        assert int(row[0].replace(",", "")) == point["nodes_at_start"]
        assert float(row[1]) == point["merge_per_sec"]
        assert float(row[2]) == point["create_per_sec"]
        assert float(row[3]) == point["match_per_sec"]


def test_the_isolating_control_is_quoted_and_measured():
    """The fresh-label rate is what makes this a claim about the index rather
    than about a slow engine. Without it the table is just three columns."""
    assert float(stated(r"\*\*([\d.]+)/sec\*\* — full speed")) == \
        MERGE["merge_into_a_fresh_label_per_sec"]
    assert float(stated(r"`MERGE` fell \*\*([\d.]+)x\*\*")) == \
        MERGE["merge_fell_by"]


def test_the_remove_table_states_both_halves_of_the_finding():
    """The row losing the key AND the reads staying stale. Either alone is a
    different, milder bug — "REMOVE does nothing" would at least leave the
    graph and the answers agreeing, which is the point the page now makes."""
    assert REMOVE["row_lost_the_key_on_remove"] is True, (
        "REMOVE no longer changes the row; the page's correction is wrong now")
    assert REMOVE["reads_stale_after_remove"] is True, (
        "reads are no longer stale — #163 is fixed, and the page and the "
        "issue both need rewriting. The best possible reason for this to fail")
    assert "**key gone**" in PAGE and "**still matches**" in PAGE, (
        "the table must show the row losing the key while the filter keeps "
        "matching — that contrast IS the finding")


def test_the_older_entry_no_longer_contradicts_the_measurement():
    """The page carried the claim twice, and the probe disproved one of them.
    A document that states a finding and its opposite in two places is worse
    than one that states neither."""
    assert "reports success and changes nothing" not in PAGE, (
        "the earlier entry still says REMOVE changes nothing; the whole-row "
        "read shows the key gone")


def test_the_restart_question_is_recorded_as_unknown_not_guessed():
    """The obvious test is void here — no volume, so a restart empties the
    graph and the re-read answers about nothing. Recorded as null."""
    assert REMOVE["staleness_survives_restart"] is None
    assert "not established" in PAGE and "mounts no volume" in PAGE


def test_the_tenant_section_quotes_the_status_codes():
    """The codes ARE the finding — that the API accepts these calls and scopes
    nothing. A page that dropped them would leave "tenant is ignored" reading
    as "tenant is rejected", which is a different bug with a different fix."""
    assert int(stated(r"Creating a tenant answered \*\*(\d+)\*\*")) == \
        TENANT["create_status"]
    assert int(stated(r"dropping one answered\n\*\*(\d+)\*\*")) == \
        TENANT["delete_status"]
    assert TENANT["every_tenant_sees_one_graph"] is True


def test_the_page_says_the_timings_vary():
    """The one claim that keeps the table honest. Absolute rates differ
    between runs; the shape does not. A page quoting rates without saying so
    invites a reader to treat a re-run's different numbers as a regression."""
    assert "vary between runs" in PAGE
    assert "still_defective" in PAGE, (
        "the page must say a FIXED defect shows up as a changed record — "
        "otherwise nothing tells the next reader how a fix would surface")


def test_every_defect_the_probe_measures_has_a_section():
    """Caught by construction rather than by memory: a fourth defect added to
    the probe with no section here would otherwise be measured and unpublished.
    """
    for key, heading in (("remove", "### `REMOVE`"),
                         ("tenant", "### `tenant`"),
                         ("merge", "### `MERGE`")):
        assert heading in PAGE, f"{key} has no section on the page"
    measured = {k for k in RECORD if not k.startswith("_")
                and isinstance(RECORD[k], dict) and "still_defective" in RECORD[k]}
    assert measured == {"remove", "tenant", "merge"}, (
        f"the probe measures {sorted(measured)}; add a section for any new "
        f"one rather than leaving it recorded and unpublished")


def test_the_page_states_the_sharpened_tenant_finding_not_the_weak_one():
    """**"`tenant` is ignored" was unfalsifiable**, and the page said it for
    a round after the probe stopped supporting it.

    A field named `zzz_not_a_field` produces a byte-identical response, so
    the engine discards unknown body fields wholesale — keyed on "every
    tenant sees one graph" alone, the finding reads true forever, including
    on an engine with perfect isolation.

    The record carries the null control; the page a reader actually opens has
    to carry the conclusion it licenses.
    """
    tenant = RECORD["tenant"]
    assert tenant["reads_as_no_tenant_parameter"] is True, (
        "the record no longer supports the page's claim")
    assert "no tenant parameter on `/api/query` at all" in PAGE
    assert "zzz_not_a_field" in PAGE, (
        "the page states the conclusion without the control that licenses it")
    assert str(tenant["count_under_a_nonsense_field"]) in PAGE


def test_the_page_says_how_many_times_each_rate_was_measured():
    """The #169 verdict landed inside its own noise band on a single draw —
    MATCH fell 1.9x against a 2.0x rule. A page quoting the figures without
    saying how many draws produced them cannot be compared with a re-run."""
    merge = RECORD["merge"]
    assert merge["repeats_per_rate"] >= 3, (
        "the record was taken with fewer draws than the page describes")
    assert f"median of {merge['repeats_per_rate']} measurements" in PAGE
    assert f"{merge['match_fell_by']}x" in PAGE


def test_every_merge_rate_on_the_page_is_the_measured_one():
    """The table's own cells, not just its shape. A row can be edited while
    the record says something else and nothing notices — which is how the
    page kept a superseded table for a round."""
    for point in RECORD["merge"]["points"]:
        row = (f"| {point['requested_size']:,} | {point['merge_per_sec']} | "
               f"{point['create_per_sec']} | {point['match_per_sec']} |")
        assert row in PAGE, f"the page does not carry the measured row: {row}"

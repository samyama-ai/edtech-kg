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
        assert int(row[0].replace(",", "")) == point["nodes_in_label"]
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


def test_the_remove_section_quotes_what_was_observed():
    assert stated(r"REMOVE p\.kind RETURN p\.kind`\nreturned `'([^']+)'`") == \
        REMOVE["remove_then_return_gave"]
    assert REMOVE["property_survives_remove"] is True, (
        "REMOVE now works — the page and #163 both need rewriting, which is "
        "the best possible reason for this to fail")


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

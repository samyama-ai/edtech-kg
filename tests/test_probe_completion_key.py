"""The key-collision measurement, driven without the cached slice.

edtech-kg#7. The figures behind the `Completion` key fix — 190,770 rows,
16,800 groups carrying more than one `majornum`, 3,524 of them losing a count
— were measured once by hand and then written into three files. Three copies
of a number with no run behind it is the failure this repo has had most
often, and the probe exists to give them one.

Nothing here reads `data/`; the rows are constructed so each assertion names
the case it is about.
"""

from __future__ import annotations

import json

import pytest

from etl import probe_completion_key as probe


def row(**over):
    base = {"unitid": 1, "cipcode_6digit": 110701, "award_level": 5,
            "majornum": 1, "race": 1, "sex": 1, "awards_6digit": 3}
    return {**base, **over}


def drive(monkeypatch, rows):
    monkeypatch.setattr(probe, "held", lambda name, cache=None: {"rows": rows})
    return probe.measure()


def test_two_majors_with_awards_are_a_group_that_loses_a_count(monkeypatch):
    """**The case the whole fix is about.** Two real completions differing
    only by `majornum`, both with awards: the five-part key merges them and
    one award count disappears."""
    found = drive(monkeypatch, [row(majornum=1, awards_6digit=3),
                                row(majornum=2, awards_6digit=1)])
    assert found["groups_the_five_part_key_merges"] == 1
    assert found["groups_with_more_than_one_majornum"] == 1
    assert found["groups_losing_a_count"] == 1
    assert found["awards_lost"] == 1, (
        "the smaller of the two counts is what disappears")


def test_a_merge_where_only_one_row_has_awards_loses_nothing(monkeypatch):
    """**The distinction that makes 16,800 the wrong headline.** A group can
    merge two rows and lose nothing, because the other row is a zero. Quoting
    the larger number as "completions lost" overstates it by nearly five
    times, and the record keeps both so the page cannot pick the wrong one by
    accident."""
    found = drive(monkeypatch, [row(majornum=1, awards_6digit=3),
                                row(majornum=2, awards_6digit=0)])
    assert found["groups_with_more_than_one_majornum"] == 1
    assert found["groups_losing_a_count"] == 0
    assert found["awards_lost"] == 0


def test_rows_that_differ_outside_majornum_are_not_a_merge(monkeypatch):
    """A group is only a merge if the five parts agree. Counting rows that
    differ by CIP or demographic would inflate every figure here."""
    found = drive(monkeypatch, [row(cipcode_6digit=110701),
                                row(cipcode_6digit=110702),
                                row(race=2)])
    assert found["groups_the_five_part_key_merges"] == 0
    assert found["groups_losing_a_count"] == 0


def test_the_six_part_key_separates_what_the_five_part_key_merges(monkeypatch):
    """The two key counts are the before and after of the fix, in one run."""
    found = drive(monkeypatch, [row(majornum=1), row(majornum=2)])
    assert found["distinct_five_part_keys"] == 1
    assert found["distinct_six_part_keys"] == 2


def test_a_duplicate_row_merges_without_more_than_one_majornum(monkeypatch):
    """Byte-identical rows merge too, and they are NOT the finding — 169 of
    those exist in this slice and lose nothing. Counting them as key
    collisions would attribute a real defect to a harmless duplicate."""
    found = drive(monkeypatch, [row(), row()])
    assert found["groups_the_five_part_key_merges"] == 1
    assert found["groups_with_more_than_one_majornum"] == 0
    assert found["groups_losing_a_count"] == 0


def test_recording_an_empty_slice_is_refused(monkeypatch, tmp_path, capsys):
    """A slice with no rows measures nothing, and writing that over a real
    measurement turns a record of something into a record of nothing."""
    monkeypatch.setattr(probe, "RECORD", tmp_path / "spine-key.json")
    monkeypatch.setattr(probe, "held", lambda name, cache=None: {"rows": []})
    assert probe.main(["--record"]) == 3
    assert "no rows" in capsys.readouterr().err
    assert not (tmp_path / "spine-key.json").exists()


def test_json_and_record_are_refused_together(capsys):
    """Opposite intentions — print without touching the tree, and write to
    it. One silently winning is the worse outcome."""
    assert probe.main(["--json", "--record"]) == 2
    assert "pick one" in capsys.readouterr().err


def test_the_committed_record_and_the_schema_agree(monkeypatch):
    """**Three files carried these figures and no run produced them.** The
    schema comment, the loader's docstring and the page all quote them; this
    is the only place they come from now.
    """
    import pathlib
    if not probe.RECORD.exists():
        pytest.skip("no committed record yet")
    found = json.loads(probe.RECORD.read_text(encoding="utf-8"))
    schema = (pathlib.Path(probe.ROOT) / "schema" / "edtech_kg.cypher"
              ).read_text(encoding="utf-8")
    for figure in ("rows", "groups_with_more_than_one_majornum",
                   "groups_losing_a_count"):
        assert f"{found[figure]:,}" in schema, (
            f"the schema does not carry the measured {figure} "
            f"({found[figure]:,})")


def test_the_committed_record_was_written_by_a_clean_tree():
    """**The figures the schema comment and the page lead with were taken on
    an uncommitted tree.** The record was stamped `dirty: true` at the
    previous head while `measure()` itself changed in the commit after it, so
    nothing committed anywhere could reproduce them.

    `test_national_spine_doc.py` enforces this for the spine record and
    nothing enforced it here, which is the whole reason it passed. This probe
    reads a local file and runs in seconds — there is no cost to re-running
    it from a clean tree.
    """
    if not probe.RECORD.exists():
        pytest.skip("no committed record yet")
    code = json.loads(probe.RECORD.read_text(encoding="utf-8"))["code"]
    assert code["dirty"] is False, (
        "the record was written from a dirty tree, so its figures cannot be "
        "reproduced from any commit — re-run `python -m "
        "etl.probe_completion_key --record` on a clean tree")
    assert code["commit"] != "unknown"


def test_completions_lost_and_awards_lost_are_different_quantities(monkeypatch):
    """**They were conflated, and the wrong one was the headline.**

    `awards_lost` SUMS award counts across the groups that lose one.
    `completions_lost` counts NODES. 23,126 was reported on the page, in the
    schema comment and in the PR body as "completions that disappear"; it is
    neither a count of nodes nor comparable to one.

    Two rows differing only by majornum, carrying 3 awards and 1: one node
    disappears, and one award count of 1 goes with it.
    """
    found = drive(monkeypatch, [row(majornum=1, awards_6digit=3),
                                row(majornum=2, awards_6digit=1)])
    assert found["completions_lost"] == 1
    assert found["awards_lost"] == 1
    # And they diverge as soon as the surviving count is not 1.
    bigger = drive(monkeypatch, [row(majornum=1, awards_6digit=3),
                                 row(majornum=2, awards_6digit=9)])
    assert bigger["completions_lost"] == 1
    assert bigger["awards_lost"] == 3, (
        "awards_lost is a sum of award counts; it tracks the awards, not the "
        "nodes")


def test_completions_lost_is_the_two_key_counts_subtracted(monkeypatch):
    """It is derivable from figures already in the record, which is what
    makes it checkable without re-running anything."""
    found = drive(monkeypatch, [row(majornum=1), row(majornum=2),
                                row(cipcode_6digit=999999)])
    assert found["completions_lost"] == (found["distinct_six_part_keys"]
                                         - found["distinct_five_part_keys"])


def test_why_two_of_the_figures_coincide(monkeypatch):
    """`majornum` takes exactly two values in this slice, so a merging group
    holds exactly two six-part keys and loses exactly one node — which is why
    `completions_lost` and `groups_with_more_than_one_majornum` are the same
    number. Recorded so the coincidence is checkable rather than surprising,
    and so a third value would break this rather than pass silently."""
    found = drive(monkeypatch, [row(majornum=1), row(majornum=2)])
    assert found["majornum_values"] == [1, 2]
    assert found["completions_lost"] == found["groups_with_more_than_one_majornum"]

    three = drive(monkeypatch, [row(majornum=1), row(majornum=2),
                                row(majornum=3)])
    assert three["majornum_values"] == [1, 2, 3]
    assert three["completions_lost"] == 2, "one group, three keys, two lost"
    assert three["groups_with_more_than_one_majornum"] == 1, (
        "with three majornum values the two figures must diverge")

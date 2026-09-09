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

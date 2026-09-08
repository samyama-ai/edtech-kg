"""A backfilled provenance stamp, and what keeps it from passing as a live one.

#171 landed `write_record` while #173 and #175 were already in flight, so three
records were measured against a tree where the stamped writer did not exist.
Each branch was green alone; main went red the moment the pair landed.

Re-running is the better fix and was tried first — Census TIGER answered
HTTP 520 on 2026-09-07. So the records are annotated instead, and the whole
risk of doing that is a weaker stamp being read as a strong one. That is what
this file guards.
"""

from __future__ import annotations

import json
import pathlib
import subprocess

import pytest

from etl import provenance

ROOT = pathlib.Path(__file__).resolve().parent.parent
RECORDS = sorted((ROOT / "docs" / "sources").glob("*.json"))

#: The three records measured while `write_record` was in flight on #171.
#: **This list may only shrink** — the same ratchet as `UNSTAMPED`, and for
#: the same reason. A record leaves it by being RE-MEASURED, which replaces
#: the weak stamp with a live one; it must not leave by having its marker
#: deleted.
#:
#: Named rather than discovered. Deriving this list by looking for the
#: `backfilled` key was the first version, and mutation-testing found the
#: hole immediately: deleting the marker from a record dropped it out of the
#: list, so every check below simply stopped running on it and the suite
#: stayed green. A guard whose subject is defined by the thing it guards
#: against cannot catch it.
EXPECTED_BACKFILL = {
    "florida-registry-measured.json",
    "geography-measured.json",
    "prerequisite-sweep-measured.json",
}
BACKFILLED = [r for r in RECORDS if r.name in EXPECTED_BACKFILL]


def test_every_expected_backfill_still_exists_and_is_marked():
    """Catches the marker being deleted, and the record being renamed away.

    Both leave the parametrised tests below iterating a shorter list, which is
    the failure mode that passes silently.
    """
    present = {r.name for r in RECORDS}
    missing = sorted(EXPECTED_BACKFILL - present)
    assert not missing, (
        f"named as backfilled but not present: {missing}. If the record was "
        f"renamed, rename it here; if it was deleted, remove the entry.")

    for record in BACKFILLED:
        stamp = json.loads(record.read_text(encoding="utf-8")).get("code") or {}
        assert "backfilled" in stamp, (
            f"{record.name} is named in EXPECTED_BACKFILL and carries no "
            f"`backfilled` marker. If it was re-measured, delete its entry — "
            f"the list is a ratchet and may only shrink.")


def test_no_record_is_marked_backfilled_without_being_named():
    """The other direction. A new record written with a backfilled stamp —
    rather than re-measured — must be a deliberate, visible act."""
    unnamed = sorted(
        r.name for r in RECORDS
        if r.name not in EXPECTED_BACKFILL
        and "backfilled" in (json.loads(r.read_text("utf-8")).get("code") or {}))
    assert not unnamed, (
        f"{unnamed} carry backfilled stamps and are not named above. A "
        f"backfill bounds the code behind a figure rather than naming it; "
        f"new records should be measured, not annotated.")


@pytest.mark.parametrize("record", BACKFILLED, ids=lambda p: p.name)
def test_a_backfilled_stamp_names_a_commit_that_touched_that_record(record):
    """The one thing that makes the annotation true rather than decorative.

    A backfill could name any commit — HEAD, a guess, the same hash for every
    file. This asserts git agrees the named commit actually changed THIS file,
    which is the only claim the stamp is entitled to make.
    """
    stamp = json.loads(record.read_text(encoding="utf-8"))["code"]
    touched = subprocess.run(
        ["git", "log", "--format=%H", "--", str(record.relative_to(ROOT))],
        cwd=ROOT, capture_output=True, text=True, check=False).stdout.split()
    assert touched, f"git knows no history for {record.name}"
    assert stamp["commit"] in touched, (
        f"{record.name} is stamped {stamp['commit'][:12]}, which never "
        f"changed this file. A backfilled stamp that names an unrelated "
        f"commit is worse than none.")


@pytest.mark.parametrize("record", BACKFILLED, ids=lambda p: p.name)
def test_a_backfilled_stamp_says_it_is_one(record):
    """`test_a_committed_record_is_stamped_or_listed_as_not` accepts any dict
    with commit/dirty/package. A backfill satisfies it while proving less, so
    the difference has to be readable IN the record — not only in this file."""
    stamp = json.loads(record.read_text(encoding="utf-8"))["code"]
    assert set(stamp) >= {"commit", "dirty", "package", "backfilled"}
    said = stamp["backfilled"]
    assert isinstance(said, str) and "predates" in said, (
        "the marker must say WHY the stamp is weaker, not merely that it is — "
        "a bare `true` tells the next reader nothing")


def test_the_backfill_refuses_when_git_cannot_name_a_commit(tmp_path, monkeypatch):
    """None, never a stamp with a hole. A file git has never seen must not be
    given a commit, and the caller must be able to tell."""
    monkeypatch.setattr(provenance, "commit_that_committed", lambda p: None)
    assert provenance.backfill_stamp(tmp_path / "nothing.json") is None
    assert provenance.commit_that_committed(tmp_path / "untracked.json") is None


def test_a_backfilled_stamp_is_not_dirty_by_reading_this_working_tree():
    """`dirty` must describe the tree that produced the record, not the one
    running the test. Copying it from `code_version()` would make the stamp
    change depending on who ran the backfill."""
    stamp = provenance.backfill_stamp(BACKFILLED[0])
    assert stamp["dirty"] is False


def test_the_cli_refuses_a_record_that_already_has_a_stamp(tmp_path):
    """Overwriting a live stamp with a backfilled one replaces strong evidence
    with weak, and looks like a routine re-run in the diff."""
    record = tmp_path / "already-measured.json"
    record.write_text(json.dumps({"n": 1, "code": {"commit": "abc",
                                                   "dirty": False,
                                                   "package": "0.1.0"}}),
                      encoding="utf-8")
    assert provenance.main(["--backfill", str(record)]) == 3
    assert json.loads(record.read_text("utf-8"))["code"]["commit"] == "abc", (
        "the record was modified despite the refusal")


def test_the_cli_refuses_a_record_git_does_not_know(tmp_path):
    """Exit code, not a stamp naming whatever git said about some other file."""
    record = tmp_path / "untracked.json"
    record.write_text(json.dumps({"n": 1}), encoding="utf-8")
    assert provenance.main(["--backfill", str(record)]) == 4
    assert "code" not in json.loads(record.read_text("utf-8"))


def test_the_cli_refuses_a_record_that_is_not_there(tmp_path):
    assert provenance.main(["--backfill", str(tmp_path / "absent.json")]) == 2


def test_the_cli_stamps_a_tracked_record_and_keeps_its_payload(tmp_path):
    """The path that actually runs. Asserted end to end rather than through
    `backfill_stamp` alone — the first backfill in this repo was done by an
    UNCOMMITTED script, so the records changed and nothing committed could say
    how. That is the objection this CLI answers, and a test that never drives
    the CLI would leave it unanswered.
    """
    tracked = ROOT / "docs" / "sources" / "sced-measured.json"
    payload = json.loads(tracked.read_text(encoding="utf-8"))
    assert "code" not in payload, (
        "sced-measured.json now carries a stamp; pick another UNSTAMPED "
        "record for this test rather than deleting the assertion")

    scratch = tmp_path / "sced-measured.json"
    scratch.write_text(json.dumps(payload), encoding="utf-8")
    # Named for a real tracked path so git can answer, written to a scratch
    # copy so the test cannot modify a committed record.
    stamp = provenance.backfill_stamp(tracked)
    assert stamp and stamp["commit"], "git could not date a tracked record"
    scratch.write_text(json.dumps({**payload, "code": stamp}), encoding="utf-8")

    after = json.loads(scratch.read_text(encoding="utf-8"))
    assert after["code"]["backfilled"], "the marker did not survive the write"
    assert {k: v for k, v in after.items() if k != "code"} == payload, (
        "stamping changed the measurement it was describing")

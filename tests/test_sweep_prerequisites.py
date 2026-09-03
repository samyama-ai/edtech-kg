"""The full-Registry sweep: resumability, and the refusal to report a prefix.

The figures this produces replace `docs/sources/ctdl.md`'s "zero in 600", so
the failure that matters is not a crash — it is a sweep that dies at page 900,
reports what it has, and gets read as a census. Most of what follows tests the
refusals.

Nothing here reaches the network. The real run is an hour long; a test that
made it would be measuring the Registry's uptime.
"""

import json
import pathlib

import pytest

from etl import sweep_prerequisites as sweep
from etl.registry_read import MalformedSource
from tests.registry_stubs import course, paged, prereq


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Every test gets its own checkpoint and record.

    Without this the suite writes `data/prerequisite-sweep-progress.json` in
    the working copy and a developer's real half-finished sweep is destroyed by
    running the tests.
    """
    monkeypatch.setattr(sweep, "CHECKPOINT", tmp_path / "progress.json")
    monkeypatch.setattr(sweep, "RECORD", tmp_path / "record.json")
    return tmp_path


def pages(monkeypatch, by_page, population):
    paged(monkeypatch, by_page, x_total=population)


# --- the walk ---------------------------------------------------------------

def test_every_page_is_walked_and_the_totals_accumulate(monkeypatch):
    pages(monkeypatch, {1: [course(**prereq("PSYC101"))] * 3,
                        2: [course(**prereq("None"))] * 2,
                        3: [course()] * 4}, population=150)
    got = sweep.sweep(pages=3, quiet=True)
    assert got["courses"] == 9
    assert got["stating_a_prerequisite"] == 3
    assert got["stated_but_empty"] == 2
    assert got["complete"] is True


def test_the_page_count_covers_the_whole_population(monkeypatch):
    """958 pages for 47,862 courses — the last partial page must be read."""
    assert sweep.page_count(47862) == 958
    assert sweep.page_count(50) == 1
    assert sweep.page_count(51) == 2


def test_a_publisher_using_the_typed_edge_is_named(monkeypatch):
    """The whole point of #58 if the count is not zero: a bare count would say
    the term is used and leave nobody to go and look at."""
    envelope = course(**{"ceterms:prerequisite": [{"@id": "https://x.test/a"}]})
    envelope["published_by"] = "https://x.test/college"
    pages(monkeypatch, {1: [envelope]}, population=1)
    got = sweep.sweep(pages=1, quiet=True)
    assert got["using_the_typed_edge"] == 1
    assert got["typed_edge_publishers"] == {"https://x.test/college": 1}


def test_a_body_that_is_not_a_list_is_reported(monkeypatch):
    pages(monkeypatch, {1: {"error": "nope"}}, population=50)
    with pytest.raises(MalformedSource, match="page 1"):
        sweep.sweep(pages=1, quiet=True)


def test_a_population_that_is_not_a_number_refuses(monkeypatch):
    """`total()` returns "secured" or "error 500" as strings. Dividing one of
    those by 50 is a TypeError; treating it as zero is worse."""
    monkeypatch.setattr(sweep, "total", lambda *a, **k: "secured")
    with pytest.raises(RuntimeError, match="did not report a population"):
        sweep.sweep(quiet=True)


# --- resumability -----------------------------------------------------------

def test_a_checkpoint_is_written_after_every_page(monkeypatch, isolated):
    pages(monkeypatch, {1: [course()], 2: [course()]}, population=100)
    sweep.sweep(pages=2, quiet=True)
    saved = json.loads((isolated / "progress.json").read_text())
    assert saved["pages_read"] == [1, 2]
    assert saved["pages"] == 2


def test_resume_does_not_reread_a_page_already_read(monkeypatch, isolated):
    """The politeness requirement. A run that dies at page 900 and restarts
    from page 1 costs the Registry twice."""
    (isolated / "progress.json").write_text(json.dumps(
        {"pages_read": [1], "courses": 50, "states": 10, "resolves": 0,
         "empty": 1, "typed": 0, "examples": [], "typed_by_publisher": {},
         "pages": 2}))
    fetched = []

    def watched(url, *a, **k):
        fetched.append(url)
        return json.dumps([course()]).encode()
    monkeypatch.setattr(sweep, "get", watched)
    monkeypatch.setattr(sweep, "total", lambda *a, **k: 100)

    got = sweep.sweep(pages=2, resume=True, quiet=True)
    assert len(fetched) == 1 and "page=2" in fetched[0]
    assert got["courses"] == 51, "the checkpoint's 50 carry forward"
    assert got["stating_a_prerequisite"] == 10


def test_resume_refuses_when_the_plan_changed(monkeypatch, isolated):
    """Blending a 3-page partial into a 5-page run produces a rate over a
    population neither run measured."""
    (isolated / "progress.json").write_text(json.dumps(
        {"pages_read": [1, 2, 3], "courses": 150, "pages": 3}))
    monkeypatch.setattr(sweep, "total", lambda *a, **k: 250)
    with pytest.raises(ValueError, match="blending two populations"):
        sweep.sweep(pages=5, resume=True, quiet=True)


def test_without_resume_a_stale_checkpoint_is_ignored(monkeypatch, isolated):
    (isolated / "progress.json").write_text(json.dumps(
        {"pages_read": [1], "courses": 9999, "pages": 1}))
    pages(monkeypatch, {1: [course()]}, population=50)
    assert sweep.sweep(pages=1, quiet=True)["courses"] == 1


def test_a_checkpoint_write_is_not_left_half_finished(isolated):
    """Written to a scratch path and moved. A resume reading half a JSON file
    is worse than no resume at all."""
    progress = sweep.Progress()
    progress.add(1, [course()])
    sweep.save(progress, 5)
    assert json.loads((isolated / "progress.json").read_text())["pages"] == 5
    assert not (isolated / "progress.part").exists()


def test_the_checkpoint_is_never_opened_for_writing_directly(isolated,
                                                             monkeypatch):
    """The property the test above does NOT establish.

    Checking the end state passes just as happily for a non-atomic write —
    which a mutation proved: replacing the move with
    `CHECKPOINT.write_text(scratch.read_text())` left every assertion green.
    The atomicity is in HOW the final file appears, so that is what is tested:
    the checkpoint is produced by a rename, and nothing ever writes to its path.
    """
    real = pathlib.Path.write_text

    def refuse_direct(self, *args, **kwargs):
        if self == sweep.CHECKPOINT:
            raise AssertionError(
                "wrote the checkpoint in place; a kill here leaves a truncated "
                "file and a resume reads half a JSON document")
        return real(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "write_text", refuse_direct)
    progress = sweep.Progress()
    progress.add(1, [course()])
    sweep.save(progress, 5)
    assert json.loads(sweep.CHECKPOINT.read_text())["pages"] == 5


# --- the refusals that keep a prefix from reading as a census ---------------

def test_an_incomplete_sweep_is_marked_incomplete(monkeypatch):
    progress = sweep.Progress()
    progress.add(1, [course()])
    partial = sweep.shape(progress, population=47862, planned=958, elapsed=1.0)
    assert partial["complete"] is False
    assert partial["pages_read"] == 1


def test_an_incomplete_report_prints_no_rate(monkeypatch, capsys):
    progress = sweep.Progress()
    progress.add(1, [course(**prereq("PSYC101"))])
    sweep.report(sweep.shape(progress, 47862, 958, 1.0))
    printed = capsys.readouterr().out
    assert "INCOMPLETE" in printed
    assert "a prefix is not a census" in printed
    assert "stating a prerequisite" not in printed, (
        "an incomplete run must not print the figure a reader would quote")


def test_record_refuses_to_write_an_incomplete_sweep(monkeypatch, isolated):
    """The one this module exists for, and the bug it shipped with.

    Completeness is measured against the POPULATION, not against `--pages`.
    Measured against the plan, a 20-page run finishes its twenty pages and
    reports a census — the exact failure this module prevents, arriving
    through the flag added to make testing cheap.
    """
    pages(monkeypatch, {1: [course()]}, population=47862)
    assert sweep.main(["--record", "--pages", "20"]) == 1
    assert not (isolated / "record.json").exists()


def test_a_short_run_is_not_a_census(monkeypatch):
    pages(monkeypatch, {1: [course()]}, population=47862)
    got = sweep.sweep(pages=20, quiet=True)
    assert got["complete"] is False
    assert got["pages_in_population"] == 958 and got["pages_planned"] == 20


def test_record_writes_a_complete_sweep(monkeypatch, isolated):
    pages(monkeypatch, {1: [course(**prereq("PSYC101"))]}, population=50)
    assert sweep.main(["--record", "--pages", "1"]) == 0
    written = json.loads((isolated / "record.json").read_text())
    assert list(written)[:2] == ["_", "retrieved_at"]
    assert written["complete"] is True
    assert written["stating_a_prerequisite"] == 1


def test_the_examples_kept_are_bounded(monkeypatch):
    """~48k courses; keeping every example makes the record a copy of the
    Registry."""
    pages(monkeypatch, {1: [course(**prereq(f"COURSE{i}")) for i in range(50)]},
          population=50)
    got = sweep.sweep(pages=1, quiet=True)
    assert len(got["examples"]) == sweep.MAX_EXAMPLES


# --- exit codes -------------------------------------------------------------

@pytest.mark.parametrize("blows_up, code", [
    (ValueError("no"), 1),
    (MalformedSource("bad"), 3),
    (RuntimeError("gone"), 2),
])
def test_the_exit_categories_match_the_probes(monkeypatch, blows_up, code):
    def dies(*a, **k):
        raise blows_up
    monkeypatch.setattr(sweep, "sweep", dies)
    assert sweep.main([]) == code

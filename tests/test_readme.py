"""The front page held to the run that produced it.

edtech-kg#6 asks for a README that opens with **one question, one Cypher
query, one results table**. It has had all three for a while — after the
title, the animation, the badges and two paragraphs about what the project is.
Moving them to the top is the easy half.

**The half that matters is that nothing checked them.** The table on the front
page is the most-read set of figures in this repo and was the only one with no
record behind it: `docs/` figures are pinned to probes, `DATASET-CARD.md` is
pinned to eight of them, and the page a reader sees first was prose.

So `etl/probe_readme_question.py` runs the page's own query — character for
character, not a paraphrase — and these tests fail when the page and the
record disagree.

Nothing here needs an engine. The record is a committed run; this reads it.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

from etl import probe_readme_question as probe

ROOT = pathlib.Path(__file__).resolve().parents[1]
CAPABILITY = ROOT / "docs" / "sources" / "engine-capability-measured.json"
README = ROOT / "README.md"
RECORD_PATH = ROOT / "docs" / "sources" / "readme-question-measured.json"

PAGE = README.read_text(encoding="utf-8") if README.exists() else ""
RECORD = (json.loads(RECORD_PATH.read_text(encoding="utf-8"))
          if RECORD_PATH.exists() else {})


def test_the_record_behind_the_front_page_exists():
    """Named, so a rename fails one test rather than erroring the file."""
    assert RECORD_PATH.exists(), (
        f"{RECORD_PATH.relative_to(ROOT)} is missing; "
        f"`python -m etl.probe_readme_question --record` writes it")


def test_the_page_opens_with_the_question():
    """#6's actual ask: the house convention is question, query, table — not
    architecture. Measured as a position, not as presence: the question was
    already on the page, twenty lines below a badge.

    **Anchored on the page's own heading**, recorded verbatim. The first
    version reduced `RECORD["question"]` through `split(",")[0].split("If")[-1]
    .strip().split()[0]` to the single character `"I"`, so what it actually
    asserted was that some capital I appears before the gif and the badges.
    `IB Programme` in the table supplies one, so the test passed with the
    question anywhere on the page — including back at the bottom, the one
    regression it names in its own docstring.

    The record's `question` is the student's wording and the page's is the
    heading's; they are different sentences, so neither pinned the other.
    Both are recorded now and both are asserted.
    """
    assert RECORD["heading"] in PAGE, (
        f"the page's opening heading is not the recorded one\n"
        f"record: {RECORD['heading']!r}")
    before_question = PAGE.index(RECORD["heading"])
    for later in ("![", "img.shields.io", "## Demo"):
        assert PAGE.index(later) > before_question, (
            f"{later!r} comes before the question; the page still opens with "
            f"something other than what it can answer")


def test_the_probe_and_the_record_agree_on_what_was_asked():
    """**The missing link in "character for character".**

    Every other test here compares the PAGE against the RECORD — two
    artifacts. The constant that actually produced the record,
    `probe.QUERY`, was read by no test: nothing under `tests/` imported the
    module, only named it in prose. Verified — changing the probe's gate to
    `Chemistry` and its bound to `*1..3` left the whole suite green at
    1,841 passed.

    So "the probe runs the page's query" was true by authorship, not by
    construction: a probe edit not followed by `--record` left page, record
    and tests all agreeing while the probe measured something else. That is
    the case CONTRIBUTING names by hand — "drive the code, not the artifact.
    A test that reads a committed record says nothing about the code that
    wrote it."

    With this, the page-against-record tests cover the code transitively.
    """
    assert probe.QUERY == RECORD["query"], (
        "the probe's query is not the one in the record — re-run "
        "`python -m etl.probe_readme_question --record`")
    assert probe.HEADING == RECORD["heading"]
    assert probe.QUESTION == RECORD["question"]
    assert probe.BOUND == RECORD["bound"]
    assert probe.GATE == RECORD["gate"]


def test_the_query_on_the_page_is_the_query_that_was_run():
    """**A probe measuring a DIFFERENT query from the one printed** proves the
    page's table is reproducible by something nobody can see. Compared
    character for character, whitespace normalised."""
    fenced = re.search(r"```cypher\n(.*?)```", PAGE, re.S)
    assert fenced, "the page has no Cypher block"
    printed = " ".join(fenced.group(1).split())
    recorded = " ".join(RECORD["query"].split())
    assert printed == recorded, (
        f"the page runs a different query from the record\n"
        f"page:   {printed}\nrecord: {recorded}")


def test_every_row_of_the_table_is_the_measured_one():
    """Anchored to the subject, not just to the number — a table that carried
    the right counts against the wrong subjects would otherwise pass."""
    # **Not vacuous.** `for row in RECORD["table"]` iterates nothing when the
    # table is empty, so `table: []` plus a deleted README table passed all
    # eight tests. The probe now refuses to record an empty table; this is
    # the other half.
    assert RECORD["table"], "the record carries no table"
    for row in RECORD["table"]:
        assert re.search(rf"^\| {re.escape(row['subject'])} \| "
                         rf"{row['closed_off']} \|$", PAGE, re.M), (
            f"the page's row for {row['subject']!r} is not the measured one "
            f"({row['closed_off']})")


def test_the_sentence_under_the_table_is_measured_too():
    """"28 courses across 14 subjects" is a different question from the
    table, which is a top-five by subject. Both come from the same run."""
    assert f"{RECORD['closes_off']} courses across {RECORD['subjects']} " \
           f"subjects" in PAGE


def test_the_page_states_why_this_needs_a_graph_with_the_depth_that_shows_it():
    """**The strongest thing on the page, and it was not there.** Asked one
    hop at a time the answer is 9, 26, 28 and then stops — so a query over
    direct prerequisites only would report 9 and be wrong by two thirds.

    That is the argument for the whole repo, and it is measured.
    """
    depths = RECORD["distinct_by_depth"]
    one_hop, total = depths["1"], RECORD["closes_off"]
    assert one_hop < total, (
        "the transitive closure adds nothing on this data, so the page's "
        "argument for a graph needs re-making rather than re-wording")
    # **THE SEQUENCE, not just its endpoints.** `str(9) in PAGE` and
    # `str(28) in PAGE` were both satisfied by other figures on the page, so
    # changing "9, 26, 28" to "9, 26, 30" passed — mutation-verified. The
    # claim is the shape of the climb, so the climb is what is pinned.
    climb = [depths[str(d)] for d in sorted(int(k) for k in depths)]
    settled = climb.index(total)
    printed = ", ".join(str(n) for n in climb[:settled + 1])
    assert printed in PAGE, (
        f"the page does not carry the measured climb {printed!r}")
    # It stops growing — that is what makes the bound honest rather than
    # arbitrary.
    assert depths[str(max(int(d) for d in depths))] == total


def test_the_bound_in_the_query_is_past_where_the_answer_stops_growing():
    """`*1..8` on a district whose deepest chain is four. A bound BELOW the
    real depth would silently under-report; the record is what shows it is
    above."""
    depths = {int(d): n for d, n in RECORD["distinct_by_depth"].items()}
    settles = min(d for d, n in depths.items() if n == RECORD["closes_off"])
    bound = re.search(r"REQUIRES\*1\.\.(\d+)", RECORD["query"])
    assert bound, "the recorded query has no depth bound"
    assert int(bound.group(1)) >= settles, (
        f"the query stops at {bound.group(1)} hops and the answer is still "
        f"growing at {settles}")
    # **This much could not fail.** `BOUND` is derived from `QUERY` and the
    # climb runs `range(1, BOUND + 1)`, so `depths[BOUND] == closes_off` and
    # `bound >= settles` hold by construction — a catalogue that later grew a
    # nine-hop chain would report a short number with every test still green.
    #
    # `deepest_chain` is the independent measurement: `probe_engine_capability`
    # asks `REQUIRES*` UNBOUNDED, so it is not derived from this bound at all.
    deepest = json.loads(CAPABILITY.read_text(encoding="utf-8"))[
        "constructs"]["deepest_chain"]["value"]
    assert settles <= deepest < int(bound.group(1)), (
        f"the unbounded deepest chain is {deepest} hops; the page's answer "
        f"settles at {settles} and its query stops at {bound.group(1)}. The "
        f"bound is only honest while it sits above the real depth.")


def test_the_record_was_written_by_a_clean_tree():
    assert RECORD["code"]["dirty"] is False
    assert RECORD["code"]["commit"] != "unknown"


# ---------------------------------------------------------------------------
# The probe DRIVEN, not just read (edtech-kg#192).
#
# Everything above compares the page against the record. These run the module:
# 62 of 62 statements were unexecuted, so the refusals keeping a wrong figure
# off the front page of the repo had never fired in a test.


class FakeEngine:
    """An engine answering per-query, so `measure` can be driven offline.

    Keyed on a distinctive fragment of each statement rather than on call
    order — `measure` issues five kinds of query and a list would silently
    re-map if one moved.
    """

    def __init__(self, table=(), closed=(), subjects=(), courses=791,
                 edges=240, depths=None):
        self.table, self.closed, self.subjects = table, closed, subjects
        self.courses, self.edges = courses, edges
        self.depths = depths or {}
        self.asked = []

    def run(self, statement):
        self.asked.append(statement)
        if "count(DISTINCT blocked)" in statement:
            return {"records": [list(r) for r in self.table]}
        if "IN_SUBJECT" in statement:
            return {"records": [[s] for s in self.subjects]}
        if "count(c)" in statement:
            return {"records": [[self.courses]]}
        if "count(r)" in statement:
            return {"records": [[self.edges]]}
        if "REQUIRES*1.." in statement:
            depth = int(statement.split("REQUIRES*1..")[1].split("]")[0])
            names = self.depths.get(depth, self.closed)
            return {"records": [[n] for n in names]}
        return {"records": []}


def drive(monkeypatch, engine):
    monkeypatch.setattr(probe, "Engine", lambda url: engine)


def test_a_graph_with_no_subjects_is_refused_rather_than_recorded(
        monkeypatch, capsys):
    """**The refusal that had never run.** `closes_off` counts courses
    reached; the table needs `IN_SUBJECT` as well. A graph with Courses
    loaded and no subjects answers `closes_off: 28` beside an empty table —
    and the page-side test iterates that table, so an empty one passes
    vacuously while the README's table is deleted.
    """
    drive(monkeypatch, FakeEngine(table=(), closed=("Chemistry",),
                                  subjects=()))
    assert probe.main(["--url", "http://engine.test"]) == 3
    assert "grouped none of them into subjects" in capsys.readouterr().err


def test_an_empty_answer_is_refused_rather_than_put_on_the_front_page(
        monkeypatch, capsys):
    """The guard keeping "closes off 0 courses" off the repo's front page.
    An empty answer here is almost always an empty graph, and recording it
    would publish that as a measurement."""
    drive(monkeypatch, FakeEngine(table=(("Math", 3),), closed=(),
                                  subjects=("Math",)))
    assert probe.main(["--url", "http://engine.test"]) == 3
    assert "answered with nothing" in capsys.readouterr().err


def test_json_and_record_are_refused_together(monkeypatch, capsys):
    """Two different asks. Refused before the engine is touched, so a
    contradictory invocation costs nothing."""
    engine = FakeEngine(table=(("Math", 3),), closed=("Chemistry",),
                        subjects=("Math",))
    drive(monkeypatch, engine)
    assert probe.main(["--json", "--record"]) == 2
    assert "pick one" in capsys.readouterr().err
    assert engine.asked == [], "the engine was queried before the refusal"


def test_a_good_run_reports_and_records(monkeypatch, tmp_path, capsys):
    """The happy path, including the write — never executed either."""
    record = tmp_path / "readme-question-measured.json"
    monkeypatch.setattr(probe, "RECORD", record)
    monkeypatch.setattr(probe, "ROOT", tmp_path)
    drive(monkeypatch, FakeEngine(
        table=(("Math - Standard", 3), ("Science - IB Programme", 4)),
        closed=tuple(f"c{i}" for i in range(28)),
        subjects=tuple(f"s{i}" for i in range(14)),
        depths={d: tuple(f"c{i}" for i in range(9 if d == 1 else 28))
                for d in range(1, probe.BOUND + 1)}))
    assert probe.main(["--url", "http://engine.test", "--record"]) == 0
    written = json.loads(record.read_text(encoding="utf-8"))
    assert written["closes_off"] == 28
    assert written["subjects"] == 14
    assert written["query"] == probe.QUERY
    assert "28 courses across 14 subjects" in capsys.readouterr().out


def test_a_graph_answering_nothing_to_the_count_is_refused_not_recorded_as_zero(
        monkeypatch, capsys):
    """**`int(courses[0][0]) if courses else 0` wrote a 0 into the record**
    for a graph that answered nothing — and the README states these two as
    denominators: "out of 791 in the graph (240 REQUIRES edges)". An
    unmeasured denominator published as a measured one is the failure this
    probe exists to prevent, arriving through the fallback rather than
    through the answer.

    Same shape as `etl/snapshot.py:_count` and `etl/scratch_engine.py`, both
    of which record this guard failing open before.
    """
    class Countless(FakeEngine):
        def run(self, statement):
            if "count(c)" in statement or "count(r)" in statement:
                return {"records": []}
            return super().run(statement)

    engine = Countless(table=(("Math", 3),), closed=("a",), subjects=("Math",))
    drive(monkeypatch, engine)
    with pytest.raises(probe.Unmeasured, match="cannot be measured"):
        probe.measure("http://engine.test")
    # and `main` turns it into an exit code, not a traceback
    drive(monkeypatch, engine)
    assert probe.main(["--url", "http://engine.test"]) == 3
    assert "Refusing rather than recording a zero" in capsys.readouterr().err


def test_a_count_that_is_not_a_number_is_refused(monkeypatch):
    """`etl/engine.py` documents that answers come back typed however the
    engine felt like typing them, and `f"{n:,}"` on a string crashes the
    report rather than reporting the graph it found."""
    class Wordy(FakeEngine):
        def run(self, statement):
            if "count(c)" in statement:
                return {"records": [["seven hundred and ninety-one"]]}
            return super().run(statement)

    drive(monkeypatch, Wordy(table=(("Math", 3),), closed=("a",),
                             subjects=("Math",)))
    with pytest.raises(probe.Unmeasured, match="not a number"):
        probe.measure("http://engine.test")

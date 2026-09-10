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

ROOT = pathlib.Path(__file__).resolve().parents[1]
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


def test_the_record_was_written_by_a_clean_tree():
    assert RECORD["code"]["dirty"] is False
    assert RECORD["code"]["commit"] != "unknown"

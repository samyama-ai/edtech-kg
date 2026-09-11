"""Tests for the narrated demo.

No engine. `table`, `chosen` and the `QUESTIONS` structure are all pure, and
they are where the demo can fail in front of an audience — which is the one
place a traceback is most expensive.

The first of these guards a crash that shipped: `table()` raised `TypeError` on
an empty result set. Every query happens to return rows against the catalogue
loaded today, which is the only reason it never fired.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from demo import demo

ROOT = pathlib.Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------
# table() — the crash
# --------------------------------------------------------------------------

def test_an_empty_result_set_does_not_crash(capsys):
    """`max(len(h), *(…) if rows else len(h))` parses as
    `max(len(h), *(… if rows else len(h)))` — the star applies to the whole
    conditional, so an empty result unpacked an int.

    A demo against a district where every pathway lists its courses (Q4), or
    where 'Studio Art 5' is named differently (Q13), would have crashed
    mid-presentation. That is the failure `preflight` exists to prevent, one
    step further down.
    """
    demo.table(["subject", "closed off"], [], limit=12)
    printed = capsys.readouterr().out
    assert "subject" in printed and "closed off" in printed


def test_a_zero_row_limit_does_not_crash(capsys):
    demo.table(["a"], [["x"]], limit=0)
    assert "a" in capsys.readouterr().out


def test_a_column_is_as_wide_as_its_widest_cell(capsys):
    demo.table(["n"], [["short"], ["a much longer value"]], limit=12)
    lines = capsys.readouterr().out.splitlines()
    assert any("─" * len("a much longer value") in line for line in lines)


def test_rows_beyond_the_limit_are_reported_not_dropped(capsys):
    demo.table(["n"], [[i] for i in range(20)], limit=5)
    assert "15 more" in capsys.readouterr().out


# --------------------------------------------------------------------------
# chosen() — argument handling
# --------------------------------------------------------------------------

def test_no_argument_runs_every_question():
    assert demo.chosen(None) == list(range(len(demo.QUESTIONS)))
    assert demo.chosen("") == list(range(len(demo.QUESTIONS)))


def test_questions_run_in_the_order_given():
    assert demo.chosen("5,0,19") == [5, 0, 19]


def test_an_out_of_range_number_is_refused_with_a_message():
    with pytest.raises(SystemExit) as raised:
        demo.chosen("99")
    assert "99" in str(raised.value)


def test_a_non_number_is_refused_with_a_message_not_a_traceback():
    """The out-of-range case exited cleanly and this one raised a raw
    ValueError — a difference nobody chose."""
    with pytest.raises(SystemExit) as raised:
        demo.chosen("3,x")
    assert "x" in str(raised.value)


# --------------------------------------------------------------------------
# the question list, which drives order, narration and queries together
# --------------------------------------------------------------------------

def test_every_question_declares_a_tier_that_exists():
    for number, item in enumerate(demo.QUESTIONS):
        assert item["tier"] in demo.TIERS, f"Q{number} has tier {item['tier']}"


def test_every_query_is_a_headers_and_cypher_pair():
    for number, item in enumerate(demo.QUESTIONS):
        assert item["queries"], f"Q{number} runs no query"
        for entry in item["queries"]:
            assert len(entry) == 2, f"Q{number}: {entry}"
            headers, cypher = entry
            assert isinstance(headers, list) and headers, f"Q{number} has no headers"
            assert cypher.strip().upper().startswith("MATCH"), f"Q{number}: {cypher[:40]}"


def test_the_columns_returned_match_the_headers_declared():
    """A header list shorter than the columns silently drops one from the
    table; longer, and `zip` hides the mismatch. Counted from the query's own
    RETURN clause."""
    for number, item in enumerate(demo.QUESTIONS):
        for headers, cypher in item["queries"]:
            returned = cypher.upper().rsplit("RETURN", 1)[1]
            for clause in (" ORDER BY", " LIMIT"):
                returned = returned.split(clause)[0]
            # Commas inside a function call are not column separators.
            depth, columns = 0, 1
            for character in returned:
                depth += character in "(["
                depth -= character in ")]"
                columns += character == "," and depth == 0
            assert columns == len(headers), (
                f"Q{number} returns {columns} column(s), headers declare "
                f"{len(headers)}: {headers}")


def test_the_tiers_do_not_go_backwards():
    """The climb is the argument. A tier-4 question before a tier-2 one would
    invite the "couldn't you do that in Excel?" the order exists to answer."""
    tiers = [item["tier"] for item in demo.QUESTIONS]
    assert tiers == sorted(tiers), tiers


def test_the_meeting_set_advertised_in_the_help_is_runnable():
    """The docstring and `--only` help both name a set. If it drifts out of
    range the first thing anyone types fails."""
    import re
    advertised = set(re.findall(r"--only ([\d,]+)", demo.__doc__ or ""))
    assert advertised, "the docstring advertises no meeting set"
    for spelling in advertised:
        assert demo.chosen(spelling), spelling


def test_every_traversal_is_bounded_the_same_way():
    """Tier 5 was bounded at `*1..4` while tier 4 used `*1..8`. Same rows
    today — the deepest chain here is 4 — but "unknown depth" is the claim
    those questions make, and a tighter bound is a silent ceiling on it."""
    import re
    bounds = set()
    for item in demo.QUESTIONS:
        for _, cypher in item["queries"]:
            bounds |= set(re.findall(r"\*(\d+\.\.\d+)", cypher))
    assert len(bounds) <= 1, f"traversals are bounded inconsistently: {bounds}"


def test_every_order_by_names_a_source_expression_or_an_aggregate_alias():
    """The rule the module docstring spends a paragraph on, enforced.

    `RETURN length(p) AS d ORDER BY d` is silently unsorted in 1.1.0 while
    `ORDER BY length(p)` sorts; aggregate aliases are the exception and do
    work (#79). Every query here obeys it today — and that is exactly the
    invariant the next question someone adds will break, failing SILENTLY,
    which is the whole reason #79 exists. Documented is not guarded.
    """
    import re
    offenders = []
    for index, item in enumerate(demo.QUESTIONS):
        for _, cypher in item["queries"]:
            ordering = re.search(r"\bORDER BY\b(.*?)(?:\bLIMIT\b|\bSKIP\b|$)",
                                 cypher, re.S)
            if not ordering:
                continue
            # Aliases bound to an aggregate are the documented exception.
            # `[^)]*` does not survive a nested call: `sum(toFloat(e.credits))
            # AS credits` is an aggregate and was read as an ordinary alias.
            aggregates = set(re.findall(
                r"\b(?:count|sum|avg|min|max|collect)\s*\((?:[^()]|\([^()]*\))*\)"
                r"\s+AS\s+(\w+)", cypher))
            for term in ordering.group(1).split(","):
                term = re.sub(r"\b(?:ASC|DESC)\b", "", term).strip()
                if not term or term in aggregates:
                    continue
                # A bare identifier is an alias unless it appears in RETURN as
                # a source expression in its own right (`RETURN n.name … ORDER
                # BY n.name` is a source expression; `AS d … ORDER BY d` is not).
                if re.fullmatch(r"\w+", term):
                    bound = re.search(rf"\bAS\s+{re.escape(term)}\b", cypher)
                    if bound:
                        offenders.append(f"Q{index}: ORDER BY {term} (an alias)")
    assert not offenders, (
        "ORDER BY on a non-aggregate alias is silently ignored in 1.1.0 (#79); "
        f"name the source expression instead: {offenders}")


def test_the_order_by_guard_catches_the_form_it_exists_for():
    """A guard over a corpus that already complies proves nothing about the
    guard. Driven with the offending form directly, and with the nested-call
    aggregate that a looser pattern misread as an ordinary alias."""
    import re
    offending = ("MATCH (a)-[:R*1..8]->(b) RETURN length(p) AS d ORDER BY d")
    compliant = ("MATCH (p:Pathway)-[e:I]->(c:Course) RETURN p.name AS pathway, "
                 "sum(toFloat(e.credits)) AS credits ORDER BY credits DESC")

    def offends(cypher: str) -> bool:
        aggregates = set(re.findall(
            r"\b(?:count|sum|avg|min|max|collect)\s*\((?:[^()]|\([^()]*\))*\)"
            r"\s+AS\s+(\w+)", cypher))
        term = re.search(r"\bORDER BY\b\s+(\w+)", cypher).group(1)
        return term not in aggregates and bool(
            re.search(rf"\bAS\s+{re.escape(term)}\b", cypher))

    assert offends(offending), "the guard would not catch the form #79 is about"
    assert not offends(compliant), "an aggregate alias is the documented exception"


@pytest.fixture(autouse=True)
def _forget_held_counts():
    """`holds` caches per (url, graph, label). Two tests pointing different
    stub engines at the same URL would otherwise see each other's answers."""
    demo._HELD.clear()
    yield
    demo._HELD.clear()


def test_only_spine_labels_are_gated():
    """The district's own labels are guaranteed by `preflight`, so gating on
    one would hide a broken load behind a skip message."""
    for item in demo.QUESTIONS:
        if item.get("needs"):
            assert item["needs"] in ("Institution", "Programme", "Completion")


def test_the_spine_questions_type_no_figures():
    """The asides elsewhere quote the catalogue, which is fixed and measured.
    A spine aside quoting a number would be a second copy of a figure the
    query beside it already prints — and #187's whole review round was about
    exactly that drift. The wrong number is READ too, not asserted."""
    import re
    for item in demo.QUESTIONS:
        if not item.get("needs"):
            continue
        digits = re.findall(r"\d[\d,]{2,}", item.get("aside", ""))
        assert not digits, (
            f"Q{demo.QUESTIONS.index(item)}'s aside types {digits}; the "
            f"queries beside it print those figures from the engine")


def test_the_walkthrough_closes_by_saying_what_is_absent(monkeypatch, capsys):
    """edtech-kg#8 asks for this by name. A demo that closes on what it can
    do invites the room to assume the rest.

    **Driven through `main`, not read off the source.** `inspect.getsource`
    passed with the whole block commented out or unreachable.
    """
    monkeypatch.setattr(demo, "Engine",
                        lambda url, graph=None: Stub(SPINE_HELD))
    assert demo.main(["--only", "0", "--auto", "--url", "http://e.test"]) == 0
    printed = capsys.readouterr().out
    assert "What this graph does not hold" in printed
    for absent in ("occupations", "enrolment", "ZERO awards", "earnings",
                   "any student"):
        assert absent in printed, f"the closing does not name {absent!r}"


def test_the_zero_award_figure_comes_from_the_record(monkeypatch, capsys):
    """**A fourth typed copy of a figure three other files bind.**
    `docs/sources/national-spine-measured.json` carries
    `rows_skipped_zero_awards`, and `test_national_spine_doc`,
    `test_dataset_card` and `test_load_education_cli` all tie their quoted
    copies to it. The demo hardcoded 132,284 with no binding, and the test
    covering that block matched the WORDS — so the number could drift to
    anything and stay green.
    """
    record = json.loads(
        (ROOT / "docs" / "sources" / "national-spine-measured.json")
        .read_text(encoding="utf-8"))
    skipped = record["issued"]["rows_skipped_zero_awards"]
    monkeypatch.setattr(demo, "Engine",
                        lambda url, graph=None: Stub(SPINE_HELD))
    demo.main(["--only", "0", "--auto", "--url", "http://e.test"])
    assert f"{skipped:,} of them" in capsys.readouterr().out

    # **The binding, driven.** Comparing the output against the record's own
    # value passes for a TYPED number that happens to be right — which is
    # exactly the state this test exists to end. Move the record and the
    # closing has to move with it.
    monkeypatch.setattr(demo, "zero_award_rows_skipped", lambda: 999_001)
    demo.main(["--only", "0", "--auto", "--url", "http://e.test"])
    moved = capsys.readouterr().out
    assert "999,001 of them" in moved, (
        "the closing does not read the figure at run time — it is typed")
    assert f"{skipped:,} of them" not in moved


def test_the_closing_does_not_describe_a_load_this_graph_never_ran(
        monkeypatch, capsys):
    """Against the district-only snapshot the walkthrough has just skipped
    the spine question for having no `Completion`. Announcing two screens
    later how many zero-award rows were dropped reads, to the room, as
    describing this run."""
    monkeypatch.setattr(demo, "Engine", lambda url, graph=None: Stub())
    demo.main(["--only", "0", "--auto", "--url", "http://e.test"])
    printed = capsys.readouterr().out
    assert "ZERO awards" not in printed, (
        "a graph with no completions claimed rows were dropped from a load "
        "it never ran")
    assert "no institutions, programmes or completions" in printed


#: The district plus the spine — the shape after `etl/load_education.py`.
SPINE_HELD = {"Course": 791, "REQUIRES": 240, "Completion": 58317,
              "Institution": 147, "Programme": 664}


class Stub:
    """An engine holding the district and nothing else — the shape the
    published snapshot has."""

    def __init__(self, held=None):
        self.held = held or {"Course": 791, "REQUIRES": 240}
        self.asked = []

    def run(self, statement):
        self.asked.append(statement)
        if "n.source" in statement:
            # Q0's shape — three columns. A one-column answer here made the
            # column-width code raise IndexError rather than the test fail on
            # what it was checking.
            return {"records": [["catalog.pwcs.edu", "Course",
                                 self.held.get("Course", 0)]]}
        for name, n in self.held.items():
            if f":{name})" in statement or f":{name}]" in statement:
                return {"records": [[n]]}
        if "RETURN labels(n), count(n)" in statement:
            return {"records": [[["Course"], self.held.get("Course", 0)]]}
        if "MATCH (n) RETURN count(n)" in statement:
            return {"records": [[self.held.get("Course", 0)]]}
        return {"records": [[0]]}

    url = "http://engine.test"
    graph = "edtech"


def test_the_spine_question_is_skipped_when_the_spine_is_absent(monkeypatch,
                                                                capsys):
    """**Driven, not declared.** Asserting only that a question carries a
    `needs` key leaves the guard itself free to be deleted — verified: with
    the skip removed the suite stayed green. This runs the walkthrough against
    a district-only engine, which is exactly what `demo/ready.sh` produces
    from the published snapshot.
    """
    engine = Stub()
    monkeypatch.setattr(demo, "Engine", lambda url, graph=None: engine)
    spine = next(i for i, q in enumerate(demo.QUESTIONS) if q.get("needs"))
    assert demo.main(["--only", str(spine), "--auto",
                      "--url", "http://engine.test"]) == 0
    printed = capsys.readouterr().out
    assert f"Q{spine} skipped" in printed, printed[-600:]
    assert "load_education" in printed, "the skip does not say how to fix it"
    # and it did not run the question's queries anyway
    assert not any("cip_code" in q for q in engine.asked), (
        "the skipped question still queried the engine")


def test_the_header_counts_the_questions_it_will_actually_ask(monkeypatch,
                                                              capsys):
    """A district-only run promised one more question than it asked: the
    count was taken before the gate, so a skipped question was still
    advertised."""
    spine = next(i for i, q in enumerate(demo.QUESTIONS) if q.get("needs"))
    monkeypatch.setattr(demo, "Engine", lambda url, graph=None: Stub())
    demo.main(["--only", f"0,{spine}", "--auto", "--url", "http://e.test"])
    printed = capsys.readouterr().out
    assert "1 question." in printed, (
        "the header promised a question the gate went on to skip")
    assert f"Q{spine} skipped" in printed


def test_a_missing_record_drops_the_figure_rather_than_the_demo(monkeypatch,
                                                                capsys):
    """**It fires at the CLOSING screen, after a successful run.** A bare
    `read_text` + `json.loads` + two subscripts raised `FileNotFoundError` or
    `KeyError` in front of the audience — the failure mode every other read
    path in this module converts into a clean message.
    """
    monkeypatch.setattr(demo, "ROOT", pathlib.Path("/nonexistent"))
    monkeypatch.setattr(demo, "Engine",
                        lambda url, graph=None: Stub(SPINE_HELD))
    assert demo.main(["--only", "0", "--auto", "--url", "http://e.test"]) == 0
    printed = capsys.readouterr().out
    assert "ZERO awards" in printed, "the line vanished with the figure"
    assert "of them" not in printed, "a figure was printed from no record"
    assert "dropped by the recorded load" in printed


def test_the_answer_table_obeys_the_axis_rule_the_aside_teaches():
    """**The answer slide must not break the rule the demo just taught.**
    The aside explains that `major_number` is a separate axis and that mixing
    it counts a student twice; the per-college table then summed both, so
    anyone who followed the aside could tear the answer up.

    The DISTINCT institution count is deliberately unfiltered — a college is
    one college however many rows it files — and says so in its header.
    """
    spine = next(q for q in demo.QUESTIONS if q.get("needs"))
    # The ANSWER — the per-college table. The single-figure queries above it
    # deliberately vary one axis at a time to demonstrate the trap, so they
    # are not held to this; the slide that answers the question is.
    table = [q for q in spine["queries"] if "college" in q[0]]
    assert len(table) == 1, f"expected one answer table, found {len(table)}"
    headers, cypher = table[0]
    assert "major_number = 1" in cypher, (
        f"{headers} sums awards across first and second majors, which the "
        f"aside names as an error — an audience member who followed it can "
        f"tear the answer slide up")
    assert "first majors" in " ".join(headers), (
        "the column does not say which majors it counts")

    distinct = [q for q in spine["queries"] if "DISTINCT" in q[1]]
    assert distinct, "no institution count to check"
    for headers, _ in distinct:
        assert "counted once" in headers[0], (
            "the unfiltered count does not explain why it is unfiltered")

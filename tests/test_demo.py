"""Tests for the narrated demo.

No engine. `table`, `chosen` and the `QUESTIONS` structure are all pure, and
they are where the demo can fail in front of an audience — which is the one
place a traceback is most expensive.

The first of these guards a crash that shipped: `table()` raised `TypeError` on
an empty result set. Every query happens to return rows against the catalogue
loaded today, which is the only reason it never fired.
"""

from __future__ import annotations

import pytest

from demo import demo


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

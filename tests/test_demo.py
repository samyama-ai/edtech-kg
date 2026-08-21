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

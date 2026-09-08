"""`docs/sources/articulation.md` held to the record that produced it.

The page answers edtech-kg#42 — can an edge from a high-school course to
college credit be sourced — and its answer re-rates a question in
`docs/questions.md`. A figure that drifts here changes what the graph claims
it can compute.

Whitespace is collapsed before matching, so reflowing prose that has not
changed does not fail these and nobody learns to loosen the guard.

Nothing reaches the network.
"""

from __future__ import annotations

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "sources" / "articulation.md"
RECORD = json.loads((ROOT / "docs" / "sources"
                     / "articulation-measured.json").read_text("utf-8"))
PAGE = re.sub(r"\s+", " ", DOC.read_text(encoding="utf-8"))
INST = RECORD["institution_level"]
COURSE = RECORD["course_level"]
CRDC = RECORD["crdc"]


def test_every_credit_flag_has_a_row_and_every_row_is_measured():
    """The table IS the institution-level half of the answer."""
    assert INST["flags"], "no flags measured; the page's yes rests on nothing"
    for flag, found in INST["flags"].items():
        row = re.search(
            rf"\| `{re.escape(flag)}` \| ([\d,]+) \| ([\d,]+) \| \*\*([\d.]+)%\*\* \|",
            PAGE)
        assert row, f"{flag}'s row no longer parses"
        assert int(row.group(1).replace(",", "")) == found["grants"]
        assert int(row.group(2).replace(",", "")) == found["does_not"]
        assert float(row.group(3)) == found["percent_of_answered"]


def test_the_institution_count_is_a_census():
    """"3,240 institutions grant AP credit" is a national figure only if every
    institution was asked. The probe checks the returned rows against the
    API's own count; this checks the page quotes that population."""
    said = re.search(r"\*\*([\d,]+) institutions\*\*", PAGE)
    assert said, "the page no longer states the population"
    assert int(said.group(1).replace(",", "")) == INST["institutions"]
    for flag, found in INST["flags"].items():
        assert found["answered"] + sum(found["missing"].values()) == \
            INST["institutions"], (
            f"{flag} accounts for {found['answered']} answered plus "
            f"{found['missing']} missing, which is not {INST['institutions']}")


def test_the_course_level_zero_is_the_measured_one():
    """The half of the answer that is a NO, and the reason Q4 gets re-rated."""
    said = re.search(r"\*\*(\d+) of the (\d+) endpoints\*\*", PAGE)
    assert said, "the page no longer states the course-level search"
    assert int(said.group(1)) == len(COURSE["matched"])
    assert int(said.group(2)) == COURSE["searched"]
    assert COURSE["matched"] == [], (
        f"an endpoint now matches a course-level term: {COURSE['matched']}. "
        f"The page's no no longer holds and needs rewriting, not re-running.")
    for term in COURSE["terms"]:
        assert f"`{term}`" in PAGE, (
            f"the page must name every term searched, or the zero is a claim "
            f"about an unstated search; {term!r} is missing")


def test_the_crdc_table_shows_what_is_missing_not_only_what_is_there():
    """"Not one names an institution or a credit amount" is the finding. A
    table listing only row counts would read as three sources that might
    work."""
    for name, found in CRDC.items():
        row = re.search(rf"\| `{re.escape(name)}` \| ([\d,]+) \|", PAGE)
        assert row, f"{name}'s row no longer parses"
        assert int(row.group(1).replace(",", "")) == found["rows"]
        assert not found["names_an_institution"], (
            f"{name} now names an institution ({found['names_an_institution']}); "
            f"a course-to-college edge may be sourceable and the page's "
            f"conclusion needs revisiting")
        assert not found["names_a_credit_amount"], (
            f"{name} now names a credit amount ({found['names_a_credit_amount']})")
    assert "Not one of the three names an institution" in PAGE


def test_the_page_says_which_question_this_re_rates():
    """The issue asks for exactly this if the answer is no: Q4 re-rated rather
    than left implying a route nobody can compute."""
    assert "Q4 should be re-rated" in PAGE
    assert "questions.md" in PAGE


def test_the_page_separates_what_it_can_and_cannot_answer():
    """The whole shape of the finding. Reporting only the no would hide a
    national, complete property the graph can use today; reporting only the
    yes would imply a route that does not exist."""
    assert "Answerable now" in PAGE
    assert "Not answerable from national data" in PAGE


def test_the_licence_position_is_stated_and_is_not_new():
    """A research page that quietly introduces an uncleared source is how the
    register in `docs/sources/README.md` stops meaning anything."""
    assert "ODC-By" in PAGE and "education-data.md" in PAGE


def test_the_page_states_what_it_does_not_establish():
    """One API. ASSIST is untested here rather than ruled out, and saying so
    is the difference between a bounded finding and an overreach."""
    assert "What this does not establish" in PAGE
    assert "ASSIST" in PAGE and "400" in PAGE
    assert RECORD["retrieved_at"] in PAGE, (
        "the ASSIST refusal is dated, because a host answering 400 today may "
        "answer 200 next month")

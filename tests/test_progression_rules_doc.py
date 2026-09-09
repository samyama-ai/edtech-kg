"""`docs/sources/progression-rules.md` held to the record that produced it.

The page answers edtech-kg#66 — are the rules joining the two tiers published
as data — and its conclusion is that four independent publishers made the
same design decision. That is a strong claim from four observations, so the
tests below hold the page to what was measured and to the caveats that bound
it.

Nothing reaches the network.
"""

from __future__ import annotations

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "sources" / "progression-rules.md"
RECORD = json.loads((ROOT / "docs" / "sources"
                     / "progression-rules-measured.json").read_text("utf-8"))
PAGE = re.sub(r"\s+", " ", DOC.read_text(encoding="utf-8"))
Q39, PROSE, Q93 = (RECORD["q39_admission_rules"], RECORD["published_as_prose"],
                   RECORD["q93_articulation"])


def test_the_flag_counts_are_the_measured_ones():
    """The table IS the finding: the flags fire, so "the substance is
    missing" is not "nobody collects this"."""
    for flag, n in Q39["institutions_requiring_coursework"].items():
        row = re.search(rf"\| `{re.escape(flag)}` \| ([\d,]+) \|", PAGE)
        assert row, f"{flag}'s row no longer parses"
        assert int(row.group(1).replace(",", "")) == n
    assert any(Q39["institutions_requiring_coursework"].values()), (
        "no coursework flag fires anywhere; the page's argument that the "
        "rule is collected-but-hollowed rests on them firing")


def test_the_zero_naming_a_course_is_the_measured_one():
    """The sentence the whole page turns on."""
    said = re.search(
        r"\*\*(\d+) of the (\d+) fields name a\s*course\.\*\*", PAGE)
    assert said, "the page no longer states the course-naming count"
    assert int(said.group(1)) == len(Q39["fields_naming_a_course"])
    assert int(said.group(2)) == Q39["fields"]
    assert Q39["fields_naming_a_course"] == [], (
        f"IPEDS now has a field naming coursework "
        f"({Q39['fields_naming_a_course']}); the page's conclusion no longer "
        f"holds and needs rewriting rather than re-running")


def test_the_census_is_stated():
    """"6,138 institutions and not one named course" is national only if
    every institution was asked; the probe checks the rows against the API's
    own count and the page quotes the population."""
    said = re.search(r"\*\*([\d,]+)\s*institutions\*\*", PAGE)
    assert said, "the page no longer states the population"
    assert int(said.group(1).replace(",", "")) == Q39["institutions"]


def test_every_prose_source_has_a_row_and_none_serves_json():
    """Four publishers, one design decision — so every one measured has to be
    on the page, and a source that started serving JSON breaks the claim."""
    for question, sources in PROSE.items():
        for name, found in sources.items():
            row = re.search(
                rf"\| {question.split(' ')[0]} \| {re.escape(name)} \| "
                rf"(\d+) \| ([\d,]+) \|", PAGE)
            assert row, f"{question}/{name}'s row no longer parses"
            assert int(row.group(1)) == found["status"]
            assert int(row.group(2).replace(",", "")) == found["bytes"]
            assert not found["is_json"], (
                f"{name} now serves JSON; the page says no source here does")


def test_q93_is_quoted_from_the_other_record_not_re_measured():
    """Two probes measuring one fact is two figures that can disagree."""
    assert Q93["available"] is True, (
        "articulation-measured.json is not committed, so Q93 rests on nothing")
    said = re.search(r"\*\*(\d+) of\s*(\d+) endpoints\*\* name a course-level rule",
                     PAGE)
    assert said, "the page no longer states Q93's figure"
    assert int(said.group(1)) == Q93["endpoints_naming_a_course_level_rule"]
    assert int(said.group(2)) == Q93["endpoints_searched"]
    assert pathlib.Path(Q93["source"]).name in PAGE, (
        "the page must name where Q93's figure comes from, or it reads as "
        "measured here")


def test_the_page_does_not_claim_the_rules_are_missing():
    """The overreach this finding invites. Every rule measured is published
    and readable; what is missing is the join."""
    assert "not missing datasets" in PAGE or "are not missing datasets" in PAGE
    assert "published and readable" in PAGE
    for overreach in ("no state publishes graduation requirements",
                      "colleges do not publish"):
        assert overreach not in PAGE.lower()


def test_the_403_is_stated_as_a_refusal_to_this_client():
    assert "refusal to" in PAGE and "none was sought" in PAGE


def test_the_page_separates_source_existence_from_extractability():
    """"Could this be extracted from prose" is a different question, and the
    page answering only the first is what keeps it honest."""
    assert "whether the prose could be extracted" in PAGE
    assert "only answers the second" in PAGE

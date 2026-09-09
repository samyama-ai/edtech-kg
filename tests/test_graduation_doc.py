"""`docs/sources/graduation-requirements.md` held to its record.

The page answers edtech-kg#41 — can a course plan be checked against a
graduation requirement — and the answer turns on a refusal. A refusal is a
claim about permission on a date, not about the requirements existing, and
the tests below hold the page to the narrower one.

Nothing reaches the network.
"""

from __future__ import annotations

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "sources" / "graduation-requirements.md"
RECORD = json.loads((ROOT / "docs" / "sources"
                     / "graduation-requirements-measured.json").read_text("utf-8"))
PAGE = re.sub(r"\s+", " ", DOC.read_text(encoding="utf-8"))
SOURCES = RECORD["sources"]


def test_every_source_has_a_row_and_every_row_is_measured():
    """Three sources, three verdicts. One left off the table is one whose
    absence changes the conclusion."""
    for name, found in SOURCES.items():
        row = re.search(
            rf"\| {re.escape(name)} \| (\d+) \| ([^|]+) \| ([^|]+) \| ([^|]+) \|",
            PAGE)
        assert row, f"{name}'s row no longer parses"
        assert int(row.group(1)) == found["robots_status"]
        refused = "refused" in row.group(2)
        assert refused is (not found["allowed"]), (
            f"{name}: the page says permission is "
            f"{'refused' if refused else 'allowed'} and the record disagrees")
        fetched = row.group(4).strip().startswith("yes")
        assert fetched is found["fetched"]


def test_nothing_disallowed_by_robots_was_fetched():
    """**The claim the page's last paragraph makes.** A probe that fetched
    first and asked afterwards has not asked, and this is what makes the
    gate real rather than described."""
    for name, found in SOURCES.items():
        if not found["allowed"]:
            assert found["fetched"] is False, (
                f"{name} was disallowed by robots.txt and fetched anyway")
            assert found["status"] is None, (
                f"{name} carries a page status, so it was requested")


def test_the_blanket_disallow_is_the_measured_one():
    """The finding. If ECS opens its reports host the answer changes, and
    this fails rather than the page going quietly stale."""
    ecs = SOURCES["ECS 50-state comparison"]
    assert ecs["allowed"] is False
    assert ecs["blanket_disallow"] is True, (
        "reports.ecs.org no longer publishes a blanket Disallow; the page's "
        "central claim needs rewriting rather than re-running")
    assert "`Disallow: /`" in PAGE


def test_the_federal_route_is_shown_to_cite_the_refused_compilation():
    """"Not an independent source" is a claim about provenance, so the SOURCE
    line has to be on the page rather than summarised."""
    nces = SOURCES["NCES state education reforms"]
    assert nces["cites"], "no SOURCE line was captured; the claim rests on it"
    quoted = nces["cites"][0][:60]
    assert quoted in PAGE, (
        f"the page does not quote the SOURCE line it argues from: {quoted!r}")
    assert "Education Commission of the States" in nces["cites"][0], (
        "the NCES table no longer credits ECS; the page's argument that the "
        "federal route is not independent no longer follows")


def test_no_shape_figures_are_quoted_from_the_wrong_table():
    """The NCES page is compulsory-attendance age. Reporting "97.6%
    structurable" from it would be a figure about the wrong subject sitting
    in a document about graduation requirements."""
    nces = SOURCES["NCES state education reforms"]
    assert "not_analysed" in (nces.get("shape") or {}), (
        "the NCES page was shape-analysed; it is not the compilation")
    assert "97.6" not in PAGE and "structurable" not in PAGE, (
        "a structurability figure is on the page, and no page carrying "
        "graduation requirements was ever read")


def test_the_page_does_not_claim_the_requirements_are_secret():
    """The overreach this finding invites. The requirements are public — in
    fifty statutes — and what is missing is a normalised machine-readable
    version we may use."""
    assert "The requirements themselves are public" in PAGE
    for overreach in ("the requirements are not published",
                      "states do not publish"):
        assert overreach not in PAGE.lower()


def test_the_refusal_is_stated_as_being_to_this_client():
    """ECS licenses its compilations. An agreement would settle it and none
    was sought — saying so is the difference between "we may not" and
    "nobody may"."""
    assert "refusals\nto *this* client" in DOC.read_text("utf-8") or \
        "refusals to *this* client" in PAGE
    assert "None was sought" in PAGE


def test_the_page_points_at_the_rule_for_what_to_say_instead():
    """The issue's real requirement: the schema must not make "you will
    graduate" easy to state by accident."""
    assert "meets the prerequisite" in PAGE
    assert "scope.md" in PAGE

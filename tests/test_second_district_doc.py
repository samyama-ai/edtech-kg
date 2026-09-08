"""`docs/sources/second-district.md` held to the record that produced it.

The page answers edtech-kg#19 — does a second district's prerequisites resolve
the way PWCS's do — and the answer decides what kind of product this is. A
figure that drifts here changes a business conclusion, not a footnote.

**Whitespace is collapsed before matching.** The first version anchored on the
source's line wrap (`in the\\nfield`, `of\\n(\\d+)`), so reflowing prose that had
not changed failed the tests — which trains the next person to loosen the
guard rather than fix the page.

Nothing reaches the network.
"""

from __future__ import annotations

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "sources" / "second-district.md"
RECORD = json.loads((ROOT / "docs" / "sources"
                     / "second-district-measured.json").read_text("utf-8"))
RAW = DOC.read_text(encoding="utf-8")
#: One line, so a pattern spans a wrap without knowing where it falls.
PAGE = re.sub(r"\s+", " ", RAW)
DISTRICTS = RECORD["districts"]
PWCS = DISTRICTS["PWCS (Prince William County, VA)"]
APS = DISTRICTS["APS (Arlington, VA)"]


def test_every_district_has_a_row_and_every_row_is_measured():
    """The table is the finding. A district measured and left off it is a
    district whose absence changes the conclusion."""
    for name, found in DISTRICTS.items():
        assert name in PAGE, f"{name} was measured and is not on the page"
        if not found.get("published"):
            continue
        row = re.search(
            rf"\| {re.escape(name)} \| (\d+) \| (\d+) \| (\d+) \| "
            rf"\*\*([\d.]+)%\*\* \| (\d+)/(\d+) \|", PAGE)
        assert row, f"{name}'s row no longer parses"
        assert [int(row.group(1)), int(row.group(2)), int(row.group(3))] == [
            found["published"], found["read"],
            found["with_a_typed_prerequisite"]]
        assert float(row.group(4)) == \
            found["percent_of_pages_with_a_typed_prerequisite"]
        assert [int(row.group(5)), int(row.group(6))] == [
            found["links_resolving_to_a_published_course"], found["links"]]


def test_the_headline_contrast_is_the_measured_one():
    """**The denominator is pages READ**, not "courses stating a
    prerequisite". The first version divided by the latter, counting any
    non-empty prose field as a statement — and that field carries "No lab
    class" and "This course is not eligible for high school credit". It
    inflated the denominator differently per district, so the comparison
    partly measured how chatty each district's notes are.
    """
    said = re.search(
        r"\*\*([\d.]+)% of PWCS course pages carry a typed prerequisite "
        r"against ([\d.]+)% of Arlington's\*\*", PAGE)
    assert said, "the page no longer states the contrast"
    assert float(said.group(1)) == \
        PWCS["percent_of_pages_with_a_typed_prerequisite"]
    assert float(said.group(2)) == \
        APS["percent_of_pages_with_a_typed_prerequisite"]
    assert PWCS["percent_of_pages_with_a_typed_prerequisite"] > \
        APS["percent_of_pages_with_a_typed_prerequisite"] * 5, (
        "Arlington has caught up with PWCS; the page's conclusion no longer "
        "follows and needs rewriting rather than re-running")


def test_resolution_and_coverage_are_kept_apart():
    """The whole point of the rewrite. A district with one link that resolves
    scores 100% on resolution and nothing on coverage, and reporting only the
    first would say prerequisites generalise when they do not."""
    said = re.search(r"resolves \((\d+)/(\d+)\)", PAGE)
    assert said, "the page no longer reports PWCS's resolution rate"
    assert [int(said.group(1)), int(said.group(2))] == [
        PWCS["links_resolving_to_a_published_course"], PWCS["links"]]
    assert "Resolution generalises and coverage does not" in PAGE


def test_the_page_states_the_89_percent_is_superseded():
    """The issue asks about 89% and the repo's own source page has since
    replaced it with 100%. Answering the question with a coverage figure
    without saying so compares two different metrics silently."""
    assert "89%" in PAGE and "superseded" in PAGE
    assert "course-prerequisites.md" in PAGE


def test_the_prose_field_is_not_counted_as_prerequisites():
    """Named for what it is, with the evidence on the page — otherwise the
    next reader restores the inflated denominator as a bug fix."""
    assert "not** as" in PAGE or "and **not** as" in PAGE
    for quoted in ("No lab class", "not eligible for high school credit"):
        assert quoted in PAGE, (
            f"the page must show what the prose field actually carries; "
            f"{quoted!r} is why it is not a prerequisite count")


def test_the_sample_ceiling_is_described_as_a_ceiling():
    """Districts publishing fewer pages than the ceiling had their whole
    catalogue read. Calling it "60 pages each" was false for three of five."""
    assert f"Ceiling of {RECORD['sample_per_district']}" in PAGE
    assert "never the ceiling" in PAGE
    smaller = [n for n, f in DISTRICTS.items()
               if f.get("published") and f["sampled"] < RECORD["sample_per_district"]]
    assert smaller, (
        "no district is below the ceiling any more; the sentence about "
        "reading whole catalogues is now describing nothing")


def test_the_seed_and_the_client_list_are_on_the_page():
    """The issue asks for a recorded seed, and the districts must be traceable
    to the vendor's list rather than reading as hosts that happened to
    answer."""
    assert re.search(rf"seed `{RECORD['seed']}`", PAGE), "the seed is not stated"
    assert RECORD["vendor_client_list"] in PAGE


def test_the_enumeration_gap_is_a_measured_figure():
    """"An index crawl finds 73 of 817" lived only in a code comment, which
    is the one place this repo says a figure may not live. Both counts are in
    the record now and both are on the page."""
    said = re.search(
        r"PWCS publishes (\d+) course pages in a sitemap; an index crawl of "
        r"the same catalogue finds (\d+)", PAGE)
    assert said, "the page no longer states the enumeration gap"
    assert int(said.group(1)) == PWCS["courses_in_sitemap"]
    assert int(said.group(2)) == PWCS["courses_in_index_crawl"]

    without = [n for n, f in DISTRICTS.items() if not f.get("has_sitemap")]
    stated = re.search(r"\*\*(\d+) of the five publish no sitemap at all\*\*",
                       PAGE)
    assert stated, "the page no longer counts the districts without a sitemap"
    assert int(stated.group(1)) == len(without), (
        f"the page says {stated.group(1)}; {len(without)} publish no sitemap")


def test_the_page_states_what_it_does_not_establish():
    """Five districts, one vendor, and Arlington's figure rests on a single
    typed prerequisite. The page has to say so, or it reads as a claim about
    US school districts."""
    assert "What this does not establish" in PAGE
    assert "one vendor" in PAGE
    assert APS["with_a_typed_prerequisite"] == 1, (
        "Arlington no longer rests on a single observation; the caveat is "
        "now understating the evidence")
    assert "single typed prerequisite" in PAGE

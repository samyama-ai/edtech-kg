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
        if not found.get("candidate_course_paths"):
            continue
        row = re.search(
            rf"\| {re.escape(name)} \| (\d+) \| (\d+) \| (\d+) \| "
            rf"\*\*([\d.]+)%\*\* \| (\d+)/(\d+)", PAGE)
        assert row, f"{name}'s row no longer parses"
        assert [int(row.group(1)), int(row.group(2)), int(row.group(3))] == [
            found["candidate_course_paths"], found["read"],
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
    said = re.search(r"resolves — (\d+)/(\d+)\s*at PWCS", PAGE)
    assert said, "the page no longer reports PWCS's resolution rate"
    assert [int(said.group(1)), int(said.group(2))] == [
        PWCS["links_resolving_to_a_published_course"], PWCS["links"]]
    # EVERY district's, not only PWCS's — "resolution generalises" is a claim
    # about all of them and one figure cannot carry it.
    for name, found in DISTRICTS.items():
        if found["links"]:
            assert found["percent_of_links_that_resolve"] == 100.0, (
                f"{name} resolves {found['percent_of_links_that_resolve']}% "
                f"of its links; the page says resolution generalises")
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
    # The sentence about reading whole catalogues is conditional — it applies
    # only while some district publishes fewer pages than the ceiling. Since
    # the pager is followed, none does; the sentence is a rule, not a claim
    # about today, so it stays and this asserts which case we are in.
    smaller = [n for n, f in DISTRICTS.items()
               if f.get("candidate_course_paths")
               and f["read"] < RECORD["sample_per_district"]]
    assert not smaller, (
        f"{smaller} read fewer pages than the ceiling; the page should say so "
        f"rather than implying every district was sampled to {RECORD['sample_per_district']}")


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
    # The CALIBRATION, which is what lets the other four population figures
    # be read as counts rather than floors. On PWCS both methods work, so the
    # crawl can be checked against a census.
    said = re.search(
        r"the crawl finds (\d+) of\s+the sitemap's (\d+)", PAGE)
    assert said, "the page no longer states the crawl's calibration"
    assert int(said.group(1)) == PWCS["courses_in_index_crawl"]
    assert int(said.group(2)) == PWCS["courses_in_sitemap"]
    assert PWCS["courses_in_index_crawl"] > PWCS["courses_in_sitemap"] * 0.9, (
        f"the crawl finds {PWCS['courses_in_index_crawl']} of "
        f"{PWCS['courses_in_sitemap']} — no longer close to a census, so the "
        f"other districts' population figures are floors and the page must "
        f"say so instead of calling them counts")

    without = [n for n, f in DISTRICTS.items() if not f.get("has_sitemap")]
    stated = re.search(r"(\d+) of the five publish no sitemap", PAGE)
    assert stated, "the page no longer counts the districts without a sitemap"
    assert int(stated.group(1)) == len(without)


def test_the_page_states_what_it_does_not_establish():
    """Five districts, one vendor, and Arlington's figure rests on a single
    typed prerequisite. The page has to say so, or it reads as a claim about
    US school districts."""
    assert "What this does not establish" in PAGE
    assert "one vendor" in PAGE
    said = re.search(
        r"Arlington's figure rests on (\d+) typed\s+prerequisites in (\d+) pages",
        PAGE)
    assert said, "the page no longer sizes Arlington's evidence"
    assert int(said.group(1)) == APS["with_a_typed_prerequisite"]
    assert int(said.group(2)) == APS["read"]


def test_the_correction_is_recorded_not_quietly_replaced():
    """The first version reported Arlington at 1.7% and Clover Park with 51
    pages, because the crawl was not following the catalogue's pager — it read
    the first page of each index and sampled from that, a BIASED subset rather
    than a small one. A page that silently swapped the numbers would leave the
    next reader with no way to know the method changed."""
    assert "not following the catalogue's pager" in PAGE
    assert "1.7%" in PAGE and "51 pages" in PAGE, (
        "the superseded figures must be named, or the correction is invisible")
    assert str(APS["candidate_course_paths"]) in PAGE

    # The SECOND correction, from the same round: Central Islip's links were
    # not deduplicated, so a course linked twice counted twice — in a rate
    # whose whole claim is that the links land.
    assert "not deduplicated" in PAGE
    said = re.search(r"reported at 10 resolving links where it publishes\s+(\d+)",
                     PAGE)
    assert said, "the page no longer records the deduplication correction"
    assert int(said.group(1)) == \
        DISTRICTS["Central Islip (NY)"]["links"]

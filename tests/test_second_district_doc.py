"""`docs/sources/second-district.md` held to the record that produced it.

The page answers edtech-kg#19 — does a second district's prerequisites resolve
the way PWCS's do — and the answer decides what kind of product this is. A
figure that drifts here changes a business conclusion, not a footnote.

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
PAGE = DOC.read_text(encoding="utf-8")
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
            rf"\| {re.escape(name)} \| (\d+) \| ([a-z ]+) \| (\d+) \| (\d+) \| "
            rf"\*\*([\d.]+)%\*\* \|", PAGE)
        assert row, f"{name}'s row no longer parses"
        assert int(row.group(1)) == found["published"]
        assert row.group(2).strip() == found["how"]
        assert int(row.group(3)) == found["state_a_prerequisite"]
        assert int(row.group(4)) == found["state_it_in_the_typed_field"]
        assert float(row.group(5)) == found["percent_stated_in_the_typed_field"]


def test_the_headline_contrast_is_the_measured_one():
    """The sentence the whole issue turns on."""
    said = re.search(
        r"\*\*PWCS states ([\d.]+)% of its prerequisites in the\nfield that "
        r"produces an edge\. Arlington states ([\d.]+)%\.\*\*", PAGE)
    assert said, "the page no longer states the contrast"
    assert float(said.group(1)) == PWCS["percent_stated_in_the_typed_field"]
    assert float(said.group(2)) == APS["percent_stated_in_the_typed_field"]
    assert PWCS["percent_stated_in_the_typed_field"] > \
        APS["percent_stated_in_the_typed_field"] * 2, (
        "Arlington has caught up with PWCS; the page's conclusion — that "
        "prerequisites are per-district — no longer follows and needs "
        "rewriting rather than re-running")


def test_the_links_that_exist_are_reported_as_working():
    """"The problem is not broken links" is a claim about the resolution rate,
    and it is the half of the finding that is GOOD news. Dropping it would
    make the page read as "the data is broken" when it is "the data is
    absent" — a different problem with a different fix."""
    said = re.search(r"\*\*Where the links exist, they work\.\*\* (\d+) of\n(\d+)", PAGE)
    assert said, "the page no longer reports the resolution rate"
    assert int(said.group(1)) == PWCS["links_resolving_to_a_published_course"]
    assert int(said.group(2)) == PWCS["links"]


def test_the_method_is_stated_because_it_is_what_makes_this_comparable():
    """Same field, same sample size, same seed. The issue asks for exactly
    this, and a comparison drawn differently per district would measure the
    method."""
    assert f"seed\n`{RECORD['seed']}`" in PAGE or \
        f"seed `{RECORD['seed']}`" in PAGE, "the seed is not on the page"
    assert str(RECORD["sample_per_district"]) in PAGE
    assert RECORD["vendor_client_list"] in PAGE, (
        "the districts must be traceable to the vendor's own client list — "
        "otherwise they read as hosts that happened to answer")


def test_the_page_states_what_it_does_not_establish():
    """Five districts, one vendor. The conclusion is about the question as
    asked and the page has to say so, or it reads as a claim about US school
    districts."""
    assert "What this does not establish" in PAGE
    assert "one vendor" in PAGE


def test_the_enumeration_finding_is_not_lost():
    """Three of five publish no sitemap, and PWCS's own population figure
    comes from one. That is a separate failure of generalisation from the
    field-use one and is easy to drop when tightening the prose."""
    assert "no sitemap at all" in PAGE
    # NO SITEMAP, not "needed a crawl" — Kenosha publishes a sitemap holding
    # only pathway pages, so it crawls while still having one. The page's
    # sentence is about the first.
    without = [n for n, f in DISTRICTS.items() if not f.get("has_sitemap")]
    assert len(without) == 3, (
        f"{len(without)} districts publish no sitemap, not 3; the page says "
        f"three: {without}")
